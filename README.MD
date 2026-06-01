# QuizGenApp — Multi-Agent AI Quiz Generator

## Overview

QuizGenApp is a local-first, multi-agent system that converts academic PDF documents into validated multiple-choice quizzes. It runs entirely on local hardware using [Ollama](https://ollama.com/) as the LLM backend — no external API keys required.

The system uses a pipeline of specialized agents, each responsible for one stage of quiz generation. This separation reduces hallucination and improves answer reliability compared to a single-prompt approach.

---

## Architecture

The pipeline has six sequential phases:

```
PDF File
   │
   ▼
[PDFExtractor]  ──fast or precision──►  Raw Markdown
   │
   ▼
[RAGIndexer]  ──chunk + embed──►  FAISS Index (or keyword fallback)
   │
   ▼
[CuratorAgent]  ──RAG-grounded extraction──►  Knowledge Bricks (JSON + Markdown)
   │
   ▼
[PedagogueAgent]  ──three-stage generation──►  Candidate Questions
   │   Stage A: Generate question + options (parallel batches)
   │   Stage B: Verify correct answer independently from source
   │   Stage C: Generate explanation from verified answer
   ▼
[AdversaryAgent]  ──batch scoring (0–100)──►  Validated Questions
   │   Accepts only questions above acceptance_threshold (default 60)
   ▼
[AnswerConsistencyValidator]  ──structural checks──►  Consistency-Filtered Questions
   │
   ▼
[ExplainerAgent]  ──batch explanations──►  Final Quiz with Explanations
   │   (skipped entirely in fast mode)
   ▼
[MetricsCollector]  ──save stats──►  outputs/metrics.json
   │
   ▼
outputs/Generated_Quiz.md
```

All agents share a single `LLMProvider` instance using one model (default: `qwen3:4b`).

---

## Pipeline Stages

| Phase | Component | File | Description |
|---|---|---|---|
| 1 | PDFExtractor | `backend/utils/text_extractor.py` | Extracts text from PDF via fitz (fast) or Marker OCR (precision) |
| 2 | RAGIndexer | `backend/utils/rag.py` | Chunks document, builds FAISS index with sentence-transformers embeddings |
| 3 | CuratorAgent | `backend/curator.py` | Extracts structured knowledge bricks via RAG-grounded LLM calls |
| 4 | PedagogueAgent | `backend/pedagogue.py` | Three-stage MCQ generation (question → answer → explanation) |
| 5 | AdversaryAgent | `backend/adversary.py` | Scores questions 0–100, rejects below threshold |
| 5.5 | AnswerConsistencyValidator | `backend/validators.py` | Structural validation of answer/explanation/option consistency |
| 6 | ExplainerAgent | `backend/explainer.py` | Generates final explanations for accepted questions (accuracy mode only) |
| 7 | MetricsCollector | `backend/utils/metrics.py` | Collects and saves pipeline timing and quality metrics |

---

## Requirements

- Python 3.12+
- [Ollama](https://ollama.com/download) installed and running locally
- NVIDIA GPU recommended (CUDA); CPU fallback is supported but slow for precision extraction

---

## Installation

### 1. Install and start Ollama

Download from https://ollama.com/download and start the Ollama server.

Pull the required model:
```bash
ollama pull qwen3:4b
```

Verify it is available:
```bash
ollama list
```

### 2. Set up Python environment

```bash
python -m venv venv
```

Activate:
- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- Linux/macOS: `source .venv/bin/activate`

Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Place your PDF

Put a single PDF file in the project root directory (where `main.py` is located). The CLI picks the first `*.pdf` it finds.

---

## Usage

### CLI mode

Default (accuracy mode, 20 questions):
```bash
python main.py
```

Fast mode (skips precision extraction and Explainer stage):
```bash
python main.py --mode fast
```

Specify number of questions:
```bash
python main.py --mode accuracy --num 30
python main.py --mode fast --num 10
```

### API mode (with frontend)

Start the backend API:
```bash
python -m uvicorn api:app --reload --port 8000
```

Start the frontend (in a separate terminal):
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

---

## Configuration

All settings are in `config.ini`:

```ini
[models]
model = qwen3:4b          # Primary model for ALL agents

[extraction]
use_gpu = true
batch_multiplier = 2

[rag]
embedding_model = all-MiniLM-L6-v2
chunk_size = 512
chunk_overlap = 64
top_k = 8
candidate_multiplier = 2.0   # Generate N×2 candidates, keep top N

[adversary]
acceptance_threshold = 60    # Minimum score (0–100) to accept a question

[logging]
level = INFO
```

The `candidate_multiplier` controls overgeneration: with the default of `2.0`, requesting 20 questions generates 40 candidates, then the Adversary selects the best 20.

---

## Outputs

All outputs are written to the `outputs/` directory:

| File | Description |
|---|---|
| `Generated_Quiz.md` | Final quiz in Markdown format |
| `knowledge_bricks.json` | Structured knowledge extracted by Curator |
| `knowledge_bricks.md` | Markdown version of knowledge bricks |
| `pedagogue_candidates.json` | All candidate questions after Stages A+B+C |
| `adversary_scored.json` | All questions with adversary scores |
| `final_quiz.json` | Final quiz as JSON |
| `metrics.json` | Full pipeline timing and quality metrics |
| `*_fast.md` | Fast-extracted Markdown from PDF |
| `*_marker.md` | Precision-extracted Markdown (if OCR was triggered) |

---

## Generation Modes

**accuracy** (default): Attempts fast extraction first. If the content appears to contain LaTeX/math or is too sparse, it falls back to Marker OCR for precision. Runs the full pipeline including the Explainer stage.

**fast**: Uses only fitz-based extraction (no OCR, no Marker). Skips the Explainer stage entirely. Suitable for text-only PDFs where speed matters.

---

## Troubleshooting

**No PDF found**: Place exactly one `.pdf` file in the project root directory.

**Ollama not running**: Start Ollama before running the app. Verify with `ollama list`.

**Model not found**: Run `ollama pull qwen3:4b`. The app logs a warning if the model is missing but Ollama is reachable.

**GPU out of memory**: Set `use_gpu = false` in `config.ini` under `[extraction]`, or reduce `batch_multiplier`.

**Empty quiz output**: The Adversary rejected all candidates. Lower `acceptance_threshold` in `config.ini`, or check that the PDF contains sufficient text content.

**FAISS not installed**: RAG falls back to keyword-based retrieval automatically. Install with `pip install faiss-cpu` for vector search.

**sentence-transformers not installed**: RAG falls back to keyword-based retrieval automatically. Install with `pip install sentence-transformers`.

---

## Limitations

- Processes one PDF at a time (CLI picks the first `*.pdf` in the project root).
- API mode stores jobs in memory only; jobs are lost on server restart.
- Precision extraction (Marker OCR) requires significant VRAM and is slow on CPU.
- The Explainer stage is skipped in fast mode; questions will have explanations from Stage C (Pedagogue) only.
- Token usage is estimated (characters ÷ 4), not measured from Ollama's actual token counts.
- No authentication or rate limiting on the API endpoints.

---

## GPU Setup (Windows)

`setup_gpu.ps1` in the project root is a PowerShell script that configures the CUDA environment for Windows. Run it once before the first use if you have an NVIDIA GPU and encounter CUDA-related errors during precision extraction.

```powershell
.\setup_gpu.ps1
```

---

## Documentation

| File | Purpose |
|---|---|
| `README.MD` | Project overview, installation, usage, configuration |
| `docs/ARCHITECTURE_REPORT.md` | Technical architecture, verified components, feature matrix, open issues |
| `docs/CONSISTENCY_AUDIT.md` | Technical debt, dead code, implementation issues, prioritized fix list |
| `docs/vi/Project.md` | Vietnamese technical documentation |
| `CHANGELOG.md` | History of all documentation changes |
| `docs/archive/Instruction.md` | Historical task specification (archived, not current documentation) |
