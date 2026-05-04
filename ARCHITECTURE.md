# DTNCV — AI Resume Screening System: Architecture Document

> **Version:** 1.0 | **Last updated:** 2026-05-02

---

## 1. Tổng quan hệ thống (System Overview)

**DTNCV** là hệ thống ATS (Applicant Tracking System) tích hợp AI, cho phép HR tự động sàng lọc hồ sơ ứng viên (CV) dựa trên Mô tả Công việc (JD) thông qua **Semantic Search** sử dụng Vector Embedding cục bộ.

```
┌──────────────────────────────────────────────────────┐
│                    NGƯỜI DÙNG (HR)                   │
└─────────────┬──────────────────────────┬─────────────┘
              │ Upload CV (PDF)          │ Kết quả / Quyết định
              ▼                          ▼
┌─────────────────────────┐   ┌──────────────────────────┐
│   Frontend (React/Vite) │   │   Gmail Inbox (nguồn CV) │
│   localhost:5173        │   │   Gmail API              │
└─────────────┬───────────┘   └───────────┬──────────────┘
              │ HTTP POST (FormData)      │
              └────────────┬──────────────┘
                           ▼
              ┌────────────────────────────┐
              │  Backend (FastAPI/Python)  │
              │  localhost:8000            │
              │  ┌──────────────────────┐  │
              │  │  Ollama Embedding    │  │
              │  │  (qwen2.5:3b, local) │  │
              │  └──────────────────────┘  │
              └────────────────────────────┘
```

---

## 2. Kiến trúc tổng thể (High-Level Architecture)

Hệ thống chia thành **3 layer** chính:

| Layer | Công nghệ | Vai trò |
|---|---|---|
| **Presentation** | React 18 + Vite + TailwindCSS | UI dashboard, hiển thị kết quả |
| **API / Business Logic** | FastAPI (Python) | Xử lý CV, tính điểm, gửi email |
| **AI / Embedding** | Ollama (Local LLM) + NumPy | Tạo vector embedding, cosine similarity |

---

## 3. Backend Architecture

### 3.1 Cấu trúc file

```
FILTER_CV_AI/
├── main.py            # FastAPI app + toàn bộ business logic
├── gmail_service.py   # Gmail API integration (đọc & gửi email)
├── auth.py            # Script cấp quyền OAuth2 lần đầu
├── requirements.txt   # Python dependencies
├── .env               # Biến môi trường (API keys, thresholds)
├── credentials.json   # Google OAuth2 client credentials
├── token.json         # OAuth2 access/refresh token (auto-generated)
└── validate_cvs/      # Thư mục chứa CV test cục bộ
```

### 3.2 FastAPI Application (`main.py`)

#### API Endpoints

| Method | Endpoint | Chức năng |
|---|---|---|
| `POST` | `/api/scan-local-cv` | Upload & chấm điểm 1 CV từ máy tính |
| `POST` | `/api/scan-gmail` | Quét hộp thư Gmail, chấm điểm hàng loạt |
| `POST` | `/api/send-interview-email` | Gửi email mời phỏng vấn tới ứng viên đạt |

#### State Management (`ATSState`)

```python
class ATSState:
    current_jd_hash: str       # MD5 hash của JD hiện tại
    jd_embedding: list[float]  # Vector embedding của JD (cached)
    jd_text: str               # Nội dung JD gốc
    lock: threading.Lock       # Thread-safe access
```

> **Tối ưu hoá:** JD chỉ được embed **1 lần** và được cache lại trong RAM. Mọi CV scan trong cùng phiên sẽ tái dụng embedding này, tránh gọi Ollama lặp lại.

### 3.3 Pipeline Xử lý CV

```
PDF File (bytes)
     │
     ▼
┌─────────────────────────────┐
│  read_pdf()                 │  PyMuPDF trích xuất text
│  └─ Nếu thất bại:           │
│     read_pdf_with_ollama_ocr│  Vision model OCR (optional)
└────────────┬────────────────┘
             │ cv_text (str)
             ▼
┌─────────────────────────────┐
│  prepare_text_for_embedding │  Chuẩn hoá + trích xuất skills
│  build_embedding_input()    │  → "Lĩnh vực: X. Kỹ năng: A, B, C"
└────────────┬────────────────┘
             │ embedding_text (str, max 800 chars)
             ▼
┌─────────────────────────────┐
│  get_text_embedding()       │  Gọi Ollama API (local)
│  ollama.embed(model, input) │  → list[float] vector
└────────────┬────────────────┘
             │ cv_embedding
             ▼
┌─────────────────────────────┐
│  calculate_cosine_similarity│  NumPy dot product / norm
│  similarity_to_percentage() │  → score 0–100%
└────────────┬────────────────┘
             │ semantic_score
             ▼
┌─────────────────────────────┐
│  Hybrid Scoring Formula     │
│  • Skill Kill Switch check  │  Nếu CV không có 1 skill JD nào → 0
│  • match_score =            │
│    semantic * 0.6 +         │
│    keyword_match * 0.4      │
└────────────┬────────────────┘
             │ match_score (0–100)
             ▼
┌─────────────────────────────┐
│  get_decision()             │  PASS ≥ 70 / PENDING ≥ 50 / FAIL
│  build_vietnamese_analysis()│  Điểm mạnh, điểm yếu, nhận xét
│  build_score_breakdown()    │  Chi tiết từng mục chấm điểm
└────────────┬────────────────┘
             │ JSON result
             ▼
         API Response
```

### 3.4 Scoring Model

Điểm tổng hợp được tính theo công thức **Hybrid**:

| Thành phần | Trọng số | Mô tả |
|---|---|---|
| Semantic Similarity | 60% | Cosine similarity giữa vector CV và JD |
| Keyword Match | 40% | Tỉ lệ kỹ năng JD xuất hiện trong CV |
| **Kill Switch** | Ghi đè = 0 | Nếu CV không có **bất kỳ** kỹ năng bắt buộc nào |

**Ngưỡng quyết định:**

| Điểm | Kết quả |
|---|---|
| ≥ 70 | ✅ ĐẠT (PASS) |
| 50 – 69 | ⏳ CHỜ XEM XÉT (PENDING) |
| < 50 | ❌ KHÔNG ĐẠT (FAIL) |

### 3.5 Embedding & AI

- **Model:** Ollama chạy cục bộ (mặc định: `qwen2.5:3b`)
- **Fallback chain:** Hỗ trợ danh sách model qua env `OLLAMA_EMBEDDING_MODELS`, tự động thử model tiếp theo nếu model hiện tại lỗi
- **OCR:** Nếu PDF là scan (không có text), có thể bật `OLLAMA_OCR_MODEL` để dùng vision model đọc ảnh

### 3.6 Gmail Integration (`gmail_service.py`)

```
scan_gmail_attachments()
     │
     ├─ 1. Kết nối Gmail API (OAuth2)
     ├─ 2. Tìm email theo query + has:attachment filename:pdf
     ├─ 3. [Sequential] Tải từng file đính kèm (tránh lỗi Google API thread-safety)
     └─ 4. [Parallel - 2 workers] Xử lý PDF + Embedding song song
```

**OAuth2 Flow:**
1. Lần đầu: `auth.py` mở browser → user chọn Google account → tạo `token.json`
2. Các lần sau: tự động refresh token từ `token.json`

---

## 4. Frontend Architecture

### 4.1 Cấu trúc file

```
frontend/
├── src/
│   ├── App.jsx          # Component chính (toàn bộ UI logic)
│   ├── main.jsx         # React entry point
│   ├── index.css        # Global styles
│   └── App.css          # App-level styles
├── index.html           # HTML shell
├── vite.config.js       # Vite build config
└── package.json         # Dependencies
```

### 4.2 Component Tree

```
App
├── <header>            # TopBar: Logo + Avatar
├── <aside>             # Sidebar: JD Input + Scan Button
│   └── <textarea>      # Job Description input
└── <main>              # Khu vực nội dung chính
    ├── Tab: "Tải từ máy tính"
    │   ├── Drop Zone    # Drag & drop PDF upload
    │   └── File List    # Trạng thái từng file (idle/scanning/done/error)
    ├── Tab: "Quét từ Gmail"
    │   ├── Query Input  # Gmail search query
    │   ├── Time Filter  # 24h / 7d / 1m / all
    │   └── Connect Btn  # Trigger scan
    └── Results Table    # Bảng ứng viên với sort, status, actions
        └── ResultDrawer # Slide-in modal chi tiết CV (AI analysis)
```

### 4.3 State Management

Toàn bộ state được quản lý bằng **React hooks** (`useState`, `useMemo`, `useRef`) — không dùng Redux hay Context API.

| State | Type | Mô tả |
|---|---|---|
| `jdText` | `string` | Nội dung JD người dùng nhập |
| `activeTab` | `'local' \| 'gmail'` | Tab đang active |
| `files` | `FileState[]` | Danh sách CV đang xử lý |
| `results` | `Result[]` | Kết quả tất cả CV đã quét |
| `sortOrder` | `'asc' \| 'desc'` | Thứ tự sắp xếp bảng |
| `selectedResult` | `Result \| null` | CV đang xem chi tiết (drawer) |
| `gmailScanning` | `boolean` | Loading state khi quét Gmail |

### 4.4 API Communication

Frontend tự động phát hiện môi trường để chọn Base URL:

```javascript
const BASE_URL =
  (hostname === 'localhost' || hostname === '127.0.0.1')
    ? 'http://127.0.0.1:8000'          // Local development
    : (import.meta.env.VITE_API_URL    // Production (Render.com)
       || 'http://127.0.0.1:8000');
```

---

## 5. Data Flow

### 5.1 Luồng quét CV từ máy tính

```
User chọn PDF → [Frontend] setFiles(idle)
     → Click "Bắt đầu quét CV"
     → POST /api/scan-local-cv (multipart/form-data: jd_text + file)
     → [Backend] read_pdf() → get_text_embedding() → cosine_similarity()
     → JSON response { status, match_score, data }
     → [Frontend] setResults([...prev, resultData])
     → Hiển thị trong bảng kết quả
```

### 5.2 Luồng quét CV từ Gmail

```
User nhập query + chọn time range
     → Click "Kết nối Gmail"
     → POST /api/scan-gmail (multipart/form-data)
     → [Backend] Gmail API → tải PDF attachments
     → ThreadPoolExecutor(2 workers) → process_pipeline()
     → JSON response { status, data: [...] }
     → [Frontend] setResults([...prev, ...data.data])
```

### 5.3 Luồng gửi email phỏng vấn

```
User click "Gửi Mail" (chỉ hiện khi status = PASS/PENDING)
     → POST /api/send-interview-email { email, name }
     → [Backend] send_gmail_message() → Gmail API send
     → Alert: "Đã gửi email thành công"
```

---

## 6. Cấu hình môi trường (Environment Variables)

### Backend (`.env` ở root)

| Biến | Mặc định | Mô tả |
|---|---|---|
| `OLLAMA_EMBEDDING_MODELS` | `qwen2.5:3b` | Model(s) embedding, ngăn cách bằng dấu phẩy |
| `OLLAMA_KEEP_ALIVE` | `10m` | Thời gian giữ model trong RAM |
| `OLLAMA_OCR_MODEL` | _(rỗng)_ | Vision model cho OCR (vd: `llama3.2-vision`) |
| `OCR_MAX_PAGES` | `1` | Số trang tối đa cho OCR |
| `MAX_EMBEDDING_CHARS` | `800` | Độ dài text tối đa trước khi embed |
| `PASS_THRESHOLD` | `70` | Ngưỡng điểm PASS |
| `REVIEW_THRESHOLD` | `50` | Ngưỡng điểm PENDING |
| `HOST` | `0.0.0.0` | Host binding cho uvicorn |
| `PORT` | `8000` | Port binding cho uvicorn |

### Frontend (`frontend/.env`)

| Biến | Mô tả |
|---|---|
| `VITE_API_URL` | URL backend khi deploy production (vd: Render.com) |

---

## 7. Tech Stack Summary

### Backend

| Thư viện | Phiên bản | Mục đích |
|---|---|---|
| `fastapi` | latest | Web framework + API |
| `uvicorn` | latest | ASGI server |
| `PyMuPDF (fitz)` | latest | Đọc/parse file PDF |
| `ollama` | latest | Gọi local LLM để tạo embedding |
| `numpy` | latest | Tính cosine similarity |
| `google-api-python-client` | latest | Gmail API |
| `google-auth-oauthlib` | latest | OAuth2 authentication |
| `python-dotenv` | latest | Đọc file `.env` |
| `pydantic` | latest | Data validation |

### Frontend

| Thư viện | Phiên bản | Mục đích |
|---|---|---|
| `react` | ^18.2 | UI framework |
| `vite` | ^5.2 | Build tool + dev server |
| `tailwindcss` | ^4.0 | Utility-first CSS |
| `lucide-react` | ^0.360 | Icon library |
| `axios` | ^1.6 | HTTP client |
| `framer-motion` | ^11.0 | Animations |

---

## 8. Deployment

### Local Development

```bash
# 1. Khởi động Ollama (cần cài sẵn)
ollama run qwen2.5:3b

# 2. Backend
cd FILTER_CV_AI
pip install -r requirements.txt
python auth.py          # Lần đầu: cấp quyền Gmail
python main.py          # Chạy FastAPI tại :8000

# 3. Frontend
cd frontend
npm install
npm run dev             # Dev server tại :5173
```

### Production (Render.com)

- Backend deploy dưới dạng **Web Service** chạy `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Frontend build static với `npm run build`, deploy lên **Static Site** hoặc CDN
- Biến môi trường `VITE_API_URL` trỏ về backend URL trên Render

> ⚠️ **Lưu ý:** Ollama phải chạy **cục bộ** hoặc trên server riêng có GPU. Render.com free tier không hỗ trợ Ollama.

---

## 9. Security Considerations

| Vấn đề | Hiện trạng | Khuyến nghị |
|---|---|---|
| CORS | `allow_origins=["*"]` (mở hoàn toàn) | Hạn chế xuống domain cụ thể khi production |
| Gmail credentials | `credentials.json` + `token.json` ở root | Thêm vào `.gitignore`, không commit |
| Secrets | `.env` ở root | Không commit, dùng secrets manager khi deploy |
| PDF parsing | Dùng PyMuPDF (an toàn) | Không có giới hạn file size hiện tại |

---

## 10. Sequence Diagram — Batch Gmail Scan

```
HR          Frontend         Backend          Gmail API        Ollama
 │                │               │                │               │
 │──nhập JD──────►│               │                │               │
 │──click Quét───►│               │                │               │
 │                │──POST scan────►│               │               │
 │                │               │──search emails─►│               │
 │                │               │◄─message list──│               │
 │                │               │──get attachment►│               │
 │                │               │◄─PDF bytes─────│               │
 │                │               │─────[thread 1]─ read_pdf()     │
 │                │               │─────[thread 2]─ read_pdf()     │
 │                │               │──embed JD──────────────────────►│
 │                │               │◄─JD vector─────────────────────│
 │                │               │──embed CV──────────────────────►│
 │                │               │◄─CV vector─────────────────────│
 │                │               │─ cosine_similarity()            │
 │                │               │─ build_score + decision         │
 │                │◄──JSON results─│                │               │
 │◄──bảng kết quả─│               │                │               │
```

## 9. Triển khai hệ thống (Deployment)

### Sơ đồ mô hình triển khai

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                      INTERNET / CLOUD                               │
 │   ┌─────────────────────────────────────────────────────────────┐   │
 │   │  Google Gmail API  —  gmail.googleapis.com  :443 HTTPS      │   │
 │   │  OAuth2 Bearer Token  |  messages.list / get / send         │   │
 │   └─────────────────────────────────────────────────────────────┘   │
 └─────────────────────────────┬───────────────────────────────────────┘
                               │  HTTPS (OAuth2 + PDF binary)
                               ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │                  MAY CHU CUC BO  (Local Server)                    │
 │                                                                    │
 │  ┌───────────────────────────────────────────────────────────────┐ │
 │  │  Process: uvicorn  [0.0.0.0 : 8000]                           │ │
 │  │                                                               │ │
 │  │  ┌─────────────────────────────────────────────────────────┐  │ │
 │  │  │  FastAPI Application  (main.py)                         │  │ │
 │  │  │  POST /api/scan-local-cv   — nhan CV tu may tinh        │  │ │
 │  │  │  POST /api/scan-gmail      — quet hop thu Gmail         │  │ │
 │  │  │  POST /api/send-interview-email — gui email moi PV      │  │ │
 │  │  │  ATSState: jd_embedding cache  |  threading.Lock        │  │ │
 │  │  │  ThreadPoolExecutor (max 2 workers song song)           │  │ │
 │  │  └──────────────────────────┬──────────────────────────────┘  │ │
 │  │                             │  HTTP POST localhost:11434      │ │
 │  │  ┌──────────────────────────▼──────────────────────────────┐  │ │
 │  │  │  Process: ollama serve  [127.0.0.1 : 11434]             │  │ │
 │  │  │  Model  : qwen2.5:3b  (RAM ~2 GB)                       │  │ │
 │  │  │  Output : list[float]  vector 1536 chieu                │  │ │
 │  │  │  Option : llama3.2-vision  (OCR scanned PDF)            │  │ │
 │  │  └─────────────────────────────────────────────────────────┘  │ │
 │  └───────────────────────────────────────────────────────────────┘ │
 │                                                                    │
 │  File System:  .env  |  token.json  |  credentials.json  |  CVs/   │
 └─────────────────────────────┬──────────────────────────────────────┘
                               │  HTTP / REST API  (LAN)
                               │  multipart/form-data + JSON
                               ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │                  MAY TINH HR  (Client Machine)                      │
 │                                                                     │
 │  ┌───────────────────────────────────────────────────────────────┐  │
 │  │  Process: vite dev  [localhost : 5173]                        │  │
 │  │  React 18 SPA  —  App.jsx                                     │  │
 │  │  • Nhap Job Description (JD)                                  │  │
 │  │  • Upload CV (.pdf) hoac quet Gmail                           │  │
 │  │  • Xem bang ket qua + Chi tiet phan tich AI                   │  │
 │  │  • Gui email moi phong van cho ung vien DAT                   │  │
 │  └───────────────────────────────────────────────────────────────┘  │
 └─────────────────────────────────────────────────────────────────────┘
```

### Giải thích các luồng giao tiếp

| Luồng | Giao thức | Mô tả |
|---|---|---|
| Browser → Backend | HTTP/REST (LAN) | Upload CV, trigger scan, gửi email |
| Backend → Ollama | HTTP (localhost) | Tạo vector embedding từ text |
| Backend → Gmail | HTTPS (Internet) | Tải PDF đính kèm, gửi email PV |
| Backend → Storage | File I/O (local) | Đọc token OAuth2, credentials |
---

## 10. Kiến trúc mức quan niệm (Conceptual Architecture)

> Mức quan niệm mô tả **hệ thống làm gì** — tập trung vào các thực thể nghiệp vụ, vai trò và mối quan hệ logic giữa chúng, **không** đề cập đến công nghệ hay cơ sở hạ tầng cụ thể.

### Sơ đồ

```
                       ┌─────────────────────────────┐
                       │   HR / Nha tuyen dung       │  Tac nhan khoi dong quy trinh
                       └──────────┬──────────────────┘
                                  │  nhap JD + chon nguon CV
                                  ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │                         NGUON CV                                   │
 │  ┌──────────────────────────┐   ┌──────────────────────────────┐   │
 │  │  CV Cuc bo               │   │  Hop thu Gmail               │   │
 │  │  Upload file .pdf        │   │  Email dinh kem .pdf         │   │
 │  └─────────────┬────────────┘   └────────────────┬─────────────┘   │
 └────────────────┼────────────────────────────────┼──────────────────┘
                  └──────────────┬─────────────────┘
                                 │  noi dung van ban tho
                                 ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │                    LOI SANG LOC AI                                   │
 │                                                                      │
 │  ┌───────────────────────────────┐                                   │
 │  │  Trich xuat thong tin CV      │  extract_skills()                 │
 │  │  Ten · Email · Ky nang        │  extract_candidate_name()         │
 │  └──────────────┬────────────────┘                                   │
 │                 │ CV text                                            │
 │                 └─────────|                                          │
 │                           │  JD + CV text                            │
 │                           ▼                                          │
 │  ┌───────────────────────────────┐                                   │
 │  │  Bieu dien Ngu nghia          │  ollama.embed()                   │
 │  │  (Vector Embedding)           │  → list[float] 1536 chieu         │
 │  └──────────────┬────────────────┘                                   │
 │                 │  vector JD + vector CV                             │
 │                 ▼                                                    │
 │  ┌───────────────────────────────┐                                   │
 │  │  Danh gia Do phu hop          │  Cosine Similarity x 0.6          │
 │  │  Hybrid Scoring               │  + Keyword Match x 0.4            │
 │  │                               │  Kill Switch neu 0 skill khop     │
 │  └──────────────┬────────────────┘                                   │
 │                 │  diem 0-100                                        │
 │                 ▼                                                    │
 │  ┌───────────────────────────────┐                                   │
 │  │  Ra Quyet dinh                │  >= 70  → DAT                     │
 │  │  get_decision()               │  50-69  → CHO XEM XET             │
 │  │                               │  < 50   → KHONG DAT               │
 │  └──────┬───────────┬────────────┘                                   │
 └─────────┼───────────┼────────────────────────────────────────────────┘
           │           │
           ▼           ▼
 ┌──────────────┐  ┌──────────────────────────────────────────────────┐
 │ Bang xep     │  │  Phan tich chi tiet AI                           │
 │ hang ung     │  │  Diem manh · Diem yeu · Ky nang · Linh vuc       │
 │ vien (HR)    │  │  Gui email moi phong van (neu DAT)               │
 └──────────────┘  └──────────────────────────────────────────────────┘
```

### Mô tả các thực thể nghiệp vụ

| Thực thể | Vai trò | Đầu vào | Đầu ra |
|---|---|---|---|
| **HR / Nhà tuyển dụng** | Tác nhân chính, điều phối toàn bộ quy trình | — | JD, lệnh quét, xác nhận gửi email |
| **Mô tả Công việc (JD)** | Tiêu chuẩn đánh giá, định nghĩa yêu cầu vị trí | Văn bản từ HR | Kỹ năng bắt buộc, ngữ nghĩa nghề |
| **Nguồn CV** | Kênh thu thập hồ sơ (Cục bộ hoặc Gmail) | File PDF | Nội dung văn bản thô |
| **Trích xuất thông tin** | Bóc tách dữ liệu có cấu trúc từ CV | Văn bản thô | Tên, email, danh sách kỹ năng |
| **Biểu diễn ngữ nghĩa** | Mã hoá ý nghĩa văn bản thành vector số | Văn bản JD & CV | Vector không gian chiều cao |
| **Scoring Engine** | Tính điểm tổng hợp theo công thức Hybrid | Hai vector + kỹ năng | Điểm 0–100 |
| **Ra quyết định** | Phân loại ứng viên theo ngưỡng | Điểm tổng hợp | ĐẠT / CHỜ XEM XÉT / KHÔNG ĐẠT |
| **Bảng xếp hạng** | Trình bày kết quả, có thể sắp xếp | Danh sách kết quả | Giao diện bảng cho HR |
| **Phân tích chi tiết** | Giải thích quyết định AI bằng ngôn ngữ tự nhiên | Kết quả CV | Điểm mạnh, điểm yếu, kỹ năng |
| **Thông báo** | Gửi email mời phỏng vấn tự động | Ứng viên ĐẠT | Email đến ứng viên |

> **Quy tắc nghiệp vụ quan trọng:**
> - CV không có **bất kỳ kỹ năng bắt buộc nào** từ JD → điểm tự động bằng **0** (Kill Switch).
> - Nút "Gửi Mail" chỉ xuất hiện với ứng viên **ĐẠT** hoặc **CHỜ XEM XÉT**.
> - JD Embedding chỉ được tính **một lần** và tái sử dụng cho toàn bộ batch CV cùng phiên.

---

## 11. Kiến trúc mức vật lý (Physical Architecture)

> Mức vật lý mô tả **hệ thống chạy như thế nào và ở đâu** — tập trung vào phần cứng, tiến trình OS, cổng mạng, giao thức truyền tải và cách các thành phần được triển khai thực tế.

### Sơ đồ

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                  MAY TINH HR  (Client Machine)                      │
 │                                                                     │
 │  ┌───────────────────────────────────────────────────────────────┐  │
 │  │  Process: vite dev  [localhost:5173]                          │  │
 │  │  React 18 SPA  —  App.jsx                                     │  │
 │  │  ─────────────────────────────────────────────────────────    │  │
 │  │  useState: jdText · files · results · selectedResult          │  │
 │  │  Tabs: Upload CV (Local)  |  Quet Gmail                       │  │
 │  │  Components: Sidebar · DropZone · Table · ResultDrawer        │  │
 │  └───────────────────────────────────────────────────────────────┘  │
 └──────────────────────────────┬──────────────────────────────────────┘
                                │
         ┌──────────────────────┼────────────────────────┐
         │                      │                        │
 POST /api/scan-local-cv  POST /api/scan-gmail  POST /api/send-interview-email
  multipart/form-data      multipart/form-data    application/json
  (jd_text + file.pdf)     (jd_text + query)      (email + name)
         │                      │                        │
         └──────────────────────┼────────────────────────┘
                                │
                                ▼  JSON response (match_score, decision, analysis)
 ┌────────────────────────────────────────────────────────────────────┐
 │                  MAY CHU CUC BO  (Local Server)                    │
 │                                                                    │
 │  ┌───────────────────────────────────────────────────────────────┐ │
 │  │  Process: uvicorn  [0.0.0.0:8000]                             │ │
 │  │                                                               │ │
 │  │  ┌─────────────────────────────────────────────────────────┐  │ │
 │  │  │  FastAPI app  (main.py)                                 │  │ │
 │  │  │  ATSState: jd_embedding (cache) · lock: threading.Lock  │  │ │
 │  │  │  ┌───────────────────────────────────────────────────┐  │  │ │
 │  │  │  │  ThreadPoolExecutor  (max_workers=2)              │  │  │ │
 │  │  │  │  Worker-1: fitz.open() → text → ollama.embed()    │  │  │ │
 │  │  │  │  Worker-2: fitz.open() → text → ollama.embed()    │  │  │ │
 │  │  │  └───────────────────────────────────────────────────┘  │  │ │
 │  │  └────────────────────────┬────────────────────────────────┘  │ │
 │  │                           │  HTTP POST localhost:11434        │ │
 │  │  ┌────────────────────────▼────────────────────────────────┐  │ │
 │  │  │  Process: ollama serve  [127.0.0.1:11434]               │  │ │
 │  │  │  Model : qwen2.5:3b  RAM ~2 GB                          │  │ │
 │  │  │  Output: list[float]  1536 chieu                        │  │ │
 │  │  │  Option: llama3.2-vision  (OCR scanned PDF)             │  │ │
 │  │  └─────────────────────────────────────────────────────────┘  │ │
 │  └───────────────────────────────────────────────────────────────┘ │
 │                                                                    │
 │  File System (project root):                                       │
 │  .env          PASS_THRESHOLD=70 · REVIEW_THRESHOLD=50             │
 │  token.json    OAuth2 access_token + refresh_token (auto-refresh)  │
 │  credentials.json  Google client_id + client_secret                │
 │  validate_cvs/     *.pdf  (test data)                              │
 └──────────────────────────────┬─────────────────────────────────────┘
                                │  HTTPS:443  (Bearer Token)
                                ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │                  GOOGLE CLOUD INFRASTRUCTURE                        │
 │                                                                     │
 │  ┌───────────────────────────────────────────────────────────────┐  │
 │  │  Gmail API  [gmail.googleapis.com:443]                        │  │
 │  │  users.messages.list       → tim email co PDF dinh kem        │  │
 │  │  users.messages.get        → doc metadata email               │  │
 │  │  messages.attachments.get  → tai file PDF (base64)            │  │
 │  │  users.messages.send       → gui email moi phong van          │  │
 │  └───────────────────────────────────────────────────────────────┘  │
 └─────────────────────────────────────────────────────────────────────┘
```

### Mô tả các thành phần vật lý

#### Máy chủ cục bộ (Server Machine)

| Thành phần | Loại | Địa chỉ mạng | Chi tiết kỹ thuật |
|---|---|---|---|
| **uvicorn** | OS Process | `0.0.0.0:8000` | ASGI server, reload mode khi dev |
| **FastAPI app** | Python runtime | — | Xử lý request đồng thời với async/await |
| **ATSState** | In-memory object | — | Cache JD embedding, thread-safe bằng `Lock` |
| **ThreadPoolExecutor** | Thread pool | — | 2 workers song song xử lý PDF + Ollama |
| **ollama serve** | OS Process | `127.0.0.1:11434` | HTTP server phục vụ local model |
| **qwen2.5:3b** | Loaded LLM | — | ~2 GB RAM, tạo embedding 1536 chiều |
| **llama3.2-vision** | Optional LLM | — | Vision model OCR scanned PDF |
| `.env` | Config file | project root | Ngưỡng điểm, tên model, giới hạn ký tự |
| `token.json` | Auth file | project root | OAuth2 token, tự refresh khi hết hạn |
| `credentials.json` | Secret file | project root | Google client ID/secret — **KHÔNG commit** |

#### Máy tính HR (Client Machine)

| Thành phần | Loại | Địa chỉ mạng | Chi tiết kỹ thuật |
|---|---|---|---|
| **vite dev** | OS Process | `localhost:5173` | Dev server HMR, build tool |
| **React SPA** | Browser runtime | — | Single Page App, không reload trang |
| **useState hooks** | Browser memory | — | Toàn bộ state sống trong RAM của browser tab |

#### Kết nối mạng & Giao thức

| Kết nối | Giao thức | Endpoint | Payload |
|---|---|---|---|
| SPA → Backend (CV local) | HTTP LAN | `POST :8000/api/scan-local-cv` | `multipart/form-data` — JD text + PDF binary |
| SPA → Backend (Gmail) | HTTP LAN | `POST :8000/api/scan-gmail` | `multipart/form-data` — JD + query + time_range |
| SPA → Backend (Email) | HTTP LAN | `POST :8000/api/send-interview-email` | `application/json` — {email, name} |
| Backend ← SPA | HTTP LAN | Response 200 | `application/json` — full result object |
| Backend → Ollama | HTTP localhost | `POST :11434/api/embed` | JSON — {model, input: string} |
| Ollama → Backend | HTTP localhost | Response 200 | JSON — {embeddings: \[\[float\]\]} |
| Backend → Gmail API | HTTPS Internet | REST `googleapis.com` | Bearer Token + JSON body |
| Gmail API → Backend | HTTPS Internet | Response 200 | PDF base64 + message metadata |

---

## 12. Cơ sở dữ liệu (Database Layer)

### 12.1 Tổng quan

Hệ thống sử dụng **SQLite** thông qua **SQLAlchemy 2.x (sync)** để lưu trữ lâu dài dữ liệu Job Description — cho phép HR tái sử dụng JD giữa các phiên làm việc mà không cần nhập lại.

| Thuộc tính | Giá trị |
|---|---|
| **Engine** | SQLite 3 |
| **ORM** | SQLAlchemy 2.0 (sync / `create_engine`) |
| **File vật lý** | `ats_data.db` (project root) |
| **Khởi tạo** | Tự động khi FastAPI startup (`init_db()`) |
| **Thread safety** | WAL journal mode (`PRAGMA journal_mode=WAL`) |
| **Thư viện** | `sqlalchemy`, `greenlet` |

---

### 12.2 Sơ đồ lưu trữ

```
 Project Root  /
 ├── ats_data.db          ← SQLite database file (tự tạo khi chạy lần đầu)
 ├── database.py          ← SQLAlchemy engine, models, helpers
 ├── token.json           ← OAuth2 token Gmail (auto-refresh)
 ├── credentials.json     ← Google client ID/secret
 └── .env                 ← Cấu hình ngưỡng điểm, tên model
```

---

### 12.3 Schema bảng `job_descriptions`

```sql
CREATE TABLE job_descriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       VARCHAR(255) NOT NULL,       -- Tên vị trí tuyển dụng
    jd_text     TEXT        NOT NULL,        -- Nội dung JD đầy đủ
    jd_hash     VARCHAR(32) NOT NULL UNIQUE, -- MD5(jd_text) — phát hiện trùng lặp
    created_at  DATETIME    DEFAULT (CURRENT_TIMESTAMP),
    updated_at  DATETIME    DEFAULT (CURRENT_TIMESTAMP),
    total_scans INTEGER     DEFAULT 0        -- Số lần JD này đã được dùng để quét CV
);
```

#### Mô tả từng cột

| Cột | Kiểu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | `INTEGER` | PK, AUTOINCREMENT | Khoá chính tự tăng |
| `title` | `VARCHAR(255)` | NOT NULL | Tên vị trí tuyển dụng (do HR nhập) |
| `jd_text` | `TEXT` | NOT NULL | Toàn văn mô tả công việc |
| `jd_hash` | `VARCHAR(32)` | NOT NULL, UNIQUE | MD5 của `jd_text` — ngăn lưu trùng nội dung |
| `created_at` | `DATETIME` | DEFAULT now | Thời điểm tạo bản ghi |
| `updated_at` | `DATETIME` | DEFAULT now | Thời điểm cập nhật gần nhất |
| `total_scans` | `INTEGER` | DEFAULT 0 | Bộ đếm số lần JD được dùng để quét CV |

---

### 12.4 API CRUD endpoints

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/jobs` | Lấy toàn bộ JD, sắp xếp theo `updated_at` giảm dần |
| `POST` | `/api/jobs` | Lưu JD mới; nếu `jd_hash` đã tồn tại → cập nhật `title` |
| `PUT` | `/api/jobs/{id}` | Cập nhật `title` và/hoặc `jd_text` của một JD |
| `DELETE` | `/api/jobs/{id}` | Xoá JD khỏi database |
| `POST` | `/api/jobs/{id}/increment-scan` | Tăng `total_scans` +1 mỗi khi JD được dùng để quét |

#### Ví dụ Request / Response

```jsonc
// POST /api/jobs
// Request body
{
  "title": "Senior Backend Engineer",
  "jd_text": "Chúng tôi tìm kiếm kỹ sư Python 3+ năm kinh nghiệm..."
}

// Response (201 Created)
{
  "status": "created",
  "message": "Đã lưu JD thành công.",
  "data": { "id": 1, "title": "Senior Backend Engineer" }
}
```

```jsonc
// GET /api/jobs
// Response (200 OK)
{
  "status": "success",
  "data": [
    {
      "id": 1,
      "title": "Senior Backend Engineer",
      "jd_text": "Chúng tôi tìm kiếm...",
      "created_at": "2026-05-03T05:18:00",
      "updated_at": "2026-05-03T10:45:00",
      "total_scans": 12
    }
  ]
}
```

---

### 12.5 Luồng xử lý Duplicate Detection

```
 HR nhập JD text
       │
       ▼
 compute_jd_hash(jd_text)      MD5(jd_text.strip()) → 32 ký tự hex
       │
       ▼
 Query: SELECT * FROM job_descriptions WHERE jd_hash = ?
       │
       ├── Tìm thấy ──► Cập nhật title + updated_at  (status: "updated")
       │
       └── Không có ──► INSERT bản ghi mới            (status: "created")
```

> **Lý do dùng MD5 thay vì so sánh text:** MD5 tạo index UNIQUE nhỏ gọn (32 bytes), truy vấn O(1) dù JD text dài hàng nghìn ký tự.

---

### 12.6 Cấu hình WAL Mode

```python
# database.py
@event.listens_for(engine, "connect")
def set_wal_mode(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
```

**WAL (Write-Ahead Logging)** cho phép đọc và ghi đồng thời mà không block lẫn nhau — cần thiết vì FastAPI + ThreadPoolExecutor có thể tạo nhiều DB session song song.

---

### 12.7 Luồng tích hợp với Frontend

```
 Sidebar (React)
       │
       ├── [Lưu JD]  ──► POST /api/jobs  ──► INSERT / UPDATE SQLite
       │
       ├── [JD đã lưu]  ──► GET /api/jobs  ──► SELECT * SQLite
       │                         │
       │                    Render danh sách
       │                    Click → loadJd(jd)
       │                    → setJdText(jd.jd_text)   (nạp vào textarea)
       │
       └── [Xoá]  ──► DELETE /api/jobs/{id}  ──► DELETE SQLite
```

---

### 12.8 Kế hoạch mở rộng (Future)

| Bảng tương lai | Lưu gì | Lợi ích |
|---|---|---|
| `scan_sessions` | Mỗi lần bấm "Quét" = 1 session, liên kết với `job_descriptions.id` | Gom nhóm kết quả theo đợt tuyển dụng |
| `candidates` | Kết quả phân tích từng CV (score, decision, strengths…) | Lưu lịch sử, không mất khi F5 |
| `email_log` | Lịch sử gửi email mời PV (to, sent_at, status) | Tránh gửi trùng, audit trail |
| `settings` | PASS_THRESHOLD, REVIEW_THRESHOLD, OLLAMA_MODEL | Chỉnh qua UI thay vì sửa `.env` |

---

### 12.9 Chi tiết Kỹ thuật Kết nối (Technical Implementation)

Hệ thống áp dụng các kỹ thuật quản trị kết nối chuyên sâu để đảm bảo tính ổn định trong môi trường đa luồng:

#### A. Kỹ thuật quản lý phiên (Session Lifecycle)
Hệ thống sử dụng mẫu thiết kế **Dependency Injection** kết hợp với **Generator** để quản lý vòng đời của kết nối database:
- **`SessionLocal`**: Một factory được cấu hình `autocommit=False`. Điều này bắt buộc hệ thống phải sử dụng giao dịch (transaction) tường minh, giúp đảm bảo tính toàn vẹn dữ liệu.
- **`get_db()` pattern**: Mỗi request từ Frontend sẽ mở một session riêng và đảm bảo đóng lại (`db.close()`) ngay cả khi có ngoại lệ xảy ra, tránh rò rỉ kết nối (connection leaks).

#### B. Tối ưu hóa đa luồng (Concurrency Tuning)
Do FastAPI xử lý đồng thời nhiều worker threads, database được cấu hình:
1.  **`check_same_thread=False`**: Vô hiệu hóa hạn chế mặc định của SQLite, cho phép các luồng xử lý CV khác nhau truy cập chung vào một pool kết nối.
2.  **WAL Mode (Write-Ahead Logging)**: 
    - Triển khai qua SQLAlchemy Event Listener (`connect` event).
    - Cho phép cơ chế **"Một người ghi - Nhiều người đọc"**. HR có thể vừa xem danh sách JD cũ (Read) trong khi hệ thống đang cập nhật bộ đếm quét (`total_scans`) cho một JD khác (Write).

#### C. Khởi tạo hạ tầng (Automatic Initialization)
Sử dụng sự kiện `@app.on_event("startup")` của FastAPI để thực thi `Base.metadata.create_all()`. Kỹ thuật này giúp hệ thống có khả năng **"Self-healing"** — tự động tái tạo cấu trúc file database nếu bị xóa nhầm, giảm thiểu công sức vận hành cho HR.

#### D. Hiệu năng truy vấn Duplicate
Việc sử dụng **MD5 Hashing** (`jd_hash`) cho phép hệ thống thực hiện so khớp văn bản JD ở độ phức tạp **O(1)**. Thay vì so sánh chuỗi (String Comparison) tốn kém tài nguyên, database chỉ cần so sánh 32 ký tự định danh duy nhất.
