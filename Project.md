# Tài Liệu Giải Thích Dự Án: QuizGenApp (Multi-Agent AI Quiz Generator)

## 1. Tổng Quan Dự Án (Overview)
**QuizGenApp** là một hệ thống AI đa tác tử (Multi-Agent System) thiết kế để chạy hoàn toàn ở môi trường nội bộ cục bộ (local-first), không phụ thuộc vào các API bên ngoài như OpenAI/Anthropic. Trọng tâm của ứng dụng là **tự động chuyển đổi các tài liệu học thuật (file PDF slide/bài giảng) thành các bài trắc nghiệm (quiz) chất lượng cao và có xác thực.**

Dự án được tối ưu để hoạt động tốt trên các phần cứng phổ thông (đặc biệt là GPU có khoảng 4GB VRAM). Việc chia tay nhiệm vụ cho nhiều "đặc vụ" (Agent) chuyên biệt giúp tăng độ chính xác lý luận và giảm thiểu tình trạng "ảo giác" (hallucination) thường gặp ở các LLM.

---

## 2. Kiến Trúc và Luồng Xử Lý (Pipeline)
Dự án được thiết kế theo dạng chuỗi xử lý (pipeline) đi qua 5 giai đoạn chính. Mỗi giai đoạn được đảm nhận bởi một Agent/Module chuyên biệt:

1. **Extraction (Trích xuất):** Đọc nội dung file PDF đầu vào và chuyển đổi thành định dạng cấu trúc Markdown để AI dễ hiểu. 
2. **Curator (Giám tuyển):** Trích lọc các khái niệm, kiến thức cốt lõi ("knowledge bricks") trong Markdown và loại bỏ các phần râu ria vô ích.
3. **Pedagogue (Giảng viên):** Dựa vào tập hợp knowledge bricks trên để sinh ra các câu hỏi trắc nghiệm (Multiple-Choice Questions) mang tính sư phạm.
4. **Adversary (Phản biện/Kiểm định):** Đóng vai trò kiểm tra chéo (Cross-Validation). Agent này đố chiếu các câu hỏi được sinh ra với tài liệu gốc để phát hiện và đánh dấu (flag) hoặc loại bỏ câu hỏi sai lệch.
5. **Explainer (Giải thích):** Dựa trên bộ câu hỏi đã qua kiểm duyệt, tiến hành tạo lời giải thích chi tiết, cặn kẽ tại sao đáp án lại đúng (hoặc các đáp án kia sai).

Kết quả cuối cùng là file bài thi hoàn chỉnh lưu lại tại `outputs/Generated_Quiz.md`.

---

## 3. Chi Tiết Các Chế Độ Chạy (Modes)
Dự án cung cấp 2 chế độ xử lý linh hoạt:
- **Chế độ `accuracy` (Mặc định):** Đảm bảo tính chính xác cao. Khởi đầu với trích xuất nhanh (fast-extract), và nếu văn bản có vẻ chứa các công thức toán/LaTeX hoặc quá ngắn, nó sẽ tự động kích hoạt `precision-extract` độ chính xác cao.
- **Chế độ `fast` (Nhanh):** Bỏ qua hoàn toàn bước `precision-extract` để tiết kiệm thời gian và tài nguyên, phù hợp cho văn bản chữ thông thường và cần tốc độ.

---

## 4. Cấu Trúc Thư Mục (Codebase Layout)

```text
QuizGenApp/
├── main.py                # Điểm khởi chạy qua dòng lệnh CLI (Thực thi luồng Pipeline).
├── api.py                 # File cung cấp API cho Frontend giao tiếp bằng FastAPI.
├── config.ini             # File cấu hình tên các Model sẽ dùng cho từng Agent.
├── README.MD              # Tài liệu tiếng Anh tổng quan của dự án.
├── Project.md             # Tài liệu tiếng Việt giải thích dự án chi tiết.
├── requirements.txt       # Danh sách các thư viện Python cần thiết cho Backend.
├── setup_gpu.ps1          # Script hỗ trợ setup cho môi trường GPU.
├── backend/               # Thư mục mã nguồn chính (AI Backend), chứa mô hình Agent
│   ├── adversary.py       # Agent đối kháng (Kiểm duyệt câu hỏi).
│   ├── curator.py         # Agent tổng hợp và trích xuất ý chính.
│   ├── explainer.py       # Agent tạo câu giải thích.
│   ├── pedagogue.py       # Agent ra đề thi.
│   └── utils/             # Các lớp tiện ích xử lý.
│       ├── markdown_cleaner.py  # Công cụ dọn dẹp định dạng MD.
│       └── text_extractor.py    # Module Parse PDF sang Markdown chuyên nghiệp.
├── frontend/              # Thư mục mã nguồn giao diện web (Next.js)
│   ├── package.json       # Danh sách các thư viện Node.js cần thiết.
│   ├── public/            # Thư mục chứa tài nguyên tĩnh (hình ảnh, icon).
│   └── src/               # Thư mục chứa code chính của frontend (components, pages).
└── outputs/               # Thư mục chứa bài Quiz thành phẩm và file Debug.
```

---

## 5. Yêu Cầu Kỹ Thuật (Requirements)
*   **Ngôn ngữ Backend:** Python 3.12+ trở lên.
*   **Ollama:** Cần tải và khởi chạy [Ollama](https://ollama.com/) (LLM engine nội bộ) làm nền tảng chạy Model.
*   **Models:** Các model cần được tải thủ công vào Ollama trước khi chạy (Vd: `qwen3:1.7b`, `llama3.2:3b`, `phi4-mini:latest`).
*   **Ngôn ngữ Frontend:** Node.js LTS (Mới nhất) và npm.
*   **Phần cứng mặc định:** Đề xuất có GPU NVIDIA mạnh (Tuy nhiên cấu hình gốc đã cân nhắc đến 4GB VRAM).

---

## 6. Hướng Dẫn Sử Dụng Nhanh (Usage)

### 6.1. Chuẩn bị Backend (Python)
**Bước 1: Khởi động và chuẩn bị Ollama**
Bạn phải đảm bảo Ollama đang chạy. Kéo các Model được khai báo trong `config.ini`:
```bash
ollama pull qwen3:1.7b
ollama pull llama3.2:3b
```

**Bước 2: Cài đặt thư viện Python**
Kích hoạt môi trường ảo (`venv_gpu`) và cài dependencies:
```bash
pip install -r requirements.txt
```

**Bước 3: Khởi chạy Backend API**
Mở một Terminal, kích hoạt môi trường ảo và chạy:
```bash
python -m uvicorn api:app --reload --port 8000
```
*(Backend sẽ chạy ở địa chỉ `http://localhost:8000`)*

### 6.2. Chuẩn bị Frontend (Next.js)
**Bước 1: Cài đặt thư viện**
Mở một Terminal mới (khác Terminal chạy Backend) và di chuyển vào thư mục frontend:
```bash
cd frontend
npm install
```

**Bước 2: Khởi chạy Frontend**
Khởi động giao diện UI:
```bash
npm run dev
```
Truy cập trình duyệt web tại địa chỉ: **http://localhost:3000** để sử dụng ứng dụng.

### 6.3. Chạy qua dòng lệnh thay vì UI (CLI Mode - Tùy chọn)
Nếu bạn không muốn mở giao diện web mà muốn dùng script trực tiếp. Chuẩn bị tài liệu bằng cách chép **duy nhất 01 file PDF** vào thư mục gốc của dự án (`QuizGenApp/`), sau đó chạy lệnh mặc định:

*   Để chạy lấy độ chính xác tối đa:
    ```bash
    python main.py
    ```
*   Để chạy nhanh và chỉ định tạo 20 câu hỏi:
    ```bash
    python main.py --mode fast --num 20
    ```
Bài trắc nghiệm cuối cùng cùng lời giải thích sẽ được hệ thống trả về và lưu ở `outputs/Generated_Quiz.md`.
