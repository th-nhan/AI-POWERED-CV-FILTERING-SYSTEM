import React, { useState, useRef, useMemo, useEffect, useCallback } from 'react';
import {
  UploadCloud, Mail, FileText, CheckCircle2, XCircle,
  Trash2, File as FileIcon, Loader2, ChevronRight, X,
  ArrowUpDown, BrainCircuit, ExternalLink, Menu,
  Briefcase, Search, AlertCircle, Save, History, ChevronDown, ChevronUp, RefreshCw
} from 'lucide-react';
import axios from 'axios';

/* =========================================
   1. MODAL CHI TIẾT KẾT QUẢ (DRAWER)
========================================= */
const ResultDrawer = ({ isOpen, onClose, data }) => {
  if (!isOpen || !data) return null;

  const tq = data.tong_quan || {};
  const plv = data.phan_tich_linh_vuc || {};
  const bccc = data.bang_cap_chung_chi || {};
  const kn = data.ky_nang || {};
  const ctd = data.chi_tiet_diem || {};
  const nxtd = data.nhan_xet_tuyen_dung || {};

  const safeArray = (val) => Array.isArray(val) ? val : (val ? [val] : []);

  const decisionColor = {
    'ĐẠT': { bg: 'text-emerald-600', badge: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: <CheckCircle2 className="w-10 h-10 text-emerald-100" /> },
    'KHÔNG ĐẠT': { bg: 'text-rose-600', badge: 'bg-rose-50 text-rose-700 border-rose-200', icon: <XCircle className="w-10 h-10 text-rose-100" /> },
    'CHỜ XEM XÉT': { bg: 'text-amber-600', badge: 'bg-amber-50 text-amber-700 border-amber-200', icon: <Loader2 className="w-10 h-10 text-amber-100" /> },
  };
  const qd = tq.quyet_dinh || data.final_decision || 'KHÔNG ĐẠT';
  const dc = decisionColor[qd] || decisionColor['KHÔNG ĐẠT'];

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/50 backdrop-blur-sm transition-all" onClick={onClose}>
      <div 
        className="w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-300"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-100">
          <div>
            <h2 className="text-xl font-bold text-slate-800">Chi tiết Phân tích AI</h2>
            <p className="text-sm text-slate-500 mt-1">{data.candidate_name || data.filename}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-full transition-colors text-slate-500">
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5 bg-slate-50">

          {/* Top Stats: Score + Decision + Industry */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col gap-1">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Điểm AI</p>
              <p className="text-3xl font-black text-indigo-600">{tq.diem_tong ?? data.score ?? 0}<span className="text-sm font-normal text-slate-400">/100</span></p>
            </div>
            <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col gap-1">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Quyết định</p>
              <p className={`text-2xl font-black ${dc.bg}`}>{qd}</p>
            </div>
            <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col gap-1">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Ngành</p>
              <p className="text-sm font-bold text-slate-700 leading-tight">{tq.nganh_nghe || data.industry || '—'}</p>
            </div>
          </div>

          {/* Scoring Breakdown */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800 mb-3">Chi tiết chấm điểm</h3>
            <div className="space-y-2.5">
              {[
                { label: 'Kỹ năng bắt buộc', key: 'ky_nang_bat_buoc', max: 45 },
                { label: 'Số năm & Cấp độ', key: 'so_nam_va_cap_do', max: 30 },
                { label: 'Chất lượng kinh nghiệm', key: 'chat_luong_kinh_nghiem', max: 15 },
                { label: 'Kỹ năng cộng điểm', key: 'ky_nang_cong_diem', max: 10 },
              ].map(({ label, key, max }) => {
                const val = ctd[key] ?? 0;
                const pct = Math.round((val / max) * 100);
                return (
                  <div key={key}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-600 font-medium">{label}</span>
                      <span className="font-bold text-slate-800">{val}/{max}</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full bg-indigo-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Kết luận */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800 mb-2">Kết luận tuyển dụng</h3>
            <p className="text-sm text-slate-600 italic border-l-4 border-indigo-500 pl-3 py-1 bg-indigo-50/50">"{nxtd.ly_do_quyet_dinh || data.match_reason}"</p>
          </div>

          {/* Domain Analysis */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800 mb-3">Phân tích lĩnh vực</h3>
            <div className="grid grid-cols-2 gap-3 text-sm mb-3">
              <div className="bg-slate-50 rounded-xl p-3">
                <p className="text-xs text-slate-400 font-bold uppercase mb-1">JD yêu cầu</p>
                <p className="font-semibold text-slate-700">{plv.linh_vuc_jd || '—'}</p>
              </div>
              <div className="bg-slate-50 rounded-xl p-3">
                <p className="text-xs text-slate-400 font-bold uppercase mb-1">CV ứng viên</p>
                <p className="font-semibold text-slate-700">{plv.linh_vuc_cv || '—'}</p>
              </div>
            </div>
            <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full border ${plv.phu_hop ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-rose-50 text-rose-700 border-rose-200'}`}>
              {plv.phu_hop ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
              {plv.phu_hop ? 'Khớp ngành' : 'Lệch ngành'}
            </span>
            {plv.nhan_xet && <p className="text-xs text-slate-500 mt-2 italic">{plv.nhan_xet}</p>}
          </div>

          {/* Credential Check */}
          {(bccc.yeu_cau?.length > 0 || bccc.nhan_xet) && (
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
              <h3 className="text-sm font-bold text-slate-800 mb-2">Bằng cấp / Chứng chỉ</h3>
              {safeArray(bccc.yeu_cau).length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {safeArray(bccc.yeu_cau).map((c, i) => (
                    <span key={i} className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium">{c}</span>
                  ))}
                </div>
              )}
              <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full border ${bccc.ung_vien_co_du ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-rose-50 text-rose-700 border-rose-200'}`}>
                {bccc.ung_vien_co_du ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {bccc.ung_vien_co_du ? 'Có chứng chỉ' : 'Thiếu chứng chỉ'}
              </span>
              {bccc.nhan_xet && <p className="text-xs text-slate-500 mt-2 italic">{bccc.nhan_xet}</p>}
            </div>
          )}

          {/* Skills */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-emerald-50/50 p-5 rounded-2xl border border-emerald-100">
              <h3 className="text-sm font-bold text-emerald-800 mb-3 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" /> Kỹ năng đáp ứng
              </h3>
              <ul className="space-y-1.5">
                {safeArray(kn.ung_vien_co).map((s, i) => (
                  <li key={i} className="text-xs text-emerald-700 font-medium bg-emerald-100/50 px-2.5 py-1.5 rounded-lg border border-emerald-200/50">{s}</li>
                ))}
              </ul>
            </div>
            <div className="bg-rose-50/50 p-5 rounded-2xl border border-rose-100">
              <h3 className="text-sm font-bold text-rose-800 mb-3 flex items-center gap-2">
                <XCircle className="w-4 h-4" /> Kỹ năng lõi còn thiếu
              </h3>
              <ul className="space-y-1.5">
                {safeArray(kn.bat_buoc_con_thieu).map((s, i) => (
                  <li key={i} className="text-xs text-rose-700 font-medium bg-rose-100/50 px-2.5 py-1.5 rounded-lg border border-rose-200/50">{s}</li>
                ))}
              </ul>
            </div>
          </div>

          {/* Strengths & Weaknesses */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-5">
            <div>
              <h3 className="text-sm font-bold text-indigo-900 mb-2">Điểm mạnh nổi bật</h3>
              <ul className="list-disc pl-4 space-y-1.5">
                {safeArray(nxtd.diem_manh).map((s, i) => (
                  <li key={i} className="text-sm text-slate-600">{s}</li>
                ))}
              </ul>
            </div>
            <div className="w-full h-px bg-slate-100" />
            <div>
              <h3 className="text-sm font-bold text-orange-900 mb-2">Hạn chế / Yếu điểm</h3>
              <ul className="list-disc pl-4 space-y-1.5">
                {safeArray(nxtd.diem_yeu).map((s, i) => (
                  <li key={i} className="text-sm text-slate-600">{s}</li>
                ))}
              </ul>
            </div>
          </div>

          {/* Recruiter Note */}
          {nxtd.ghi_chu_phong_van && (
            <div className="bg-amber-50 p-5 rounded-2xl border border-amber-200">
              <h3 className="text-sm font-bold text-amber-800 mb-2">📝 Ghi chú nội bộ HR</h3>
              <p className="text-sm text-amber-700">{nxtd.ghi_chu_phong_van}</p>
            </div>
          )}

        </div>
      </div>
    </div>
  );
};


/* =========================================
   2. MAIN APPLICATION COMPONENT
========================================= */
export default function App() {
  const [jdText, setJdText] = useState('');
  const [jdTitle, setJdTitle] = useState('');
  const [activeTab, setActiveTab] = useState('local');

  // JD History
  const [jdHistory, setJdHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [savingJd, setSavingJd] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const BASE_URL = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://127.0.0.1:8000'
    : (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000');

  const loadJdHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const res = await fetch(`${BASE_URL}/api/jd`);
      const data = await res.json();
      if (res.ok) setJdHistory(data.data || []);
    } catch (e) {
      console.error('loadJdHistory failed', e);
    } finally {
      setLoadingHistory(false);
    }
  }, [BASE_URL]);

  useEffect(() => { loadJdHistory(); }, [loadJdHistory]);

  const handleSaveJd = async () => {
    if (!jdText.trim()) { alert('Vui lòng nhập JD trước khi lưu!'); return; }
    setSavingJd(true);
    try {
      const res = await fetch(`${BASE_URL}/api/jd`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: jdTitle.trim() || 'JD không tên', jd_text: jdText }),
      });
      const data = await res.json();
      if (res.ok) {
        alert('Đã lưu JD thành công!');
        await loadJdHistory();
        setShowHistory(true);
      } else {
        alert('Lỗi lưu JD: ' + (data.detail || 'Không rõ'));
      }
    } catch (e) {
      alert('Mất kết nối server!');
    } finally {
      setSavingJd(false);
    }
  };

  const handleDeleteJd = async (id, e) => {
    e.stopPropagation();
    if (!confirm('Xóa JD này khỏi lịch sử?')) return;
    try {
      await fetch(`${BASE_URL}/api/jd/${id}`, { method: 'DELETE' });
      setJdHistory(prev => prev.filter(j => j.id !== id));
    } catch (e) { console.error(e); }
  };

  const handleLoadJd = async (jd) => {
    try {
      // Fetch full jd_text (list API only returns preview)
      const res = await fetch(`${BASE_URL}/api/jd/${jd.id}`);
      const data = await res.json();
      if (res.ok && data.data) {
        setJdText(data.data.jd_text || '');
        setJdTitle(data.data.title || '');
        setShowHistory(false);
      } else {
        alert('Không tải được JD: ' + (data.detail || 'Lỗi server'));
      }
    } catch (e) {
      alert('Mất kết nối server khi tải JD!');
    }
  };

  // File State
  const fileInputRef = useRef(null);
  const [files, setFiles] = useState([]); // [{ file: File, id: string, status: 'idle'|'scanning'|'done'|'error', result: obj }]

  // Gmail State
  const [gmailQuery, setGmailQuery] = useState('subject: "CV"');
  const [gmailTimeRange, setGmailTimeRange] = useState('1m');
  const [gmailScanning, setGmailScanning] = useState(false);

  // General Results
  const [results, setResults] = useState([]);
  const [sortOrder, setSortOrder] = useState('none');
  const [selectedResult, setSelectedResult] = useState(null);

  // -- FILE HANDLING (LOCAL) --
  const handleFileSelect = (e) => {
    const selectedFiles = Array.from(e.target.files);
    const newFiles = selectedFiles.map(f => ({
      file: f,
      id: Math.random().toString(36).substring(7),
      status: 'idle',
      result: null
    }));
    setFiles(prev => [...prev, ...newFiles]);
  };

  const removeFile = (id) => {
    setFiles(prev => prev.filter(f => f.id !== id));
  };

  const scanLocalFiles = async () => {
    if (!jdText) {
      alert("Vui lòng dán Job Description trước khi quét!");
      return;
    }

    // Process only idle or error files
    const filesToScan = files.filter(f => f.status === 'idle' || f.status === 'error');
    if (filesToScan.length === 0) return;

    for (let fObj of filesToScan) {
      // Update status to scanning
      setFiles(prev => prev.map(f => f.id === fObj.id ? { ...f, status: 'scanning' } : f));

      const formData = new FormData();
      formData.append('jd_text', jdText);
      formData.append('file', fObj.file);

      const BASE_URL = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') ? 'http://127.0.0.1:8000' : (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000');

      try {
        const response = await fetch(`${BASE_URL}/api/scan-local-cv`, {
          method: 'POST',
          body: formData,
        });
        const data = await response.json();

        if (response.ok && data.status === 'success') {
          const resultData = { ...data.data, source: 'Local', filename: fObj.file.name };
          setFiles(prev => prev.map(f => f.id === fObj.id ? { ...f, status: 'done', result: resultData } : f));
          setResults(prev => [...prev, resultData]);
        } else {
          console.error('scan-local-cv failed', response.status, data);
          setFiles(prev => prev.map(f => f.id === fObj.id ? { ...f, status: 'error', errorMsg: data.detail || 'Lỗi Server' } : f));
        }
      } catch (err) {
        console.error('scan-local-cv request failed', err);
        setFiles(prev => prev.map(f => f.id === fObj.id ? { ...f, status: 'error', errorMsg: 'Mất kết nối API' } : f));
      }
    }
  };

  const handleFetchFromGmail = async () => {
    if (!jdText) {
      alert("Vui lòng dán Job Description trước khi quét!");
      return;
    }
    setGmailScanning(true);
    try {
      const formData = new FormData();
      formData.append('jd_text', jdText);
      formData.append('query', gmailQuery);
      formData.append('time_range', gmailTimeRange);

      const BASE_URL = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') ? 'http://127.0.0.1:8000' : (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000');

      const response = await fetch(`${BASE_URL}/api/scan-gmail`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();

      if (response.ok && data.status === 'success') {
        if (data.data.length === 0) {
          alert("Không tìm thấy email nào khớp với truy vấn hoặc có đính kèm PDF.");
        } else {
          setResults(prev => [...prev, ...data.data]);
          alert(`Đã tải và quét thành công ${data.data.length} CV từ Gmail!`);
        }
      } else {
        alert("Lỗi từ server: " + (data.detail || 'Không xác định'));
      }
    } catch (e) {
      console.error(e);
      alert("Không thể kết nối đến Backend. Hãy chắc chắn Server đang chạy!");
    } finally {
      setGmailScanning(false);
    }
  };

  // -- TABLE SORTING --
  const sortedResults = useMemo(() => {
    if (sortOrder === 'none') {
      return results;
    }
    return [...results].sort((a, b) => {
      const scoreA = a.tong_quan?.diem_tong ?? a.score ?? 0;
      const scoreB = b.tong_quan?.diem_tong ?? b.score ?? 0;
      return sortOrder === 'desc' ? scoreB - scoreA : scoreA - scoreB;
    });
  }, [results, sortOrder]);

  const extractEmail = (value) => {
    const match = String(value || '').match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/);
    return match ? match[0] : '';
  };

  const handleSendEmail = async (res) => {
    const email = extractEmail(res.candidate_email);
    if (!email) {
      alert("Không tìm thấy địa chỉ email hợp lệ của ứng viên trong hồ sơ này!");
      return;
    }
    const BASE_URL = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') ? 'http://127.0.0.1:8000' : (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000');

    try {
      const response = await fetch(`${BASE_URL}/api/send-interview-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, name: res.candidate_name || 'Ứng viên' })
      });
      const data = await response.json();
      if (response.ok) {
        alert("Đã gửi email yêu cầu điền form thành công đến " + email + "!");
      } else {
        alert("Lỗi khi gửi email: " + (data.detail || "Không rõ nguyên nhân"));
      }
    } catch (e) {
      alert("Lỗi kết nối tới server: " + e.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-900">

      {/* TOPBAR */}
      <header className="w-full flex-shrink-0 h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 sticky top-0 z-40">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center shadow-sm shadow-indigo-200">
            <BrainCircuit className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">
            <span className="text-indigo-600">DTN</span>
            <span className="text-slate-900">CV</span>
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="w-8 h-8 rounded-full bg-slate-200 border-2 border-white shadow-sm overflow-hidden">
            <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=HR" alt="Avatar" />
          </div>
        </div>
      </header>

      <div className="flex flex-col md:flex-row flex-1 overflow-hidden">

        {/* SIDEBAR (Responsive: Top trên Mobile, Trái trên Desktop) */}
        <aside className="w-full md:w-[320px] lg:w-[380px] bg-white border-b md:border-b-0 md:border-r border-slate-200 flex flex-col shadow-sm z-30 flex-shrink-0 transition-all">
          <div className="p-5 flex-1 flex flex-col gap-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500 flex items-center gap-2">
              <Briefcase className="w-4 h-4" /> Yêu cầu tuyển dụng
            </h2>

            {/* JD Title Input */}
            <input
              type="text"
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all text-slate-700 placeholder-slate-400"
              placeholder="Tên vị trí tuyển dụng (VD: Backend Python)…"
              value={jdTitle}
              onChange={(e) => setJdTitle(e.target.value)}
            />

            {/* JD Textarea */}
            <textarea
              className="flex-1 w-full bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm resize-none outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all text-slate-700 leading-relaxed shadow-inner min-h-[150px] md:min-h-0"
              placeholder="Dán Job Description (JD) vào đây... Hệ thống AI sẽ phân tích dựa trên khung năng lực này."
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
            />

            {/* Action Buttons */}
            <div className="space-y-2">
              {/* Scan button */}
              <button
                onClick={activeTab === 'local' ? scanLocalFiles : handleFetchFromGmail}
                className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold shadow-sm shadow-indigo-200 transition-all active:scale-[0.98] flex items-center justify-center gap-2"
              >
                <BrainCircuit className="w-5 h-5" />
                {activeTab === 'local' ? 'Bắt đầu quét CV' : 'Quét Hộp thư Gmail'}
              </button>

              {/* Save JD button */}
              <button
                onClick={handleSaveJd}
                disabled={savingJd || !(jdText?.trim())}
                className="w-full py-2.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 rounded-xl font-semibold transition-all active:scale-[0.98] flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed text-sm"
              >
                {savingJd ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {savingJd ? 'Đang lưu…' : 'Lưu JD'}
              </button>

              {/* Toggle history */}
              <button
                onClick={() => { setShowHistory(v => !v); if (!showHistory) loadJdHistory(); }}
                className="w-full py-2 text-slate-500 hover:text-indigo-600 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
              >
                <History className="w-3.5 h-3.5" />
                Lịch sử JD ({jdHistory.length})
                {showHistory ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
            </div>

            {/* JD History Panel */}
            {showHistory && (
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
                  <span className="text-xs font-bold text-slate-500 uppercase tracking-wide">Lịch sử JD đã lưu</span>
                  <button onClick={loadJdHistory} className="p-1 hover:text-indigo-600 text-slate-400 transition-colors" title="Làm mới">
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingHistory ? 'animate-spin' : ''}`} />
                  </button>
                </div>
                <div className="max-h-56 overflow-y-auto divide-y divide-slate-100">
                  {jdHistory.length === 0 ? (
                    <p className="text-xs text-slate-400 text-center py-4">Chưa có JD nào được lưu</p>
                  ) : jdHistory.map(jd => (
                    <div
                      key={jd.id}
                      className="flex items-start gap-2 px-3 py-2.5 hover:bg-indigo-50 cursor-pointer group transition-colors"
                      onClick={() => handleLoadJd(jd)}
                    >
                      <FileText className="w-3.5 h-3.5 mt-0.5 text-indigo-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-slate-700 truncate group-hover:text-indigo-700">{jd.title || '(Không tên)'}</p>
                        <p className="text-[10px] text-slate-400 mt-0.5 truncate">{jd.preview}…</p>
                        <p className="text-[10px] text-slate-400">{new Date(jd.created_at).toLocaleDateString('vi-VN')}</p>
                      </div>
                      <button
                        onClick={(e) => handleDeleteJd(jd.id, e)}
                        className="p-1 text-slate-300 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-all flex-shrink-0"
                        title="Xóa"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </aside>

        {/* MAIN AREA (Phải) */}
        <main className="flex-1 overflow-y-auto p-6 md:p-8 bg-slate-50/50">
          <div className="max-w-6xl mx-auto space-y-8">

            {/* TABS NGUỒN DỮ LIỆU */}
            <div className="bg-white p-2 rounded-2xl border border-slate-200 shadow-sm inline-flex">
              <button
                onClick={() => setActiveTab('local')}
                className={`px-6 py-2.5 rounded-xl text-sm font-bold transition-all flex items-center gap-2 ${activeTab === 'local' ? 'bg-indigo-50 text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'}`}
              >
                <UploadCloud className="w-4 h-4" /> Tải từ máy tính
              </button>
              <button
                onClick={() => setActiveTab('gmail')}
                className={`px-6 py-2.5 rounded-xl text-sm font-bold transition-all flex items-center gap-2 ${activeTab === 'gmail' ? 'bg-blue-50 text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'}`}
              >
                <Mail className="w-4 h-4" /> Quét từ Gmail
              </button>
            </div>

            {/* TAB CONTENT */}
            {activeTab === 'local' && (
              <section className="space-y-6">
                {/* Khu vực Drag & Drop Upload */}
                <div
                  className="border-2 border-dashed border-indigo-200 bg-indigo-50/30 rounded-3xl p-10 flex flex-col items-center justify-center text-center hover:bg-indigo-50/50 transition-colors cursor-pointer group"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input
                    type="file"
                    multiple
                    accept=".pdf"
                    className="hidden"
                    ref={fileInputRef}
                    onChange={handleFileSelect}
                  />
                  <div className="w-16 h-16 bg-white rounded-2xl shadow-sm flex items-center justify-center mb-4 group-hover:scale-105 transition-transform duration-300">
                    <UploadCloud className="w-8 h-8 text-indigo-500" />
                  </div>
                  <h3 className="text-lg font-bold text-slate-800 mb-1">Kéo thả CV hoặc click để chọn</h3>
                  <p className="text-sm text-slate-500">Hỗ trợ định dạng PDF (Tối đa 10MB/file)</p>
                </div>

                {/* Quản lý Tiến trình Files */}
                {files.length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/50">
                      <h4 className="font-bold text-slate-700 text-sm">Danh sách file tải lên ({files.length})</h4>
                    </div>
                    <ul className="divide-y divide-slate-100 max-h-64 overflow-y-auto">
                      {files.map(f => (
                        <li key={f.id} className="p-4 flex items-center justify-between hover:bg-slate-50 transition-colors">
                          <div className="flex items-center gap-3 overflow-hidden">
                            <div className={`p-2 rounded-lg ${f.status === 'error' ? 'bg-rose-50 text-rose-500' : 'bg-indigo-50 text-indigo-500'}`}>
                              <FileIcon className="w-5 h-5" />
                            </div>
                            <div className="truncate">
                              <p className="text-sm font-bold text-slate-700 truncate">{f.file.name}</p>
                              <p className="text-xs text-slate-400">{(f.file.size / 1024 / 1024).toFixed(2)} MB</p>
                            </div>
                          </div>

                          <div className="flex items-center gap-4">
                            {f.status === 'idle' && <span className="text-xs font-bold text-slate-400 bg-slate-100 px-2 py-1 rounded-md">Sẵn sàng</span>}
                            {f.status === 'scanning' && (
                              <span className="text-xs font-bold text-indigo-600 bg-indigo-50 px-2 py-1 rounded-md flex items-center gap-1.5">
                                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Đang quét...
                              </span>
                            )}
                            {f.status === 'done' && (
                              <span className="text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded-md flex items-center gap-1.5">
                                <CheckCircle2 className="w-3.5 h-3.5" /> Hoàn thành
                              </span>
                            )}
                            {f.status === 'error' && (
                              <span className="text-xs font-bold text-rose-600 bg-rose-50 px-2 py-1 rounded-md flex items-center gap-1.5" title={f.errorMsg}>
                                <AlertCircle className="w-3.5 h-3.5" /> Lỗi PDF
                              </span>
                            )}

                            <button onClick={(e) => { e.stopPropagation(); removeFile(f.id); }} className="p-1.5 text-slate-400 hover:text-rose-500 hover:bg-rose-50 rounded-md transition-colors">
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            )}

            {activeTab === 'gmail' && (
              <section className="space-y-6">
                <div className="bg-white border border-slate-200 rounded-3xl p-8 flex flex-col md:flex-row items-center gap-6 shadow-sm">
                  <div className="w-16 h-16 bg-blue-50 text-blue-500 rounded-2xl flex items-center justify-center flex-shrink-0">
                    <Mail className="w-8 h-8" />
                  </div>
                  <div className="flex-1 w-full">
                    <label className="block text-sm font-bold text-slate-700 mb-2">Truy vấn tìm kiếm Email (Filter)</label>
                    <div className="flex gap-3">
                      <div className="relative flex-1">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                        <input
                          type="text"
                          className="w-full bg-slate-50 border border-slate-200 rounded-xl py-3 pl-10 pr-4 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 text-slate-700"
                          value={gmailQuery}
                          onChange={(e) => setGmailQuery(e.target.value)}
                        />
                      </div>

                      <select
                        className="bg-slate-50 border border-slate-200 rounded-xl py-3 px-4 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 text-slate-700 font-medium whitespace-nowrap"
                        value={gmailTimeRange}
                        onChange={(e) => setGmailTimeRange(e.target.value)}
                      >
                        <option value="1d">Trong 24 giờ qua</option>
                        <option value="7d">Trong 1 tuần qua</option>
                        <option value="1m">Trong 1 tháng qua</option>
                        <option value="all">Tất cả thời gian</option>
                      </select>

                      <button
                        onClick={handleFetchFromGmail}
                        disabled={gmailScanning}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-xl font-bold shadow-sm transition-all disabled:opacity-50 flex items-center gap-2 whitespace-nowrap"
                      >
                        {gmailScanning ? <Loader2 className="w-5 h-5 animate-spin" /> : <Mail className="w-5 h-5" />}
                        Kết nối Gmail
                      </button>
                    </div>
                    <p className="text-xs text-slate-500 mt-2">Hệ thống sẽ chỉ quét các email Chưa đọc (Unread) có chứa file đính kèm PDF.</p>
                  </div>
                </div>
              </section>
            )}

            {/* BẢNG KẾT QUẢ (DATA TABLE) */}
            {results.length > 0 && (
              <section className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden animate-in fade-in duration-500">
                <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                  <h3 className="font-bold text-slate-800 text-lg flex items-center gap-2">
                    <BrainCircuit className="w-5 h-5 text-indigo-600" />
                    Kết quả Ứng viên ({results.length})
                  </h3>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => {
                        if (confirm('Bạn có chắc muốn xóa toàn bộ kết quả đã lọc?')) {
                          setResults([]);
                          setFiles([]);
                        }
                      }}
                      className="text-sm font-bold text-rose-500 hover:text-rose-700 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-rose-200 bg-rose-50 shadow-sm transition-colors"
                    >
                      <Trash2 className="w-4 h-4" /> Xóa kết quả
                    </button>
                    <button
                      onClick={() => setSortOrder(prev => prev === 'none' ? 'desc' : prev === 'desc' ? 'asc' : 'none')}
                      className={`text-sm font-bold flex items-center gap-1.5 px-3 py-1.5 rounded-lg border shadow-sm transition-colors ${sortOrder !== 'none' ? 'bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100' : 'text-slate-500 hover:text-slate-800 border-slate-200 bg-white'}`}
                    >
                      {sortOrder === 'none' ? 'Sắp xếp Điểm' : sortOrder === 'desc' ? 'Điểm: Cao -> Thấp' : 'Điểm: Thấp -> Cao'} <ArrowUpDown className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-white border-b border-slate-200">
                        <th className="py-4 px-6 text-xs font-black text-slate-400 uppercase tracking-wider">Ứng viên / File</th>
                        <th className="py-4 px-6 text-xs font-black text-slate-400 uppercase tracking-wider text-center">Ngành</th>
                        <th className="py-4 px-6 text-xs font-black text-slate-400 uppercase tracking-wider text-center">Score</th>
                        <th className="py-4 px-6 text-xs font-black text-slate-400 uppercase tracking-wider text-center">Kinh nghiệm</th>
                        <th className="py-4 px-6 text-xs font-black text-slate-400 uppercase tracking-wider text-center">Trạng thái</th>
                        <th className="py-4 px-6 text-xs font-black text-slate-400 uppercase tracking-wider text-right">Hành động</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {sortedResults.map((res, i) => (
                        <tr key={i} className="hover:bg-slate-50/80 transition-colors group">
                          <td className="py-4 px-6 align-middle">
                            <p className="text-sm font-bold text-slate-800 mb-0.5">{res.candidate_name || 'Không xác định'}</p>
                            <div className="flex items-center gap-1.5 text-xs text-slate-500 font-medium mt-1">
                              <FileIcon className="w-3.5 h-3.5 text-slate-400" />
                              <span className="truncate max-w-[150px] lg:max-w-[200px]">{res.filename}</span>
                            </div>
                          </td>
                          <td className="py-4 px-6 align-middle text-center">
                            <span className="text-xs font-semibold text-slate-600 bg-slate-100 px-2 py-1 rounded-md">{res.tong_quan?.nganh_nghe || res.industry || '—'}</span>
                          </td>
                          <td className="py-4 px-6 align-middle text-center">
                            <span className="inline-flex items-center justify-center min-w-[3rem] px-2 py-1 bg-indigo-50 text-indigo-700 font-black rounded-lg border border-indigo-100">
                              {res.tong_quan?.diem_tong ?? res.score ?? 0}
                            </span>
                          </td>
                          <td className="py-4 px-6 align-middle text-center">
                            <p className="text-sm font-bold text-slate-700">{res.tong_quan?.so_nam_kinh_nghiem ?? res.candidate_years_experience ?? 0} <span className="text-xs font-normal text-slate-400">năm</span></p>
                          </td>
                          <td className="py-4 px-6 align-middle text-center">
                            {(res.tong_quan?.quyet_dinh || res.final_decision) === 'ĐẠT' || (res.tong_quan?.quyet_dinh || res.final_decision) === 'PASS' ? (
                              <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-emerald-50 text-emerald-700 text-xs font-bold rounded-full border border-emerald-200">
                                <CheckCircle2 className="w-3.5 h-3.5" /> ĐẠT
                              </span>
                            ) : (res.tong_quan?.quyet_dinh || res.final_decision) === 'CHỜ XEM XÉT' || (res.tong_quan?.quyet_dinh || res.final_decision) === 'PENDING' ? (
                              <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-50 text-amber-700 text-xs font-bold rounded-full border border-amber-200">
                                <Loader2 className="w-3.5 h-3.5" /> CHỜ XEM XÉT
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-rose-50 text-rose-700 text-xs font-bold rounded-full border border-rose-200">
                                <XCircle className="w-3.5 h-3.5" /> KHÔNG ĐẠT
                              </span>
                            )}
                          </td>
                          <td className="py-4 px-6 align-middle text-right">
                            <div className="flex items-center justify-end gap-3">
                              {/* 
                                BUSINESS LOGIC UPDATE:
                                - If status = "PASS" or "REVIEW" -> SHOW (Gửi mail phỏng vấn / điền form)
                                - If status = "FAIL" -> HIDE
                              */}
                              {((res.tong_quan?.quyet_dinh || res.final_decision) === 'ĐẠT' || (res.tong_quan?.quyet_dinh || res.final_decision) === 'PASS' || (res.tong_quan?.quyet_dinh || res.final_decision) === 'CHỜ XEM XÉT') && (
                                <button
                                  onClick={() => handleSendEmail(res)}
                                  className="inline-flex items-center gap-1.5 text-xs font-bold bg-gradient-to-r from-indigo-500 to-blue-600 text-white hover:from-indigo-600 hover:to-blue-700 px-4 py-2 rounded-lg transition-all shadow border border-transparent hover:shadow-indigo-500/25 active:scale-95"
                                >
                                  <Mail className="w-3.5 h-3.5" /> Gửi Mail
                                </button>
                              )}
                              <button
                                onClick={() => setSelectedResult(res)}
                                className="inline-flex items-center gap-1.5 text-sm font-bold text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 px-3 py-2 rounded-lg transition-all"
                              >
                                Chi tiết <ExternalLink className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

          </div>
        </main>
      </div>

      {/* RENDER MODAL */}
      <ResultDrawer
        isOpen={selectedResult !== null}
        onClose={() => setSelectedResult(null)}
        data={selectedResult}
      />

    </div>
  );
}
