---
description: Luồng tự động nhận CV, trích xuất văn bản, dùng AI (Ollama) chấm điểm dựa trên JD và phân loại ứng viên.
---

{
  "name": "CV_Screening_AI_Workflow",
  "description": "Luồng tự động phân tích chữ từ CV, đối chiếu với JD và dùng AI để chấm điểm ứng viên.",
  "trigger": {
    "type": "api",
    "inputs": [
      {
        "name": "cv_content",
        "type": "string",
        "description": "Chứa nội dung văn bản (text) đã được trích xuất từ file PDF/Docx của ứng viên."
      },
      {
        "name": "jd_content",
        "type": "string",
        "description": "Chứa nội dung Yêu cầu công việc (Job Description)."
      }
    ]
  },
  "steps": [
    {
      "name": "AI_HR_Evaluation",
      "description": "Trạm AI phân tích và chấm điểm CV",
      "action": "prompt",
      "inputs": {
        "cv": "{{cv_content}}",
        "jd": "{{jd_content}}"
      },
      "system_prompt": "Bạn là chuyên gia Tuyển dụng (HR). Nhiệm vụ của bạn là đọc nội dung CV: {{cv}} và so sánh nó với Yêu cầu công việc (JD): {{jd}}. Chú ý phân biệt rạch ròi giữa 'Ngành/Chuyên môn' (VD: Frontend, Backend) và 'Cấp bậc' (VD: Intern, Junior, Senior, Lead). Tuyệt đối không lấy cấp bậc làm ngành. Khi phân tích, hãy tự động quy đổi cấp bậc sang số năm kinh nghiệm tương ứng (Intern/Fresher: 0 năm, Junior: 1 năm, Mid: 2 năm, Senior/Lead: 4+ năm) nếu CV không ghi rõ số năm. QUAN TRỌNG: Nếu JD ghi yêu cầu dạng lựa chọn (ví dụ: 'Thành thạo 1 trong các stack', 'Biết 1 trong 2'), hãy áp dụng quy tắc chấm điểm sau: Nếu ứng viên ĐÁP ỨNG ĐƯỢC 1 LỰA CHỌN, hãy chấm một nửa (50%) số điểm cho tiêu chí đó. Nếu ứng viên ĐÁP ỨNG ĐƯỢC TỪ 2 LỰA CHỌN TRỞ LÊN, hãy chấm ĐIỂM TUYỆT ĐỐI (100%) cho tiêu chí đó. Tuyệt đối không đánh giá là hoàn toàn thiếu sót nếu họ đã có ít nhất 1. Hãy phân tích kỹ năng, kinh nghiệm. Sau đó trả về kết quả bằng Tiếng Việt gồm 3 phần: 1. Điểm phù hợp (0-100), 2. Kỹ năng trùng khớp, 3. Lý do điểm cao/thấp."
    }
  ]
}