# Chương 1. Giới thiệu

## 1.1 Đặt vấn đề

Trong thời đại số, việc tạo câu hỏi trắc nghiệm tự động từ tài liệu học thuật là một nhu cầu quan trọng cho nội dung giảng dạy và đánh giá năng lực. QuizGenApp ra đời để giải quyết vấn đề chuyển đổi PDF học thuật thành bộ câu hỏi trắc nghiệm chất lượng mà không phụ thuộc vào dịch vụ LLM bên ngoài.

## 1.2 Mục tiêu đề tài

Mục tiêu của đề tài là xây dựng một hệ thống tự động tạo quiz từ PDF bằng cách kết hợp các kỹ thuật trích xuất văn bản, RAG, và kiến trúc đa tác tử. Hệ thống cần đảm bảo khả năng hoạt động nội bộ, kiểm soát chất lượng câu hỏi và xuất kết quả rõ ràng.

## 1.3 Phạm vi nghiên cứu

Phạm vi của báo cáo tập trung vào:
- Trích xuất nội dung PDF thành Markdown.
- Xây dựng chỉ mục RAG và truy vấn ngữ cảnh nguồn.
- Thiết kế các agent chuyên biệt cho sinh câu hỏi, xác minh và giải thích.
- Triển khai backend bằng FastAPI và frontend bằng Next.js.
- Sử dụng Ollama làm nền tảng LLM nội bộ.

## 1.4 Cấu trúc báo cáo

Báo cáo gồm sáu chương:
- Chương 1: Giới thiệu chung và định hướng nghiên cứu.
- Chương 2: Cơ sở lý thuyết và công nghệ sử dụng.
- Chương 3: Phân tích và thiết kế hệ thống.
- Chương 4: Xây dựng và triển khai hệ thống.
- Chương 5: Thực nghiệm và đánh giá.
- Chương 6: Kết luận và hướng phát triển.

# Chương 2. Cơ sở lý thuyết và công nghệ sử dụng

## 2.1 Large Language Models

Large Language Models là nền tảng cho việc sinh nội dung ngôn ngữ tự nhiên trong hệ thống. QuizGenApp sử dụng mô hình nội bộ thông qua Ollama với model `qwen3:4b`.

## 2.2 Retrieval-Augmented Generation

Retrieval-Augmented Generation (RAG) là phương pháp kết hợp truy vấn tài liệu nguồn với quá trình sinh văn bản để cải thiện tính chính xác. Hệ thống sử dụng RAGIndexer để tạo chỉ mục embedding và truy vấn các đoạn văn bản liên quan.

## 2.3 Multi-Agent Systems

Kiến trúc đa tác tử cho phép phân chia nhiệm vụ thành các agent độc lập nhưng phối hợp. QuizGenApp định nghĩa các agent chuyên biệt như CuratorAgent, PedagogueAgent, AdversaryAgent và ExplainerAgent, mỗi agent đảm nhiệm một phần của pipeline.

## 2.4 Ollama

Ollama là nền tảng chạy LLM nội bộ trong hệ thống. LLMProvider quản lý kết nối và chuẩn bị model để giảm thiểu chi phí khởi tạo và giữ phiên làm việc ổn định.

## 2.5 FAISS

FAISS là thư viện chỉ mục vector dùng để lưu trữ embedding và truy vấn tương tự. RAGIndexer sử dụng FAISS `IndexFlatIP` cùng cosine similarity để tìm các đoạn nội dung liên quan.

## 2.6 FastAPI

FastAPI được chọn làm framework backend cho API của hệ thống. Backend cung cấp các endpoint upload PDF, truy vấn trạng thái và lấy kết quả quiz.

## 2.7 Next.js

Frontend được xây dựng bằng Next.js, kết hợp React và TypeScript để tạo giao diện người dùng cho upload tệp, cấu hình pipeline và hiển thị kết quả.

# Chương 3. Phân tích và thiết kế hệ thống

## 3.1 Kiến trúc tổng thể

Hệ thống được thiết kế theo mô hình local-first, bao gồm backend Python và frontend Next.js. Toàn bộ quá trình xử lý tài liệu và sinh câu hỏi diễn ra trong môi trường nội bộ, không phụ thuộc API bên ngoài.

[Hình 3.1: Kiến trúc tổng thể của hệ thống]

## 3.2 Luồng xử lý

Luồng xử lý chính của QuizGenApp gồm các bước sau:
1. Trích xuất PDF sang Markdown.
2. Chia tài liệu thành chunks và xây dựng chỉ mục RAG.
3. CuratorAgent tạo knowledge bricks.
4. PedagogueAgent sinh câu hỏi ứng viên theo ba giai đoạn.
5. AdversaryAgent chấm điểm và lọc câu hỏi.
6. AnswerConsistencyValidator kiểm tra sự nhất quán.
7. ExplainerAgent sinh giải thích cuối cùng.
8. Lưu trữ kết quả và metrics.

[Hình 3.2: Luồng xử lý sinh câu hỏi]

## 3.3 Thiết kế các thành phần chính

### 3.3.1 PDFExtractor

PDFExtractor (`backend/utils/text_extractor.py`) chịu trách nhiệm trích xuất nội dung từ PDF sang Markdown. Có hai phương thức chính:
- `fast_extract()`: sử dụng PyMuPDF (`fitz`) để lấy text cơ bản.
- `precision_extract()`: sử dụng Marker OCR khi kết quả fast extract không đủ.

Trong chế độ accuracy, hệ thống ưu tiên `fast_extract()` nếu kết quả đủ dài và không chứa LaTeX/math, còn lại sẽ chuyển sang `precision_extract()`.

### 3.3.2 RAGIndexer

RAGIndexer (`backend/utils/rag.py`) đảm nhiệm chia nhỏ tài liệu thành chunks, tạo embedding với `sentence-transformers/all-MiniLM-L6-v2` và lưu trữ trong FAISS `IndexFlatIP`. Các hàm truy vấn gồm `retrieve()` và `retrieve_with_ids()` để hỗ trợ truy xuất nguồn.

### 3.3.3 CuratorAgent

CuratorAgent (`backend/curator.py`) chuyển Markdown thành knowledge bricks có cấu trúc. Quá trình gồm truy vấn RAG, gom batches, gọi LLM song song và parse JSON để xây dựng các khối tri thức.

### 3.3.4 PedagogueAgent

PedagogueAgent (`backend/pedagogue.py`) sinh câu hỏi trắc nghiệm qua ba giai đoạn:
- Stage A: sinh câu hỏi và tùy chọn.
- Stage B: xác minh đáp án.
- Stage C: sinh giải thích.

Agent thực hiện overgeneration bằng cách tạo nhiều câu hỏi ứng viên rồi lọc lại, đồng thời áp dụng retry khi JSON parse thất bại.

### 3.3.5 AdversaryAgent

AdversaryAgent (`backend/adversary.py`) chấm điểm câu hỏi theo rubic gồm factual correctness, source support, clarity và difficulty/quality. Chỉ những câu hỏi đạt ngưỡng mới được giữ lại.

### 3.3.6 AnswerConsistencyValidator

AnswerConsistencyValidator (`backend/validators.py`) kiểm tra cấu trúc câu hỏi bao gồm số lượng options, tính nhất quán đáp án và định dạng giải thích. Khi có source_chunks, validator còn kiểm tra hỗ trợ nguồn và tương quan giữa giải thích và nguồn.

### 3.3.7 ExplainerAgent

ExplainerAgent (`backend/explainer.py`) sinh giải thích chi tiết cho câu hỏi đã qua vòng đánh giá. Thành phần này chỉ hoạt động trong chế độ accuracy và bỏ qua trong fast mode.

### 3.3.8 LLMProvider

LLMProvider (`backend/llm_provider.py`) quản lý kết nối chung tới Ollama, bao gồm kiểm tra availability, giữ phiên model và hỗ trợ gọi hàng loạt prompt song song.

### 3.3.9 MetricsCollector

MetricsCollector (`backend/utils/metrics.py`) thu thập các chỉ số pipeline như thời gian xử lý, latency LLM, ước tính token và số lượng câu hỏi. Kết quả lưu dưới `outputs/metrics.json`.

## 3.4 Thiết kế API

Backend API được triển khai trong `api.py` với các endpoint:
- `POST /generate`: upload PDF và bắt đầu job nền.
- `GET /status/{job_id}`: truy vấn trạng thái.
- `GET /result/{job_id}`: lấy kết quả quiz.

API lưu trạng thái job trong bộ nhớ và sử dụng FastAPI BackgroundTasks để chạy pipeline bất đồng bộ.

## 3.5 Thiết kế frontend

Frontend trong `frontend/` gồm các thành phần giao diện chính:
- `UploadZone`
- `QuizForm`
- `PipelineStatus`
- `LogsPanel`
- `QuizViewer`
- `ExportButtons`

Frontend sử dụng Zustand để quản lý state và Axios để gọi API. Giao diện hỗ trợ hiển thị tiến độ, log và kết quả markdown.

[Hình 3.3: Kiến trúc Multi-Agent]

# Chương 4. Xây dựng và triển khai hệ thống

## 4.1 Cấu trúc mã nguồn

Dự án tổ chức theo cấu trúc:
- `main.py`: entry point CLI.
- `api.py`: backend FastAPI.
- `config.ini`: cấu hình pipeline.
- `backend/`: các agent và tiện ích.
- `frontend/`: ứng dụng Next.js.
- `outputs/`: file kết quả.

## 4.2 Triển khai backend

Backend sử dụng Python và các thư viện cần thiết bao gồm FastAPI, PyMuPDF, Marker OCR, torch, ollama, sentence-transformers và FAISS.

## 4.3 Triển khai frontend

Frontend sử dụng Node.js, Next.js, React và TypeScript. Ứng dụng giao tiếp với backend qua Axios và các endpoint FastAPI.

## 4.4 Cấu hình pipeline

Các tham số cấu hình lưu trong `config.ini`, như `embedding_model`, `chunk_size`, `chunk_overlap` và `top_k`.

## 4.5 Chạy hệ thống

Hệ thống có thể khởi chạy qua CLI `main.py` hoặc API FastAPI `api.py`. CLI tự động tìm file PDF đầu tiên trong thư mục hiện tại và xuất kết quả vào `outputs/Generated_Quiz.md`.

## 4.6 Ghi nhận và lưu trữ kết quả

Kết quả đầu ra bao gồm các file:
- `outputs/Generated_Quiz.md`
- `outputs/metrics.json`
- `outputs/knowledge_bricks.json`
- `outputs/adversary_scored.json`
- `outputs/final_quiz.json`

[Hình 4.1: Giao diện người dùng]

# Chương 5. Thực nghiệm và đánh giá

## 5.1 Môi trường thực nghiệm

- Phần cứng: [TODO]
- Phần mềm: Python 3.12+, Node.js LTS, Ollama, CUDA nếu có
- Thư viện chính: FastAPI, Next.js, sentence-transformers, FAISS, PyMuPDF, Marker OCR
- Thiết lập GPU: `setup_gpu.ps1`

## 5.2 Bộ dữ liệu đánh giá

- Dữ liệu đầu vào: PDF học thuật
- Tiêu chí chọn tài liệu: [TODO]
- Số lượng bộ dữ liệu thử nghiệm: [TODO]

## 5.3 Kết quả thực nghiệm

Các đầu ra thu được từ thực nghiệm sẽ được tổng hợp và phân tích trong báo cáo:

| Chỉ số                    | Giá trị |
| ------------------------- | ------- |
| Thời gian xử lý           | [TODO]  |
| Tỷ lệ chấp nhận           | [TODO]  |
| Điểm Adversary trung bình | [TODO]  |
| Số lượng câu hỏi tạo ra    | [TODO]  |

## 5.4 Phân tích kết quả

- Đánh giá tính đúng đắn của pipeline RAG và multi-agent.
- So sánh đặc điểm của chế độ `fast` và `accuracy`.
- Nhận xét về cơ chế retry và xử lý JSON không hợp lệ.
- Phân tích các hạn chế dựa trên thực nghiệm.

## 5.5 Hạn chế của hệ thống

- Job storage in-memory làm mất trạng thái khi restart server.
- Không có cơ chế fallback model khi `qwen3:4b` không khả dụng.
- ExplainerAgent bị bỏ qua trong chế độ `fast`.
- Chưa có đánh giá người dùng hoặc bộ dữ liệu thử nghiệm rộng.
- [TODO: Bổ sung hạn chế kỹ thuật cụ thể sau khi thực nghiệm]

# Chương 6. Kết luận và hướng phát triển

## 6.1 Kết luận

QuizGenApp là hệ thống tự động tạo câu hỏi trắc nghiệm từ PDF học thuật bằng kiến trúc multi-agent và RAG. Hệ thống thể hiện khả năng vận hành nội bộ và kiểm soát chất lượng câu hỏi thông qua nhiều bước xác minh.

## 6.2 Hướng phát triển

Các hướng phát triển tiếp theo gồm:
- Thực hiện fallback model hoặc model swap.
- Cải thiện OCR và trích xuất PDF.
- Mở rộng frontend và hỗ trợ nhiều định dạng đầu vào.
- Xây dựng cơ chế lưu trữ job bền vững.
- Bổ sung đánh giá chất lượng thực nghiệm và phản hồi người dùng.

## 6.3 Tổng kết

QuizGenApp minh họa khả năng kết hợp Ollama, FastAPI và Next.js để xây dựng hệ thống sinh quiz tự động nội bộ. Báo cáo cung cấp khung nền tảng để hoàn thiện và mở rộng hệ thống trong nghiên cứu tiếp theo.
