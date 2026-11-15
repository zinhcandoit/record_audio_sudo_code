# HỆ THỐNG THU ÂM TELESALE & ĐÁNH GIÁ GIỌNG NỮ BẮC (NỮ 1 & NỮ 2)

Hệ thống web thu âm dành riêng cho người đọc giọng **Nữ Bắc 1** và **Nữ Bắc 2** dựa trên tập kịch bản hội thoại chuẩn [`telesale_cases_full.json`](data/telesale_cases_full.json). Ứng dụng tích hợp nhận dạng giọng nói ASR bằng **OpenAI Whisper API**, tự động chuẩn hóa văn bản tiếng Việt, tính điểm tương đồng **RapidFuzz** và tốc độ đọc **WPM** (Words Per Minute) để thẩm định chất lượng bản thu trước khi lưu trữ vào MongoDB.

---

## 1. Tính Năng & Luồng Hoạt Động

1. **Lựa chọn giọng đọc**: Người dùng chọn **Nữ 1** hoặc **Nữ 2** (hỗ trợ cả Nữ 3, Nam 3 nếu cần).
2. **Hiển thị kịch bản trực quan**:
   - Từng lượt thoại hiển thị rõ mã Dialogue (`D01`, `D02`...), số thứ tự lượt thoại, vai (`Khách hàng` / `Tư vấn viên`), phương ngữ và tên file chuẩn.
   - Text kịch bản được định dạng chữ to, rõ ràng, dễ đọc.
3. **Thu âm chuyên nghiệp với Waveform & Timer**:
   - Khi bấm "Bắt đầu thu âm", bộ đếm thời gian (`MM:SS`) chạy theo thời gian thực.
   - Cột sóng âm (**Live Waveform**) hiển thị động trên Canvas theo âm lượng và tần số giọng nói, giúp người thu âm biết chắc chắn mic đang hoạt động tốt.
   - Hỗ trợ nghe lại ngay sau khi thu âm.
4. **Kiểm tra chất lượng nghiêm ngặt (3 Tiêu chí)** khi bấm **"Xác nhận & Kiểm tra toàn bộ"**:
   - **Đầy đủ**: Bắt buộc thu âm 100% các đoạn được phân công (không bỏ sót đoạn nào).
   - **ASR & RapidFuzz Score**: Nhận dạng âm thanh bằng OpenAI Whisper (`whisper-1`) và so sánh với kịch bản gốc. Đoạn thoại chỉ đạt khi **Score ≥ 0.85 (85%)**.
   - **Tốc độ đọc WPM**: Tính WPM theo chuẩn bộ đếm tiếng Việt (số âm tiết / thời lượng giây * 60). Đoạn thoại chỉ đạt khi **WPM ≥ 4.0**.
5. **Cơ chế Khóa & Thu lại thông minh**:
   - **Đoạn đã đạt**: Hệ thống tự động **KHÓA** (không cho ghi đè), hiển thị huy hiệu xanh `✓ Đạt chuẩn (Locked)`, điểm tương đồng, WPM và lời nhận dạng ASR.
   - **Đoạn chưa đạt**: Báo lỗi cụ thể (ví dụ: điểm thấp hoặc tốc độ quá chậm), yêu cầu người dùng thu âm lại.
   - Người dùng bấm "Xác nhận & Kiểm tra" lần nữa để thẩm định lại các đoạn chưa đạt cho đến khi hoàn thành 100%.
6. **Lưu trữ MP3 chuẩn vào MongoDB GridFS**:
   - Audio được chuyển đổi tự động sang chuẩn **MP3 (16kHz Mono 128kbps)**.
   - Đặt tên file theo cú pháp bắt buộc: `D<XX>_YY_<gender>_<region>_<role>.mp3`.

---

## 2. Bảng Phân Công Vai Đọc (Khớp 100% Kịch Bản)

| Giọng | Giới tính | Vùng miền | Vai đọc | Số lượt | Dải file audio |
|---|---|---|---|:---:|---|
| **Nữ 1** | Nữ (`f`) | Bắc (`bac`) | Khách ở D01 và D02 (cùng một người) | **9 lượt** | `D01_02`, `D01_04`, `D01_06`, `D01_08`, `D01_10`, `D02_01`, `D02_03`, `D02_05`, `D02_07` |
| **Nữ 2** | Nữ (`f`) | Bắc (`bac`) | Tư vấn viên D01, D03 · Khách D04 | **13 lượt** | `D01_01`, `D01_03`, `D01_05`, `D01_07`, `D01_09`, `D03_02`, `D03_04`, `D03_06`, `D03_08`, `D04_01`, `D04_03`, `D04_05`, `D04_07` |
| **Nữ 3** | Nữ (`f`) | Nam (`nam`) | Tư vấn viên D02, D04 | 7 lượt | `D02_02`, `D02_04`, `D02_06`, `D02_08`, `D04_02`, `D04_04`, `D04_06` |
| **Nam 3** | Nam (`m`) | Trung (`trung`) | Khách D03 | 5 lượt | `D03_01`, `D03_03`, `D03_05`, `D03_07`, `D03_09` |

### Quy cách đặt tên file âm thanh:
```text
D<XX>_YY_<f/m>_<bac/trung/nam>_<customer_agent>.mp3
```
- **Ví dụ Nữ 1**: `D01_02_f_bac_customer.mp3`, `D02_01_f_bac_customer.mp3`
- **Ví dụ Nữ 2**: `D01_01_f_bac_agent.mp3`, `D03_02_f_bac_agent.mp3`, `D04_01_f_bac_customer.mp3`

---

## 3. Kiến Trúc Tách Biệt Cơ Sở Dữ Liệu (MongoDB)

Nhằm đảm bảo tính độc lập và toàn vẹn dữ liệu, hệ thống phân tách thành 2 cơ sở dữ liệu riêng biệt:

1. **`DB_NAME_SCRIPTS` (Mặc định: `telesale_scripts_db`)**:
   - Collection `dialogues`: Lưu toàn bộ 284+ kịch bản đối thoại từ `telesale_cases_full.json`.
   - Collection `assignments`: Lưu cấu hình phân công vai đọc cho Nữ 1, Nữ 2, Nữ 3, Nam 3.
2. **`DB_NAME_RECORDINGS` (Mặc định: `telesale_recordings_db`)**:
   - Bucket `fs.files` & `fs.chunks` (MongoDB GridFS): Lưu trữ file nhị phân âm thanh định dạng `.mp3`.
   - Collection `recordings`: Lưu metadata chi tiết của từng bản thu:
     ```json
     {
       "filename": "D01_02_f_bac_customer.mp3",
       "reader_id": "nu_1",
       "reader_name": "Nữ 1 (Bắc)",
       "dialogue_id": "D01",
       "turn_idx": 2,
       "speaker": "C",
       "role": "customer",
       "gender": "f",
       "region": "bac",
       "ground_truth_text": "alo, chị muốn hỏi máy lọc không khí...",
       "asr_transcript": "alo chị muốn hỏi máy lọc không khí...",
       "rapidfuzz_score": 0.942,
       "wpm": 185.4,
       "word_count": 19,
       "duration_seconds": 6.15,
       "gridfs_id": "6736...",
       "status": "passed",
       "updated_at": "2026-11-15T..."
     }
     ```

> **Lưu ý Fallback:** Nếu chưa cấu hình MongoDB, hệ thống sẽ tự động chuyển sang chế độ **Local Storage** (`storage/mp3/` và `storage/recordings.json`) mà không bị crash web.

---

## 4. Hướng Dẫn Cấu Hình Biến Môi Trường (`.env`)

Tạo file `.env` tại thư mục gốc `nu_thu_am/` dựa trên mẫu [`.env.example`](.env.example):

```env
# 1. OpenAI Whisper API Key (Bắt buộc cho ASR)
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 2. Kết nối MongoDB Atlas hoặc Local
MONGODB_URI=mongodb+srv://<username>:<password>@cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority

# 3. Hai cơ sở dữ liệu tách biệt
DB_NAME_SCRIPTS=telesale_scripts_db
DB_NAME_RECORDINGS=telesale_recordings_db

# 4. Ngưỡng kiểm tra
RAPIDFUZZ_SCORE_THRESHOLD=0.85
WPM_MIN_THRESHOLD=4.0

# 5. Cổng dịch vụ
PORT=8000
HOST=0.0.0.0
```

---

## 5. Hướng Dẫn Chạy Cục Bộ (Local)

### Bước 1: Cài đặt thư viện Python
Yêu cầu Python 3.10 trở lên và FFmpeg (đã có sẵn trong Windows PATH hoặc package `imageio-ffmpeg`).

```bash
cd nu_thu_am
pip install -r requirements.txt
```

### Bước 2: Tạo file `.env`
Sao chép `.env.example` thành `.env` và điền `OPENAI_API_KEY` cùng `MONGODB_URI`.

### Bước 3: Khởi chạy ứng dụng
```bash
python run.py
```
Hoặc:
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

Truy cập trình duyệt: **`http://localhost:8000`**

---

## 6. Hướng Dẫn Triển Khai Lên Render (Render.com)

Render hỗ trợ triển khai cả Frontend lẫn Backend trong **1 Web Service duy nhất** rất tiết kiệm và tiện lợi:

### Cách 1: Sử dụng Native Python Runtime (Khuyên dùng)
1. Đẩy mã nguồn thư mục `nu_thu_am` lên GitHub / GitLab repository.
2. Đăng nhập vào [Render Dashboard](https://dashboard.render.com).
3. Chọn **New +** $\rightarrow$ **Web Service**.
4. Kết nối tới Git repository của bạn.
5. Cấu hình các thông số:
   - **Name**: `nu-thu-am-telesale`
   - **Root Directory**: `nu_thu_am` (hoặc để trống nếu repo ở root)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
6. Trong mục **Environment Variables**, thêm:
   - `OPENAI_API_KEY`: *(Key OpenAI của bạn)*
   - `MONGODB_URI`: *(URI kết nối MongoDB Atlas)*
   - `DB_NAME_SCRIPTS`: `telesale_scripts_db`
   - `DB_NAME_RECORDINGS`: `telesale_recordings_db`
7. Nhấn **Deploy Web Service**.

### Cách 2: Sử dụng Docker trên Render
Repository đã tích hợp sẵn [`Dockerfile`](Dockerfile) có cài sẵn `ffmpeg`. Render sẽ tự động phát hiện và build container.

---

## 7. Hướng Dẫn Tạo MongoDB Atlas (Miễn phí)

1. Truy cập [mongodb.com/atlas](https://www.mongodb.com/cloud/atlas) và đăng ký tài khoản miễn phí.
2. Tạo 1 Cluster **M0 Free Tier** (chọn khu vực Singapore hoặc gần bạn nhất).
3. Tại **Database Access**: Tạo người dùng (Username & Password).
4. Tại **Network Access**: Thêm IP `0.0.0.0/0` (Allow Access from Anywhere) để Render có thể kết nối.
5. Bấm **Connect** $\rightarrow$ **Drivers (Python)** $\rightarrow$ Sao chép chuỗi kết nối dán vào `MONGODB_URI` trong file `.env`.

---

## 8. Danh Sách API (RESTful Endpoints)

| Phương thức | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/` | Giao diện web người dùng (HTML/JS/CSS) |
| `GET` | `/api/system/status` | Kiểm tra trạng thái MongoDB, OpenAI API và FFmpeg |
| `GET` | `/api/readers` | Danh sách người đọc (`nu_1`, `nu_2`...) |
| `GET` | `/api/readers/{id}/turns` | Danh sách câu thoại & trạng thái thu âm |
| `POST` | `/api/verify/turn` | Tải lên audio, chạy Whisper ASR, tính RapidFuzz, WPM và lưu MongoDB |
| `GET` | `/api/verify/status/{id}` | Kiểm tra tiến độ hoàn thành các lượt |
| `GET` | `/api/recordings/{filename}` | Nghe / Stream trực tiếp file MP3 từ MongoDB GridFS |
| `GET` | `/api/recordings/export/zip` | Tải trọn bộ các file MP3 và metadata dưới dạng ZIP |
| `POST` | `/api/recordings/reset/{id}` | Xóa bản thu để thu âm lại từ đầu |

