import json
import re
import ollama
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import os
import socket
from dotenv import load_dotenv
import google.generativeai as genai
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from gmail_service import scan_gmail_attachments, send_gmail_message

# Cấu hình Gemini
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY"))

# Cấu hình chuẩn cho Ollama
OLLAMA_MODEL = 'qwen2.5:3b'
OLLAMA_OPTIONS = {
    "temperature": 0.0,
    "num_ctx": 2048,
    "num_thread": 6
}
KEEP_ALIVE = "10m"

# Cấu hình đường dẫn Tesseract (Sửa nếu cần)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Khởi tạo FastAPI App
app = FastAPI(title="ATS AI Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def read_pdf(file_bytes):
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for i, page in enumerate(doc):
            if i >= 2: break  # Chỉ đọc tối đa 2 trang đầu
            
            page_text = page.get_text()
            if page_text.strip():
                text += page_text
            else:
                # Quét OCR nếu là file ảnh
                pix = page.get_pixmap(dpi=150)
                img = Image.open(io.BytesIO(pix.tobytes()))
                text += pytesseract.image_to_string(img, lang='eng+vie')
        return text, None
    except Exception as e:
        print(f"Lỗi đọc PDF: {e}")
        return "", str(e)

def extract_json_from_text(raw_text):
    """Sử dụng Regex để bóc tách JSON an toàn từ phản hồi của model"""
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Lỗi parse JSON: {e}")
            return None
    return None

def check_internet(host="8.8.8.8", port=53, timeout=3):
    """Kiểm tra kết nối Internet"""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False

def call_ollama(prompt):
    """Hàm tiện ích gọi Ollama API (Offline Fallback)"""
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            options=OLLAMA_OPTIONS,
            keep_alive=KEEP_ALIVE,
            format='json'
        )
        raw_text = response['message']['content'].strip()
        return extract_json_from_text(raw_text)
    except Exception as e:
        print(f"Lỗi khi gọi Ollama: {e}")
        return None

def call_ai_hybrid(prompt):
    """Kiến trúc Hybrid: Ưu tiên Gemini, Fallback sang Ollama"""
    import time
    # Nghỉ 3 giây TRƯỚC KHI gọi để đảm bảo không bắn request liên tục quá nhanh
    time.sleep(1)
    
    if check_internet():
        try:
            # SỬ DỤNG gemini-2.0-flash (Model 1.5 đã bị Google xóa bỏ trong năm 2026)
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            raw_text = response.text.strip()
            return extract_json_from_text(raw_text)
        except Exception as e:
            print("Đang dùng modal tự build Ollama...")
            return call_ollama(prompt)
    else:
        print("Mất mạng! Chuyển sang chế độ Offline với Ollama...")
        return call_ollama(prompt)

# ==========================================
# CẤU TRÚC STATE-BASED (LƯU TRỮ JD BLUEPRINT)
# ==========================================
import hashlib

class ATSState:
    def __init__(self):
        self.jd_blueprint = None
        self.current_jd_hash = None

global_ats_state = ATSState()

def parse_jd_to_json(jd_text):
    """
    HÀM CỐT LÕI: Đọc văn bản JD và trích xuất thành JSON.
    """
    prompt = f"""Bạn là một chuyên gia phân tích Job Description (JD). 
Nhiệm vụ: Đọc văn bản JD dưới đây và trích xuất thông tin thành định dạng JSON.

YÊU CẦU BẮT BUỘC:
- Bắt buộc không được suy diễn kỹ năng ngoài văn bản.
- CHỈ trích xuất TÊN KỸ NĂNG CỤ THỂ, ngắn gọn (VD: Python, Machine Learning, OOP, REST API). TUYỆT ĐỐI KHÔNG bưng nguyên cả câu dài hay đoạn văn vào mảng.
- Các kỹ năng 'must have', 'required', 'yêu cầu bắt buộc' đưa vào mảng must_have_skills.
- Các kỹ năng 'nice to have', 'ưu tiên', 'lợi thế' đưa vào mảng nice_to_have_skills.

[VĂN BẢN JD]:
{jd_text}

CHỈ TRẢ VỀ JSON DUY NHẤT THEO SCHEMA SAU:
{{
    "job_title": "string",
    "domain": "string",
    "required_years_of_experience": 0.0,
    "must_have_skills": ["danh sách chính xác từ JD"],
    "nice_to_have_skills": ["danh sách từ JD"]
}}
"""
    print("[1/3] Đang phân tích JD...")
    result = call_ai_hybrid(prompt)
    if result is None:
        return {"error": "Không thể parse JD"}
    
    # Ép kiểu an toàn
    if "required_years_of_experience" in result and isinstance(result["required_years_of_experience"], str):
        try:
            result["required_years_of_experience"] = float(result["required_years_of_experience"])
        except:
            result["required_years_of_experience"] = 0.0
            
    return result

def parse_cv_to_json(cv_text):
    """
    HÀM 2: Đọc văn bản CV và trích xuất thành JSON.
    """
    prompt = f"""Bạn là một chuyên gia phân tích CV.
Nhiệm vụ: Đọc văn bản CV dưới đây và trích xuất thông tin thành định dạng JSON.

YÊU CẦU BẮT BUỘC:
- Chỉ lấy kỹ năng có thật trong CV.
- Liệt kê ĐẦY ĐỦ TẤT CẢ các kỹ năng được nhắc đến trong toàn bộ CV (đặc biệt chú ý liệt kê toàn bộ các kỹ năng trong mục Skills/Core Skills).
- Tính TỔNG SỐ NĂM KINH NGHIỆM làm việc. (Bỏ qua thời gian học đại học).
- Mốc năm hiện tại bắt buộc dùng là 2026.
- Thực tập sinh (Intern) = 0 năm kinh nghiệm (hoặc tính theo thời gian thực tập nếu có).

[VĂN BẢN CV]:
{cv_text}

CHỈ TRẢ VỀ JSON DUY NHẤT THEO SCHEMA SAU:
{{
    "candidate_name": "string",
    "candidate_email": "string (Email của ứng viên. Cực kỳ quan trọng. Nếu không thấy để rỗng '')",
    "total_years_experience": 0.0,
    "experience_details": ["string (nháp phép tính: [Tên Job] - [Thời gian] - [Số năm])"],
    "extracted_skills": ["danh sách kỹ năng trong CV"]
}}
"""
    print("[2/3] Đang phân tích CV...")
    result = call_ai_hybrid(prompt)
    if result is None:
        return {"error": "Không thể parse CV"}
    
    # Ép kiểu an toàn
    if "total_years_experience" in result and isinstance(result["total_years_experience"], str):
        try:
            result["total_years_experience"] = float(result["total_years_experience"])
        except:
            result["total_years_experience"] = 0.0
            
    return result

def match_cv_jd(cv_json_dict, jd_json_dict, raw_cv_text=""):
    """
    HÀM 3: Nhận vào 2 object JSON (Hàm 1 và 2), so sánh và chấm điểm.
    """
    cv_str = json.dumps(cv_json_dict, ensure_ascii=False, indent=2)
    jd_str = json.dumps(jd_json_dict, ensure_ascii=False, indent=2)
    
    prompt = f"""Bạn là một hệ thống ATS đánh giá độ phù hợp của ứng viên.
Sử dụng Blueprint JD cố định dưới đây để đối chiếu với CV mới. Tuyệt đối không thay đổi tiêu chí chấm điểm giữa các CV.
Nhiệm vụ: Phân tích 2 dữ liệu JSON của CV và JD dưới đây để đưa ra nhận xét tuyển dụng chi tiết. KHÔNG CẦN CHẤM ĐIỂM BẰNG SỐ (Hệ thống sẽ tự tính).

Chú ý các tiêu chí nới lỏng mới:
- Chấp nhận các kỹ năng tự học, làm đồ án (được tính tương đương kinh nghiệm).
- Tích cực khen ngợi nếu ứng viên có chứng chỉ (Coursera, Udemy), link GitHub, đồ án cá nhân, hoặc có sự nhiệt huyết trong phần tóm tắt.

[JSON JD]:
{jd_str}

[JSON CV]:
{cv_str}

BẠN BẮT BUỘC PHẢI TRẢ VỀ ĐÚNG CẤU TRÚC JSON SAU (KHÔNG THÊM BẤT KỲ VĂN BẢN NÀO BÊN NGOÀI):
{{
    "tong_quan": {{
        "nganh_nghe": "(Tóm tắt ngành nghề của ứng viên. VD: Công nghệ thông tin / Web Development)"
    }},
    "phan_tich_linh_vuc": {{
        "linh_vuc_jd": "(Lĩnh vực JD yêu cầu)",
        "linh_vuc_cv": "(Lĩnh vực ứng viên có kinh nghiệm)",
        "phu_hop": true/false,
        "nhan_xet": "(1 câu nhận xét khớp hay lệch)"
    }},
    "ky_nang": {{
        "ung_vien_co": ["(Danh sách kỹ năng CV có mà JD yêu cầu)"],
        "bat_buoc_con_thieu": ["(Danh sách kỹ năng BẮT BUỘC của JD mà CV không có)"]
    }},
    "nhan_xet_tuyen_dung": {{
        "diem_manh": ["(Liệt kê cụ thể, đặc biệt chú ý khen ngợi các khóa học Coursera/Udemy/GitHub hoặc đồ án nếu có. Nếu không có để mảng rỗng [])"],
        "diem_yeu": ["(Liệt kê cụ thể. VD: 'Thiếu kỹ năng thực tế với ReactJS'. Nếu không có để mảng rỗng [])"],
        "ghi_chu_phong_van": "(1 câu gợi ý cho HR hỏi phỏng vấn)",
        "ly_do_quyet_dinh": "(Tóm tắt 1-2 câu về mức độ phù hợp của ứng viên)"
    }}
}}
"""
    print("[3/3] Đang tiến hành Matching và Chấm điểm...")
    result = call_ai_hybrid(prompt)
    if result is None:
        return {"error": "Không thể match CV và JD"}
        
    # =========================================================
    # PYTHON HARD VERIFICATION (TÍNH ĐIỂM BẰNG CODE ĐỂ CHỐNG ẢO GIÁC)
    # =========================================================
    def safe_array(val):
        if isinstance(val, str): 
            return [s.strip() for s in val.split(',') if s.strip()]
        if isinstance(val, list):
            res = []
            for item in val:
                if isinstance(item, str):
                    res.extend([s.strip() for s in item.split(',') if s.strip()])
                else:
                    res.append(item)
            return res
        return []

    must_have = safe_array(jd_json_dict.get("must_have_skills", []))
    nice_to_have = safe_array(jd_json_dict.get("nice_to_have_skills", []))
    extracted = safe_array(cv_json_dict.get("extracted_skills", []))
    yoe = float(cv_json_dict.get("total_years_experience", 0))
    req_yoe = float(jd_json_dict.get("required_years_of_experience", 0))
    
    extracted_lower = " ".join([str(s).lower() for s in extracted])
    full_text_lower = (extracted_lower + " " + raw_cv_text).lower()
    
    def has_skill(skill, text):
        import re
        skill_lower = skill.lower()
        if not skill_lower.isalnum():
            return skill_lower in text
        return bool(re.search(rf'\b{re.escape(skill_lower)}\b', text))
    
    # 1. Điểm kỹ năng bắt buộc (Max 45)
    matched_must_have = [s for s in must_have if has_skill(s, full_text_lower)]
    if len(must_have) == 0:
        ky_nang_bat_buoc = 45
    else:
        # Nếu ứng viên thiếu kỹ năng, chỉ trừ tối đa 10đ cho mỗi kỹ năng bị thiếu
        missing_core = len(must_have) - len(matched_must_have)
        ky_nang_bat_buoc = max(0, 45 - (missing_core * 10))
        
    # 2. Số năm kinh nghiệm (Max 30)
    if req_yoe == 0:
        so_nam_va_cap_do = 30
    else:
        if yoe >= req_yoe:
            so_nam_va_cap_do = 30
        else:
            # Mỗi năm thiếu so với JD chỉ trừ 5đ (thay vì 8đ)
            so_nam_va_cap_do = max(0, int(30 - 5 * (req_yoe - yoe)))
            
    # 3. Kỹ năng cộng điểm (Max 10)
    matched_nice = [s for s in nice_to_have if has_skill(s, full_text_lower)]
    if len(nice_to_have) == 0:
        ky_nang_cong_diem = 10
    else:
        ky_nang_cong_diem = min(10, int(len(matched_nice) * (10 / len(nice_to_have))))
        
    # Thưởng: AI chủ động tìm các chứng chỉ Coursera, Udemy, Link GitHub
    if "coursera" in full_text_lower or "udemy" in full_text_lower or "github" in full_text_lower:
        ky_nang_cong_diem = 10
        
    # 4. Chất lượng kinh nghiệm (Max 15)
    if yoe > 0:
        chat_luong_kinh_nghiem = 15
    elif "project" in full_text_lower or "đồ án" in full_text_lower or "github" in full_text_lower:
        # Nâng mức điểm cho đồ án trường học lên 10đ
        chat_luong_kinh_nghiem = 10 
    else:
        chat_luong_kinh_nghiem = 5

    # KIỂM TRA KILL SWITCH
    ks = False
    if len(must_have) > 0 and len(matched_must_have) == 0:
        ks = True # Lệch hoàn toàn Tech Stack
    elif req_yoe >= 2 and yoe < 0.5:
        ks = True # Thiếu trầm trọng kinh nghiệm
        
    if ks:
        ky_nang_bat_buoc = 0
        so_nam_va_cap_do = 0
        chat_luong_kinh_nghiem = 0
        ky_nang_cong_diem = 0
        
    total_score = ky_nang_bat_buoc + so_nam_va_cap_do + chat_luong_kinh_nghiem + ky_nang_cong_diem
    
    # TẦNG 2: NGƯỠNG QUYẾT ĐỊNH
    if ks:
        quyet_dinh = "KHÔNG ĐẠT"
    elif total_score >= 60:
        quyet_dinh = "ĐẠT"
    elif total_score >= 30:
        quyet_dinh = "CHỜ XEM XÉT"
    else:
        quyet_dinh = "KHÔNG ĐẠT"
        
    # Tái cấu trúc lại Output JSON cho chuẩn với Frontend React
    if "tong_quan" not in result: result["tong_quan"] = {}
    result["tong_quan"]["diem_tong"] = total_score
    result["tong_quan"]["quyet_dinh"] = quyet_dinh
    result["tong_quan"]["ten_ung_vien"] = cv_json_dict.get("candidate_name", "Không xác định")
    result["tong_quan"]["so_nam_kinh_nghiem"] = yoe
    
    result["chi_tiet_diem"] = {
        "ky_nang_bat_buoc": ky_nang_bat_buoc,
        "so_nam_va_cap_do": so_nam_va_cap_do,
        "chat_luong_kinh_nghiem": chat_luong_kinh_nghiem,
        "ky_nang_cong_diem": ky_nang_cong_diem
    }
    
    # Ép AI mảng kỹ năng thiếu để UI hiển thị đúng
    if "ky_nang" not in result: result["ky_nang"] = {}
    result["ky_nang"]["bat_buoc_con_thieu"] = [s for s in must_have if not has_skill(s, full_text_lower)]
    result["ky_nang"]["ung_vien_co"] = matched_must_have + matched_nice
    
    return result

# ==========================================
# QUẢN LÝ LUỒNG CHẠY (PIPELINE & BATCH)
# ==========================================

def prepare_job(jd_text):
    """
    HÀM A: Chỉ chạy 1 lần. Nhận jd_text thô, gọi AI để chuyển thành jd_json.
    Trả về jd_json này để sử dụng xuyên suốt phiên làm việc (Bulk Scan).
    """
    jd_hash = hashlib.md5(jd_text.encode('utf-8')).hexdigest()
    
    # Kiểm tra State: Nếu JD chưa đổi, dùng lại Blueprint cũ
    if global_ats_state.current_jd_hash == jd_hash and global_ats_state.jd_blueprint:
        print("[CACHE] Đã có JD Blueprint trong bộ nhớ. Tái sử dụng để tiết kiệm AI!")
        return global_ats_state.jd_blueprint
        
    print("\n[HỆ THỐNG] Khởi tạo Job mới. Bắt đầu phân tích JD Blueprint...")
    jd_json = parse_jd_to_json(jd_text)
    
    if "error" not in jd_json:
        global_ats_state.jd_blueprint = jd_json
        global_ats_state.current_jd_hash = jd_hash
        
    return jd_json

def process_single_cv(cv_text, jd_blueprint, filename=""):
    """Xử lý 1 file CV dựa trên Blueprint JD đã chốt"""
    cv_json = parse_cv_to_json(cv_text)
    if "error" in cv_json:
        return None, "Lỗi phân tích CV"
        
    result = match_cv_jd(cv_json, jd_blueprint, cv_text)
    if "error" in result:
        return None, "Lỗi so khớp CV và JD"
        
    # Gắn thêm metadata để Frontend hiển thị
    result["filename"] = filename
    result["candidate_name"] = cv_json.get("candidate_name", "Không xác định")
    result["candidate_email"] = cv_json.get("candidate_email", "")
    return result, None

def batch_processor(cv_data_list, jd_blueprint):
    """
    HÀM B: Vòng lặp chạy hàng loạt cho mảng Bulk Scan.
    cv_data_list: mảng các dict chứa {"filename": str, "text": str}
    """
    results = []
    total = len(cv_data_list)
    for idx, cv_item in enumerate(cv_data_list):
        print(f"\n[BATCH PROCESSOR] Đang xử lý CV {idx+1}/{total}: {cv_item['filename']}")
        res, err = process_single_cv(cv_item["text"], jd_blueprint, cv_item["filename"])
        results.append({
            "filename": cv_item["filename"],
            "success": res is not None,
            "data": res,
            "error": err
        })
    return results

def process_pipeline(cv_text, jd_text, filename=""):
    """Wrapper thực thi tương thích ngược cho API & Gmail"""
    jd_blueprint = prepare_job(jd_text)
    if "error" in jd_blueprint:
        return None, "Lỗi phân tích JD"
        
    return process_single_cv(cv_text, jd_blueprint, filename)

# ==========================================
# CÁC API ENDPOINTS DÀNH CHO FRONTEND
# ==========================================

@app.post("/api/scan-local-cv")
async def scan_local_cv(jd_text: str = Form(...), file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file PDF")

    try:
        file_bytes = await file.read()
        cv_text, pdf_err = read_pdf(file_bytes)
        
        if not cv_text:
            raise HTTPException(status_code=500, detail=f"Lỗi đọc PDF: {pdf_err}")

        cv_text = cv_text[:3000] # Giới hạn 3000 ký tự đầu tiên để tối ưu AI

        # Chạy Pipeline 3 bước
        result, err = process_pipeline(cv_text, jd_text, file.filename)
        
        if not result:
            raise HTTPException(status_code=500, detail=err)

        return {"status": "success", "data": result}
    except Exception as e:
        print(f"API Error (Local CV): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scan-gmail")
async def scan_gmail(
    jd_text: str = Form(...), 
    query: str = Form(...), 
    time_range: str = Form("all"),
    max_results: Optional[int] = Form(50)
):
    try:
        final_query = query
        if time_range != "all":
            final_query = f"{query} newer_than:{time_range}"
            
        # Truyền hàm read_pdf và process_pipeline vào Gmail Service
        results = scan_gmail_attachments(jd_text, final_query, max_results, read_pdf, process_pipeline)
        return {"status": "success", "data": results}
    except Exception as e:
        print(f"API Error (Gmail): {e}")
        raise HTTPException(status_code=500, detail=str(e))


class EmailRequest(BaseModel):
    email: str
    name: str

@app.post("/api/send-interview-email")
async def send_interview_email(request: EmailRequest):
    subject = f"Thư Mời Phỏng Vấn - Chúc mừng {request.name} đã vượt qua vòng sơ loại!"
    body = f"""Chào {request.name},
    
Chúc mừng bạn đã vượt qua vòng sơ loại hồ sơ AI của chúng tôi. 
Hồ sơ của bạn được đánh giá là rất phù hợp với vị trí mà chúng tôi đang tìm kiếm.

Để chuẩn bị cho bước tiếp theo, vui lòng điền thông tin bổ sung vào biểu mẫu sau đây:
https://forms.gle/JE7m5EQF4x37jhvQ6

Nếu bạn có bất kỳ câu hỏi nào, đừng ngần ngại phản hồi lại email này.

Trân trọng,
Bộ phận Tuyển dụng
"""
    success, msg = send_gmail_message(request.email, subject, body)
    if success:
        return {"message": "Đã gửi email thành công!"}
    else:
        raise HTTPException(status_code=500, detail=msg)

if __name__ == "__main__":
    import uvicorn, os
    host = os.getenv("HOST", "[IP_ADDRESS]")
    print("🚀 Khởi động Server FastAPI tại http://127.0.0.1:8000")
    uvicorn.run("main:app", host=host, port=8000, reload=True)