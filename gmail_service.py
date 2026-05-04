import os.path
import base64
import concurrent.futures
import re
from email.utils import parseaddr
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send'
]

EMAIL_REGEX = re.compile(r'(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.+-])')

def normalize_email_address(value):
    """Lấy địa chỉ email hợp lệ từ chuỗi AI/Gmail trả về."""
    if not value:
        return ""

    raw_value = str(value).strip().strip("'\"")
    _, parsed_email = parseaddr(raw_value)

    for candidate in (parsed_email, raw_value):
        match = EMAIL_REGEX.search(candidate)
        if match:
            return match.group(1)

    return ""

def get_gmail_service():
    """Xác thực và khởi tạo Gmail API Service"""
    creds = None
    
    # BƯỚC 1: Tìm xem trong máy đã có thẻ nhớ "token.json" của lần đăng nhập trước chưa?
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    # BƯỚC 2: Nếu chưa có thẻ nhớ, HOẶC thẻ nhớ bị hết hạn (hết phiên)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                # Thẻ nhớ hết hạn nhưng có thể tự động gia hạn (Refresh) ngầm
                creds.refresh(Request())
            except Exception as e:
                # Nếu không gia hạn được (VD: đổi mật khẩu Gmail), mới bắt đăng nhập lại
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            # Lần đầu tiên chạy, mở trình duyệt bắt chọn Email
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # BƯỚC 3 (QUAN TRỌNG NHẤT): LƯU LẠI THẺ NHỚ!
        # Code cũ của bạn thiếu đoạn này nên nó cứ hỏi hoài.
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    # BƯỚC 4: Trả về công cụ lấy thư
    return build('gmail', 'v1', credentials=creds)

def process_ai_only(filename, sender, file_data, jd_text, read_pdf_func, extract_ai_func):
    """Tiến trình xử lý PDF và AI riêng biệt (Thread-safe)"""
    try:
        cv_text, pdf_err = read_pdf_func(file_data)
        if not cv_text:
            return {"filename": filename, "candidate_name": sender, "status": "error", "errorMsg": f"Lỗi đọc PDF: {pdf_err}"}
            
        ai_result, ai_err = extract_ai_func(cv_text, jd_text, filename)
        
        if ai_result:
            # Trích xuất email từ trường 'From' (VD: "Name <email@example.com>" hoặc "email@example.com")
            sender_email = normalize_email_address(sender)
            
            ai_result['filename'] = filename
            # Nếu muốn giữ tên gốc từ CV do AI bóc tách thì không ghi đè, hoặc lấy tên từ sender
            # Ở đây giữ nguyên tên AI tìm được, và dùng sender_email
            ai_result['candidate_email'] = sender_email
            ai_result['source'] = 'Gmail'
            return ai_result
        else:
            return {"filename": filename, "candidate_name": sender, "status": "error", "errorMsg": f"Lỗi AI: {ai_err}"}
    except Exception as e:
        return {"filename": filename, "candidate_name": sender, "status": "error", "errorMsg": f"Lỗi hệ thống: {str(e)}"}

def scan_gmail_attachments(jd_text, query, max_results, read_pdf_func, extract_ai_func):
    """Lọc email, lấy danh sách file và quét đa luồng"""
    service = get_gmail_service()
    
    search_query = f"{query} has:attachment filename:pdf"
    results = service.users().messages().list(userId='me', q=search_query, maxResults=max_results).execute()
    messages = results.get('messages', [])
    
    if not messages:
        return []
        
    tasks = []
    
    # BƯỚC 1: Thu thập và Tải file tuần tự (Tránh lỗi IncompleteRead do Google API không thread-safe)
    for msg in messages:
        msg_id = msg['id']
        message = service.users().messages().get(userId='me', id=msg_id).execute()
        
        headers = message['payload'].get('headers', [])
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
        
        parts = message['payload'].get('parts', [])
        if not parts and 'body' in message['payload']:
            parts = [message['payload']]
            
        for part in parts:
            if part.get('filename') and part['filename'].lower().endswith('.pdf'):
                attachment_id = part['body'].get('attachmentId')
                if attachment_id:
                    try:
                        attachment = service.users().messages().attachments().get(
                            userId='me', messageId=msg_id, id=attachment_id).execute()
                        file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))
                        tasks.append((part['filename'], sender, file_data))
                    except Exception as e:
                        print(f"Không thể tải file {part['filename']} từ Gmail: {e}")
                    
    # BƯỚC 2: Chỉ sử dụng đa luồng cho phần đọc PDF và AI (Nặng nhất)
    # Giảm xuống 2 workers để tránh quá tải Ollama cục bộ gây sập RAM
    analyzed_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_to_task = {
            executor.submit(process_ai_only, filename, sender, file_data, jd_text, read_pdf_func, extract_ai_func): filename
            for (filename, sender, file_data) in tasks
        }
        
        for future in concurrent.futures.as_completed(future_to_task):
            try:
                res = future.result()
                if res.get('status') != 'error':
                    analyzed_results.append(res)
                else:
                    print(f"Lỗi khi xử lý file {res['filename']}: {res['errorMsg']}")
            except Exception as exc:
                print(f"File sinh lỗi: {exc}")
                
    return analyzed_results

def send_gmail_message(to_email, subject, body):
    """Gửi email tới ứng viên qua Gmail API"""
    from email.message import EmailMessage
    try:
        clean_to_email = normalize_email_address(to_email)
        if not clean_to_email:
            return False, f"Email không hợp lệ: {to_email}"

        service = get_gmail_service()
        message = EmailMessage()
        message.set_content(body)
        message['To'] = clean_to_email
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        service.users().messages().send(userId="me", body=create_message).execute()
        return True, "Email sent successfully"
    except Exception as e:
        return False, str(e)
