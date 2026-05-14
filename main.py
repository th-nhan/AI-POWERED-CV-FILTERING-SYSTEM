import base64
import hashlib
import os
import re
import threading
from typing import Optional, Sequence

import fitz  # PyMuPDF
import numpy as np
import ollama # Dòng 10 — Import thư viện Ollama Python SDK
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from gmail_service import scan_gmail_attachments, send_gmail_message
from database import (
    init_db,
    upsert_job_description,
    list_job_descriptions,
    get_job_description,
    delete_job_description,
)


load_dotenv()
# Dòng 28–32 — Khai báo danh sách model từ biến môi trường .env
OLLAMA_EMBEDDING_MODELS = [
    model.strip()
    for model in os.getenv("OLLAMA_EMBEDDING_MODELS", "qwen2.5:3b").split(",")
    if model.strip()
]
# Dòng 33 — Thời gian giữ model trong RAM sau lần gọi cuối
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
# Dòng 34 — Model OCR (tùy chọn, dùng llama3.2-vision)
OLLAMA_OCR_MODEL = os.getenv("OLLAMA_OCR_MODEL", "").strip()

OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "1"))
# Dòng 36 — Giới hạn ký tự gửi vào model (kiểm soát chi phí RAM)
MAX_EMBEDDING_CHARS = int(os.getenv("MAX_EMBEDDING_CHARS", "800"))
PASS_THRESHOLD = float(os.getenv("PASS_THRESHOLD", "70"))
REVIEW_THRESHOLD = float(os.getenv("REVIEW_THRESHOLD", "50"))

EMAIL_REGEX = re.compile(
    r"(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.+-])"
)

TECH_SKILL_ALIASES = [
    ("Python", ["python"]),
    ("FastAPI", ["fastapi", "fast api"]),
    ("Django", ["django"]),
    ("Flask", ["flask"]),
    ("REST API", ["rest api", "restful api", "rest"]),
    ("SQL", ["sql"]),
    ("PostgreSQL", ["postgresql", "postgres"]),
    ("MySQL", ["mysql"]),
    ("MongoDB", ["mongodb", "mongo db"]),
    ("Redis", ["redis"]),
    ("Docker", ["docker"]),
    ("Kubernetes", ["kubernetes", "k8s"]),
    ("Git", ["git", "github", "gitlab"]),
    ("Linux", ["linux", "ubuntu"]),
    ("AWS", ["aws", "amazon web services"]),
    ("Azure", ["azure"]),
    ("GCP", ["gcp", "google cloud"]),
    ("JavaScript", ["javascript", "js"]),
    ("TypeScript", ["typescript", "ts"]),
    ("React Native", ["react native"]),
    ("Flutter", ["flutter"]),
    ("HTML", ["html", "html5"]),
    ("CSS", ["css", "css3"]),
    ("React", ["react", "reactjs", "react.js"]),
    ("Next.js", ["nextjs", "next.js"]),
    ("Vue", ["vue", "vuejs", "vue.js"]),
    ("Angular", ["angular"]),
    ("Node.js", ["nodejs", "node.js", "node js"]),
    ("Express", ["express", "expressjs"]),
    ("Java", ["java"]),
    ("Spring Boot", ["spring boot", "springboot"]),
    ("C#", ["c#"]),
    (".NET", [".net", "asp.net"]),
    ("PHP", ["php"]),
    ("Laravel", ["laravel"]),
    ("NLP", ["nlp", "natural language processing"]),
    ("Computer Vision", ["computer vision", "opencv"]),
    ("TensorFlow", ["tensorflow"]),
    ("PyTorch", ["pytorch", "torch"]),
    ("Pandas", ["pandas"]),
    ("NumPy", ["numpy"]),
    ("Scikit-learn", ["scikit-learn", "sklearn"]),
    ("Power BI", ["power bi", "powerbi"]),
    ("Excel", ["excel"]),
    ("CI/CD", ["ci/cd", "cicd", "github actions", "jenkins"]),
    ("Testing", ["testing", "unit test", "pytest", "jest"]),
    ("Microservices", ["microservices", "microservice"]),
    ("Agile/Scrum", ["agile", "scrum"]),
]

app = FastAPI(title="ATS Semantic Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    """Initialise SQLite schema once when the server starts."""
    init_db()


class ATSState:
    def __init__(self):
        self.current_jd_hash: Optional[str] = None
        self.jd_embedding: Optional[list[float]] = None
        self.jd_text: str = ""
        self.lock = threading.Lock()


global_ats_state = ATSState()
_active_embedding_model = None
_embedding_model_lock = threading.Lock()


class EmbeddingServiceError(RuntimeError):
    pass


def is_ollama_model_unavailable_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "not found" in message
        or "try pulling it first" in message
        or "status code: 404" in message
    )


def get_embedding_model_candidates() -> list[str]:
    if _active_embedding_model:
        return [_active_embedding_model]

    return OLLAMA_EMBEDDING_MODELS or ["qwen2.5:3b"]


def remember_active_embedding_model(model_name: str) -> None:
    global _active_embedding_model

    with _embedding_model_lock:
        _active_embedding_model = model_name


def extract_embedding_vector(response) -> list[float]:
    vector = None

    embeddings = getattr(response, "embeddings", None)
    if embeddings:
        vector = embeddings[0]

    if vector is None:
        embedding = getattr(response, "embedding", None)
        if embedding:
            vector = embedding

    if vector is None and isinstance(response, dict):
        if response.get("embeddings"):
            vector = response["embeddings"][0]
        elif response.get("embedding"):
            vector = response["embedding"]

    if vector is None or len(vector) == 0:
        raise RuntimeError("Ollama returned an empty embedding vector.")

    return [float(value) for value in vector]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_search_text(text: str) -> str:
    return f" {re.sub(r'[^a-z0-9+#./]+', ' ', (text or '').lower())} "


def contains_alias(search_text: str, alias: str) -> bool:
    alias_text = re.escape(alias.lower())
    if re.fullmatch(r"[a-z0-9]+", alias.lower()):
        return bool(re.search(rf"(?<![a-z0-9]){alias_text}(?![a-z0-9])", search_text))
    return alias.lower() in search_text


def extract_skills(text: str) -> list[str]:
    search_text = normalize_search_text(text)
    found = []

    flat_aliases = []
    for skill, aliases in TECH_SKILL_ALIASES:
        for alias in aliases:
            flat_aliases.append((skill, alias.lower()))
    
    flat_aliases.sort(key=lambda x: len(x[1]), reverse=True)

    for skill, alias in flat_aliases:
        alias_esc = re.escape(alias)
        if re.fullmatch(r"[a-z0-9 ]+", alias):
            pattern = rf"(?<![a-z0-9]){alias_esc}(?![a-z0-9])"
        else:
            pattern = alias_esc
            
        if re.search(pattern, search_text):
            if skill not in found:
                found.append(skill)
            search_text = re.sub(pattern, " ", search_text)

    ordered_found = []
    for skill, _ in TECH_SKILL_ALIASES:
        if skill in found:
            ordered_found.append(skill)
            
    return ordered_found


def infer_domain(skills: Sequence[str], text: str) -> str:
    skill_set = set(skills)
    search_text = normalize_search_text(text)

    if skill_set & {"Machine Learning", "Deep Learning", "NLP", "Computer Vision", "TensorFlow", "PyTorch", "Scikit-learn"}:
        return "AI / Machine Learning"
    if skill_set & {"Data Analysis", "Pandas", "NumPy", "Power BI", "Excel"}:
        return "Phân tích dữ liệu"
    if skill_set & {"React", "Next.js", "Vue", "Angular", "JavaScript", "TypeScript"}:
        return "Frontend / Web"
    if skill_set & {"Python", "FastAPI", "Django", "Flask", "Node.js", "Express", "Java", "Spring Boot", "C#", ".NET", "PHP", "Laravel"}:
        return "Backend / API"
    if skill_set & {"Docker", "Kubernetes", "AWS", "Azure", "GCP", "CI/CD", "Linux"}:
        return "DevOps / Cloud"
    if "mobile" in search_text or "android" in search_text or "ios" in search_text:
        return "Mobile"

    return "Chưa xác định rõ"


def take_items(items: Sequence[str], limit: int = 6) -> list[str]:
    return list(items[:limit])


def extract_role_from_text(text: str) -> Optional[str]:
    role_keywords = [
        "developer", "engineer", "designer", "analyst", "scientist",
        "administrator", "consultant", "specialist", "kỹ sư", "lập trình",
        "chuyên viên", "quản lý", "tester", "qa", "qc",
        "data", "frontend", "backend", "fullstack", "devops", "marketing",
        "sales", "nhân sự", "hr", "accountant", "kế toán", "business analyst",
        "giám đốc", "trưởng phòng", "phó phòng", "trưởng nhóm"
    ]
    
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for line in lines[:15]:
        clean_line = re.sub(r"\s+", " ", line).strip(" -_|[]()")
        lower_line = clean_line.lower()
        
        if len(clean_line) > 50 or len(clean_line) < 3:
            continue
            
        if EMAIL_REGEX.search(clean_line) or sum(c.isdigit() for c in clean_line) >= 4:
            continue
            
        if any(kw in lower_line for kw in role_keywords):
            if len(clean_line.split()) <= 8:
                if any(bad in lower_line for bad in ["experience", "kinh nghiệm", "kỹ năng", "skill", "education", "học vấn", "certificate", "chứng chỉ", "objective", "mục tiêu"]):
                    continue
                
                result_role = clean_line
                levels_to_remove = [
                    "intern", "fresher", "junior", "senior", "lead", 
                    "mid-level", "mid level", "middle", "mid", "thực tập sinh", "thực tập"
                ]
                for lvl in levels_to_remove:
                    result_role = re.sub(rf"(?i)\b{lvl}\b", "", result_role)
                
                result_role = re.sub(r"\s+", " ", result_role).strip(" -_,|")
                return result_role.title() if result_role else clean_line.title()
                
    return None


def build_embedding_input(text: str) -> str:
    clean_text = normalize_text(text)
    skills = extract_skills(clean_text)

    if skills:
        domain = extract_role_from_text(text) or infer_domain(skills, clean_text)
        return normalize_text(f"Lĩnh vực: {domain}. Kỹ năng: {', '.join(skills)}.")

    return clean_text[:MAX_EMBEDDING_CHARS]


def extract_skill_requirements(text: str) -> list[list[str]]:
    groups = []
    or_keywords = ["1 trong", "biết 1", "hoặc", " or ", "one of", "1 stack", "ít nhất 1", "at least 1", "1 language"]
    
    is_or_context = False
    
    for line in text.splitlines():
        lower_line = line.lower()
        if any(kw in lower_line for kw in or_keywords):
            is_or_context = True
            
        skills_in_line = extract_skills(line)
        if not skills_in_line:
            continue
            
        if is_or_context and len(skills_in_line) > 1:
            groups.append(skills_in_line) # OR group
            is_or_context = False # Reset after using
        else:
            for s in skills_in_line:
                groups.append([s]) # AND group
            is_or_context = False # Reset if used
                
    unique_groups = []
    for g in groups:
        if g not in unique_groups:
            unique_groups.append(g)
    return unique_groups


def evaluate_skills(skill_groups: list[list[str]], cv_skills: list[str]) -> tuple[list[str], list[str]]:
    matched = []
    missing = []
    
    for group in skill_groups:
        group_matched = [s for s in group if s in cv_skills]
        if group_matched:
            for s in group_matched:
                if s not in matched:
                    matched.append(s)
        else:
            repr_group = " hoặc ".join(group)
            if repr_group not in missing:
                missing.append(repr_group)
                
    return matched, missing


def extract_mandatory_and_nice_skills(jd_text: str) -> tuple[list[list[str]], list[list[str]]]:
    lines = [line.strip() for line in (jd_text or "").splitlines() if line.strip()]
    mandatory_text = []
    nice_to_have_text = []
    
    is_nice = False
    nice_keywords = ["nice to have", "nice-to-have", "plus", "điểm cộng", "ưu tiên", "không bắt buộc", "optional", "bonus", "lợi thế"]
    
    for line in lines:
        lower_line = line.lower()
        if any(kw in lower_line for kw in nice_keywords) and len(line) < 60:
            is_nice = True
            
        if is_nice:
            nice_to_have_text.append(line)
        else:
            mandatory_text.append(line)
            
    mandatory_groups = extract_skill_requirements("\n".join(mandatory_text))
    nice_groups = extract_skill_requirements("\n".join(nice_to_have_text))
    
    flat_mandatory = {s for g in mandatory_groups for s in g}
    filtered_nice_groups = []
    for g in nice_groups:
        filtered_g = [s for s in g if s not in flat_mandatory]
        if filtered_g:
            filtered_nice_groups.append(filtered_g)
    
    return mandatory_groups, filtered_nice_groups


def build_vietnamese_analysis(
    jd_text: str,
    cv_text: str,
    match_score: float,
) -> dict:
    mandatory_groups, nice_groups = extract_mandatory_and_nice_skills(jd_text)
    cv_skills = extract_skills(cv_text)
    
    matched_mandatory, missing_mandatory = evaluate_skills(mandatory_groups, cv_skills)
    matched_nice, missing_nice = evaluate_skills(nice_groups, cv_skills)
    
    flat_mandatory = [s for g in mandatory_groups for s in g]
    flat_nice = [s for g in nice_groups for s in g]
    jd_skills = flat_mandatory + flat_nice
    matched_skills = matched_mandatory + matched_nice
    
    extra_skills = [s for s in cv_skills if s not in jd_skills]
    
    jd_domain = extract_role_from_text(jd_text) or infer_domain(jd_skills, jd_text)
    cv_domain = extract_role_from_text(cv_text) or infer_domain(cv_skills, cv_text)

    strengths = []
    weaknesses = []

    if matched_mandatory:
        strengths.append(
            "Ứng viên đáp ứng các kỹ năng BẮT BUỘC: "
            + ", ".join(take_items(matched_mandatory))
            + "."
        )
        
    if matched_nice:
        strengths.append(
            "Điểm cộng (Nice-to-have): Ứng viên có kỹ năng ưu tiên: "
            + ", ".join(take_items(matched_nice))
            + "."
        )

    if match_score >= PASS_THRESHOLD:
        strengths.append(
            f"Độ tương đồng tổng thể đạt {match_score}%, phù hợp để chuyển sang bước phỏng vấn."
        )
    elif match_score >= REVIEW_THRESHOLD:
        strengths.append(
            f"Độ tương đồng đạt {match_score}%, có thể xem xét thêm nếu kinh nghiệm thực tế phù hợp."
        )

    if extra_skills:
        strengths.append(
            "CV có thêm năng lực liên quan: " + ", ".join(take_items(extra_skills)) + "."
        )

    if not strengths:
        strengths.append("CV có một số tín hiệu liên quan tới JD nhưng chưa nổi bật.")

    if missing_mandatory:
        weaknesses.append(
            "Chưa thấy rõ trong CV các yêu cầu BẮT BUỘC: "
            + ", ".join(take_items(missing_mandatory))
            + "."
        )

    if match_score < REVIEW_THRESHOLD:
        weaknesses.append(
            f"Độ tương đồng chỉ đạt {match_score}%, cần kiểm tra kỹ trước khi mời phỏng vấn."
        )

    if not cv_skills:
        weaknesses.append("CV chưa trình bày rõ nhóm kỹ năng kỹ thuật để hệ thống đối chiếu.")

    if not weaknesses:
        weaknesses.append("Chưa phát hiện hạn chế lớn từ phần kỹ năng và nội dung CV.")

    jd_domain_inferred = infer_domain(jd_skills, jd_text)
    cv_domain_inferred = infer_domain(cv_skills, cv_text)

    if jd_domain == cv_domain and jd_domain != "Chưa xác định rõ":
        domain_comment = f"CV và JD cùng nhóm {jd_domain}."
    elif jd_domain_inferred == cv_domain_inferred and jd_domain_inferred != "Chưa xác định rõ":
        domain_comment = f"CV và JD cùng thuộc lĩnh vực {jd_domain_inferred}."
    elif jd_domain != "Chưa xác định rõ" and cv_domain != "Chưa xác định rõ":
        domain_comment = f"JD nghiêng về {jd_domain}, trong khi CV nghiêng về {cv_domain}; cần phỏng vấn để xác nhận mức độ phù hợp."
    else:
        domain_comment = "Chưa đủ dữ liệu để kết luận chắc chắn về nhóm lĩnh vực."

    return {
        "jd_skills": jd_skills,
        "cv_skills": cv_skills,
        "mandatory_groups": mandatory_groups,
        "nice_groups": nice_groups,
        "matched_mandatory": matched_mandatory,
        "matched_nice": matched_nice,
        "matched_skills": matched_skills,
        "missing_mandatory": missing_mandatory,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "jd_domain": jd_domain,
        "cv_domain": cv_domain,
        "domain_comment": domain_comment,
    }


def prepare_text_for_embedding(text: str) -> str:
    clean_text = normalize_text(text)
    if not clean_text:
        raise ValueError("Input text is empty.")

    embedding_text = build_embedding_input(clean_text)
    if len(embedding_text) > MAX_EMBEDDING_CHARS:
        return embedding_text[:MAX_EMBEDDING_CHARS]

    return embedding_text


def read_pdf_with_ollama_ocr(doc) -> tuple[str, Optional[str]]:
    """Optional OCR fallback for scanned PDFs with an Ollama vision model."""
    if not OLLAMA_OCR_MODEL:
        return (
            "",
            "Cannot read text from PDF. The file may be a scanned/image PDF. "
            "Set OLLAMA_OCR_MODEL to a local vision model such as llama3.2-vision "
            "to enable OCR.",
        )

    try:
        page_texts = []
        max_pages = min(len(doc), OCR_MAX_PAGES)

        for page_index in range(max_pages):
            page = doc[page_index]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image_base64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
            response = ollama.chat(
                model=OLLAMA_OCR_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Extract all readable text from this CV page. "
                            "Return only plain text, no explanation."
                        ),
                        "images": [image_base64],
                    }
                ],
                keep_alive=OLLAMA_KEEP_ALIVE,
            )
            content = response.get("message", {}).get("content", "").strip()
            if content:
                page_texts.append(content)

        ocr_text = "\n".join(page_texts).strip()
        if not ocr_text:
            return "", "Ollama OCR returned no text from the scanned PDF."

        return ocr_text, None
    except Exception as exc:
        return "", f"Ollama OCR error: {exc}"


def read_pdf(file_bytes: bytes):
    """Read selectable text from a PDF file with PyMuPDF."""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text_parts = []

        for page in doc:
            page_text = page.get_text()
            if page_text.strip():
                text_parts.append(page_text)

        text = "\n".join(text_parts).strip()
        if not text:
            ocr_text, ocr_error = read_pdf_with_ollama_ocr(doc)
            doc.close()
            if ocr_text:
                return ocr_text, None
            return "", ocr_error

        doc.close()

        return text, None
    except Exception as exc:
        print(f"PDF read error: {exc}")
        return "", str(exc)


def get_text_embedding(text: str) -> list[float]:
    """
    Embed text with local Ollama models, then use the vector for cosine similarity.
    """
    embedding_text = prepare_text_for_embedding(text)
    candidates = get_embedding_model_candidates()
    last_error = None

    for index, model_name in enumerate(candidates):
        try:
            response = ollama.embed(
                model=model_name,
                input=embedding_text,
                keep_alive=OLLAMA_KEEP_ALIVE,
            )
            remember_active_embedding_model(model_name)
            return extract_embedding_vector(response)
        except Exception as exc:
            last_error = exc
            has_next_model = index < len(candidates) - 1
            if has_next_model and is_ollama_model_unavailable_error(exc):
                print(
                    f"[EMBEDDING] Model {model_name} is unavailable. "
                    f"Trying {candidates[index + 1]}."
                )
                continue
            break

    raise EmbeddingServiceError(f"Ollama embedding error: {last_error}") from last_error


def calculate_cosine_similarity(vec1: Sequence[float], vec2: Sequence[float]) -> float:
    a = np.asarray(vec1, dtype=np.float32)
    b = np.asarray(vec2, dtype=np.float32)

    if a.size == 0 or b.size == 0:
        raise ValueError("Cannot calculate cosine similarity for empty vectors.")

    if a.shape != b.shape:
        raise ValueError(f"Vector dimensions do not match: {a.shape} vs {b.shape}.")

    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        return 0.0

    similarity = float(np.dot(a, b) / denominator)
    return max(-1.0, min(1.0, similarity))


def similarity_to_percentage(similarity: float) -> float:
    score = ((similarity + 1.0) / 2.0) * 100.0
    return round(max(0.0, min(100.0, score)), 2)


def extract_candidate_email(cv_text: str) -> str:
    match = EMAIL_REGEX.search(cv_text or "")
    return match.group(1) if match else ""


def extract_candidate_name(cv_text: str, filename: str = "") -> str:
    ignored_terms = (
        "resume",
        "curriculum vitae",
        "cv",
        "profile",
        "email",
        "phone",
        "linkedin",
        "github",
    )

    lines = [line.strip() for line in (cv_text or "").splitlines() if line.strip()]
    for line in lines[:12]:
        clean_line = re.sub(r"\s+", " ", line).strip(" -_|")
        lower_line = clean_line.lower()

        if not (2 <= len(clean_line) <= 80):
            continue
        if EMAIL_REGEX.search(clean_line) or any(char.isdigit() for char in clean_line):
            continue
        if ":" in clean_line or any(term == lower_line for term in ignored_terms):
            continue
        if len(clean_line.split()) <= 6:
            return clean_line

    fallback = os.path.splitext(filename or "")[0].strip()
    return fallback or "Unknown candidate"


def extract_years_of_experience(cv_text: str) -> int:
    if not cv_text:
        return 0
    text = cv_text.lower()
    patterns = [
        r"(\d+)(?:\+| - \d+)?\s*(?:years?|yrs?)(?:\s*of\s*experience)?",
        r"(\d+)(?:\+| - \d+)?\s*năm\s*kinh\s*nghiệm",
        r"kinh\s*nghiệm\s*(?:hơn\s*|trên\s*|over\s*)?(\d+)(?:\+| - \d+)?\s*năm",
        r"(?:over|more than)\s*(\d+)\s*(?:years?|yrs?)"
    ]
    max_years = 0
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            try:
                y = int(match.group(1))
                if 0 < y < 30:
                    max_years = max(max_years, y)
            except ValueError:
                pass
                
    if max_years == 0:
        lines = [line.strip().lower() for line in text.splitlines()[:20] if line.strip()]
        for line in lines:
            if "senior" in line or "lead" in line or "architect" in line or "trưởng nhóm" in line:
                return 4
            elif "mid-level" in line or "mid level" in line or "middle" in line:
                return 2
            elif "junior" in line:
                return 1
            elif "intern" in line or "fresher" in line or "thực tập" in line:
                return 0
                
    return max_years


def get_decision(score: float) -> tuple[str, str, bool]:
    if score >= PASS_THRESHOLD:
        return "ĐẠT", "PASS", True
    if score >= REVIEW_THRESHOLD:
        return "CHỜ XEM XÉT", "PENDING", False
    return "KHÔNG ĐẠT", "FAIL", False


def build_score_breakdown(
    semantic_score: float,
    mandatory_groups: Optional[Sequence[list[str]]] = None,
    matched_mandatory: Optional[Sequence[str]] = None,
    matched_nice: Optional[Sequence[str]] = None,
    exp_score: float = 0.0,
    skill_kill_switch: bool = False,
    has_core_skill: bool = True,
) -> dict:
    if skill_kill_switch:
        return {
            "semantic_similarity": 0,
            "ky_nang_bat_buoc": 0,
            "so_nam_va_cap_do": 0,
            "chat_luong_kinh_nghiem": 0,
            "ky_nang_cong_diem": 0,
            "tong_diem": 0,
        }

    mandatory_groups = mandatory_groups or []
    matched_mandatory = matched_mandatory or []
    matched_nice = matched_nice or []

    if mandatory_groups:
        fulfilled_groups = 0.0
        for g in mandatory_groups:
            matched_count = sum(1 for s in g if s in matched_mandatory)
            if len(g) > 1:
                if matched_count >= 2:
                    fulfilled_groups += 1.0
                elif matched_count == 1:
                    fulfilled_groups += 0.5
            else:
                if matched_count > 0:
                    fulfilled_groups += 1.0
        skill_ratio = fulfilled_groups / len(mandatory_groups)
    else:
        skill_ratio = semantic_score / 100.0

    ky_nang_bat_buoc = int(round(45 * skill_ratio))
    if exp_score >= 100.0:
        so_nam_va_cap_do = 30
    else:
        so_nam_va_cap_do = int(round(30 * (exp_score / 100.0) * skill_ratio))
    
    if has_core_skill:
        chat_luong_kinh_nghiem = int(round(15 * (semantic_score / 100.0) * skill_ratio))
    else:
        chat_luong_kinh_nghiem = 0
        
    # Bonus for nice-to-have skills
    ky_nang_cong_diem = int(round(10 * (semantic_score / 100.0) * skill_ratio)) + (len(matched_nice) * 3)
    if ky_nang_cong_diem > 10:
        ky_nang_cong_diem = 10

    tong_diem = min(100, ky_nang_bat_buoc + so_nam_va_cap_do + chat_luong_kinh_nghiem + ky_nang_cong_diem)

    return {
        "semantic_similarity": int(round(semantic_score)),
        "ky_nang_bat_buoc": ky_nang_bat_buoc,
        "so_nam_va_cap_do": so_nam_va_cap_do,
        "chat_luong_kinh_nghiem": chat_luong_kinh_nghiem,
        "ky_nang_cong_diem": ky_nang_cong_diem,
        "tong_diem": tong_diem,
    }


def prepare_job(jd_text: str) -> list[float]:
    """Embed JD once and reuse it for batch CV scans with the same JD text."""
    prepared_jd = prepare_text_for_embedding(jd_text)
    jd_hash = hashlib.md5(prepared_jd.encode("utf-8")).hexdigest()

    with global_ats_state.lock:
        if (
            global_ats_state.current_jd_hash == jd_hash
            and global_ats_state.jd_embedding is not None
        ):
            print("[CACHE] Reusing JD embedding.")
            return global_ats_state.jd_embedding

        print("[EMBEDDING] Creating JD embedding.")
        jd_embedding = get_text_embedding(prepared_jd)
        global_ats_state.current_jd_hash = jd_hash
        global_ats_state.jd_embedding = jd_embedding
        global_ats_state.jd_text = prepared_jd
        return jd_embedding


def match_cv_to_jd(
    cv_text: str,
    jd_embedding: Sequence[float],
    filename: str = "",
    jd_text: str = "",
) -> dict:
    print(f"[EMBEDDING] Creating CV embedding for {filename or 'uploaded file'}.")
    cv_embedding = get_text_embedding(cv_text)

    similarity = calculate_cosine_similarity(jd_embedding, cv_embedding)
    semantic_score = similarity_to_percentage(similarity)
    analysis = build_vietnamese_analysis(
        jd_text or global_ats_state.jd_text,
        cv_text,
        semantic_score,
    )

    actual_jd_text = jd_text or global_ats_state.jd_text
    jd_years = extract_years_of_experience(actual_jd_text)
    cv_years = extract_years_of_experience(cv_text)
    
    # Force 0 years for Intern/Fresher roles or if no experience is required
    jd_domain_role = extract_role_from_text(actual_jd_text) or ""
    is_intern_role = any(role in jd_domain_role.lower() for role in ["intern", "thực tập", "fresher"])
    entry_level_keywords = ["không yêu cầu kinh nghiệm", "mới tốt nghiệp", "sinh viên năm cuối", "chưa có kinh nghiệm"]
    
    if is_intern_role or any(kw in actual_jd_text.lower() for kw in entry_level_keywords):
        jd_years = 0
    
    if jd_years > 0:
        if cv_years >= jd_years:
            exp_score = 100.0
        else:
            exp_score = 0.0
    else:
        exp_score = 100.0
    
    jd_domain_inferred = infer_domain(analysis.get("jd_skills", []), actual_jd_text)
    cv_domain_inferred = infer_domain(analysis.get("cv_skills", []), cv_text)

    core_jd_skills = extract_skills("\n".join(actual_jd_text.splitlines()[:3]))
    if core_jd_skills:
        has_core_skill = any(skill in analysis["cv_skills"] for skill in core_jd_skills) or (jd_domain_inferred == cv_domain_inferred and jd_domain_inferred != "Chưa xác định rõ")
    else:
        has_core_skill = bool(analysis["matched_skills"]) if analysis["jd_skills"] else True

    skill_kill_switch = bool(analysis["mandatory_groups"]) and not analysis["matched_mandatory"]

    score_breakdown = build_score_breakdown(
        semantic_score=semantic_score,
        mandatory_groups=analysis["mandatory_groups"],
        matched_mandatory=analysis["matched_mandatory"],
        matched_nice=analysis["matched_nice"],
        exp_score=exp_score,
        skill_kill_switch=skill_kill_switch,
        has_core_skill=has_core_skill,
    )
    match_score = score_breakdown["tong_diem"]

    analysis = build_vietnamese_analysis(
        jd_text or global_ats_state.jd_text,
        cv_text,
        match_score,
    )
    if skill_kill_switch:
        analysis["weaknesses"].insert(
            0,
            "Không khớp bất kỳ kỹ năng bắt buộc nào trong JD, hệ thống cho rớt tự động.",
        )
    if jd_years > 0 and cv_years < jd_years:
        analysis["weaknesses"].insert(
            0,
            f"Chưa đáp ứng đủ yêu cầu kinh nghiệm (JD yêu cầu {jd_years} năm, CV chỉ có {cv_years} năm).",
        )

    decision_vi, decision_code, passed = get_decision(match_score)
    candidate_name = extract_candidate_name(cv_text, filename)
    candidate_email = extract_candidate_email(cv_text)
    candidate_years_experience = cv_years
    embedding_model = _active_embedding_model or get_embedding_model_candidates()[0]

    return {
        "match_score": match_score,
        "method": "Vector Embedding",
        "embedding_model": embedding_model,
        "similarity": round(similarity, 6),
        "semantic_score": semantic_score,
        "filename": filename,
        "candidate_name": candidate_name,
        "candidate_email": candidate_email,
        "score": match_score,
        "passed": passed,
        "final_decision": decision_code,
        "candidate_years_experience": candidate_years_experience,
        "industry": analysis["cv_domain"],
        "match_reason": (
            f"Điểm phù hợp đạt {match_score}% dựa trên so khớp ngữ nghĩa và kỹ năng trong CV/JD."
        ),
        "summary": (
            f"Ứng viên {candidate_name} được đánh giá ở mức {decision_vi.lower()} "
            f"cho nhóm {analysis['jd_domain']}."
        ),
        "strengths": analysis["strengths"],
        "weaknesses": analysis["weaknesses"],
        "tong_quan": {
            "diem_tong": match_score,
            "quyet_dinh": decision_vi,
            "ten_ung_vien": candidate_name,
            "nganh_nghe": analysis["cv_domain"],
            "so_nam_kinh_nghiem": candidate_years_experience,
            "phuong_phap": "Ollama Semantic Search",
        },
        "chi_tiet_diem": score_breakdown,
        "phan_tich_linh_vuc": {
            "linh_vuc_jd": analysis["jd_domain"],
            "linh_vuc_cv": analysis["cv_domain"],
            "phu_hop": match_score >= REVIEW_THRESHOLD,
            "nhan_xet": analysis["domain_comment"],
        },
        "ky_nang": {
            "ung_vien_co": analysis["matched_skills"] or ["Chưa phát hiện kỹ năng trùng rõ ràng"],
            "bat_buoc_con_thieu": analysis["missing_mandatory"] or ["Đã đáp ứng đủ kỹ năng bắt buộc"],
        },
        "nhan_xet_tuyen_dung": {
            "diem_manh": analysis["strengths"],
            "diem_yeu": analysis["weaknesses"],
            "ghi_chu_phong_van": "Nên hỏi ứng viên trình bày dự án gần nhất có dùng các kỹ năng trùng với JD.",
            "ly_do_quyet_dinh": (
                f"Hệ thống chấm {match_score}% nhờ so khớp ngữ nghĩa bằng Ollama và kiểm tra kỹ năng xuất hiện trong CV/JD."
            ),
        },
    }


def process_single_cv(
    cv_text: str,
    jd_embedding: Sequence[float],
    filename: str = "",
    jd_text: str = "",
):
    try:
        return match_cv_to_jd(cv_text, jd_embedding, filename, jd_text), None
    except Exception as exc:
        print(f"CV matching error ({filename}): {exc}")
        return None, str(exc)


def batch_processor(cv_data_list: list[dict], jd_text: str) -> list[dict]:
    results = []

    try:
        jd_embedding = prepare_job(jd_text)
    except Exception as exc:
        error = f"JD embedding error: {exc}"
        return [
            {
                "filename": item.get("filename", ""),
                "success": False,
                "data": None,
                "error": error,
            }
            for item in cv_data_list
        ]

    for cv_item in cv_data_list:
        filename = cv_item.get("filename", "")
        result, error = process_single_cv(
            cv_item.get("text", ""),
            jd_embedding,
            filename,
            jd_text,
        )
        results.append(
            {
                "filename": filename,
                "success": result is not None,
                "data": result,
                "error": error,
            }
        )

    return results


def process_pipeline(cv_text: str, jd_text: str, filename: str = ""):
    """Compatibility wrapper used by the local upload API and Gmail scanner."""
    try:
        jd_embedding = prepare_job(jd_text)
        return process_single_cv(cv_text, jd_embedding, filename, jd_text)
    except Exception as exc:
        print(f"Pipeline error ({filename}): {exc}")
        return None, str(exc)


def get_error_status_code(error: Optional[str]) -> int:
    error_text = (error or "").lower()
    if "ollama embedding error" in error_text:
        return 502
    if "input text is empty" in error_text:
        return 400
    return 500


@app.post("/api/scan-local-cv")
async def scan_local_cv(jd_text: str = Form(...), file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    if not normalize_text(jd_text):
        raise HTTPException(status_code=400, detail="Job description text is empty.")

    try:
        file_bytes = await file.read()
        cv_text, pdf_error = read_pdf(file_bytes)

        if not cv_text:
            raise HTTPException(status_code=422, detail="Lỗi định dạng: Không thể trích xuất văn bản từ CV này.")

        result, error = process_pipeline(cv_text, jd_text, file.filename)
        if not result:
            raise HTTPException(status_code=get_error_status_code(error), detail=error)

        return {
            "status": "success",
            "match_score": result["match_score"],
            "method": result["method"],
            "data": result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        print(f"API error (local CV): {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/upload_cvs")
async def upload_cvs(job_description: str = Form(...), files: list[UploadFile] = File(...)):
    if not normalize_text(job_description):
        raise HTTPException(status_code=400, detail="Job description text is empty.")

    cv_data_list = []
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            cv_data_list.append({
                "filename": file.filename or "unknown",
                "text": "",
                "error": "Only PDF files are supported."
            })
            continue

        try:
            file_bytes = await file.read()
            cv_text, pdf_error = read_pdf(file_bytes)

            if not cv_text:
                cv_data_list.append({
                    "filename": file.filename,
                    "text": "",
                    "error": "Lỗi định dạng: Không thể trích xuất văn bản từ CV này."
                })
            else:
                cv_data_list.append({
                    "filename": file.filename,
                    "text": cv_text,
                    "error": None
                })
        except Exception as e:
             cv_data_list.append({
                "filename": file.filename,
                "text": "",
                "error": f"Lỗi đọc file: {e}"
            })

    valid_cvs = [cv for cv in cv_data_list if cv["text"]]
    
    batch_results = []
    if valid_cvs:
        batch_results = batch_processor(valid_cvs, job_description)
        
    final_results = []
    for cv in cv_data_list:
        if cv["error"]:
            final_results.append({
                "filename": cv["filename"],
                "success": False,
                "error": cv["error"],
                "data": None
            })
        else:
            matched = next((res for res in batch_results if res["filename"] == cv["filename"]), None)
            if matched:
                final_results.append(matched)
                
    return {"status": "success", "results": final_results}


@app.post("/api/scan-gmail")
async def scan_gmail(
    jd_text: str = Form(...),
    query: str = Form(...),
    time_range: str = Form("all"),
    max_results: Optional[int] = Form(50),
):
    try:
        final_query = query
        if time_range != "all":
            final_query = f"{query} newer_than:{time_range}"

        results = scan_gmail_attachments(
            jd_text,
            final_query,
            max_results,
            read_pdf,
            process_pipeline,
        )
        return {"status": "success", "data": results}
    except Exception as exc:
        print(f"API error (Gmail): {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class EmailRequest(BaseModel):
    email: str
    name: str


@app.post("/api/send-interview-email")
async def send_interview_email(request: EmailRequest):
    subject = f"Thư Mời Phỏng Vấn - Chúc mừng {request.name} đã vượt qua vòng sơ loại!"
    body = f"""Chào {request.name},

Chúc mừng bạn đã vượt qua vòng sơ loại hồ sơ AI của chúng tôi.
Hồ sơ của bạn được đánh giá là phù hợp với vị trí mà chúng tôi đang tìm kiếm.

Để chuẩn bị cho bước tiếp theo, vui lòng điền thông tin bổ sung vào biểu mẫu sau đây:
https://forms.gle/JE7m5EQF4x37jhvQ6

Nếu bạn có bất kỳ câu hỏi nào, đừng ngần ngại phản hồi lại email này.

Trân trọng,
Bộ phận Tuyển dụng
"""
    success, message = send_gmail_message(request.email, subject, body)
    if success:
        return {"message": "Đã gửi email thành công!"}

    raise HTTPException(status_code=500, detail=message)


# ─────────────────────────────────────────
#  JD Management Endpoints
# ─────────────────────────────────────────

class SaveJDRequest(BaseModel):
    title: str = ""
    jd_text: str
    pass_threshold: float = 70.0
    review_threshold: float = 50.0


@app.post("/api/jd", status_code=201)
async def save_jd(request: SaveJDRequest):
    """Luu mot JD moi vao SQLite. Neu JD da ton tai (cung hash) thi cap nhat title/threshold."""
    if not normalize_text(request.jd_text):
        raise HTTPException(status_code=400, detail="JD text is empty.")

    prepared = prepare_text_for_embedding(request.jd_text)
    jd_hash = hashlib.md5(prepared.encode("utf-8")).hexdigest()

    try:
        jd_id = upsert_job_description(
            jd_text=request.jd_text,
            jd_hash=jd_hash,
            title=request.title,
            pass_threshold=request.pass_threshold,
            review_threshold=request.review_threshold,
        )
        return {"status": "success", "id": jd_id, "jd_hash": jd_hash}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/jd")
async def list_jds(limit: int = 50, offset: int = 0):
    """Tra ve danh sach tat ca JD da luu, moi nhat truoc."""
    try:
        items = list_job_descriptions(limit=limit, offset=offset)
        return {"status": "success", "total": len(items), "data": items}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/jd/{jd_id}")
async def get_jd(jd_id: int):
    """Tra ve day du noi dung mot JD theo id."""
    jd = get_job_description(jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail=f"JD id={jd_id} not found.")
    return {"status": "success", "data": jd}


@app.delete("/api/jd/{jd_id}")
async def remove_jd(jd_id: int):
    """Xoa mot JD khoi SQLite."""
    deleted = delete_job_description(jd_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"JD id={jd_id} not found.")
    return {"status": "success", "message": f"JD id={jd_id} deleted."}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting FastAPI server at http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=True)
