# Architecture Report — QuizGenApp

**Status**: Current architecture as of codebase audit.
**Source of truth**: Implementation files only. All claims verified against code.

---

## 1. Current Architecture

### 1.1 Pipeline Overview

The system implements a linear multi-agent pipeline. Each phase is sequential; parallelism occurs within phases (batch processing), not between them.

```
PDF File
   │
   ▼
[PDFExtractor]
   ├── fast_extract():  fitz → pymupdf4llm fallback → raw fitz fallback
   └── precision_extract(): Marker OCR (surya engine, lazy-init, CUDA-aware)
   │
   ▼
[chunk_document()]
   └── Paragraph split → sentence split → merge tiny → sliding overlap
   │
   ▼
[RAGIndexer.build_index()]
   └── sentence-transformers all-MiniLM-L6-v2 → FAISS IndexFlatIP
       (fallback: keyword overlap if FAISS/sentence-transformers unavailable)
   │
   ▼
[CuratorAgent.extract_knowledge()]
   ├── 5 broad RAG queries → deduplicated chunks → ~3000-char batches
   ├── ThreadPoolExecutor (max 3 workers) → LLM calls
   └── JSON knowledge bricks → deduplicate → Markdown string
   │
   ▼
[PedagogueAgent.generate_quiz()]
   ├── Stage A: ThreadPoolExecutor (max 4 workers), batches of 5
   │   └── LLM: question + options only (no answer)
   ├── Source chunk assignment: retrieve_with_ids(topic, top_k=1)
   ├── Stage B: _verify_answers() — LLM independently determines answer
   │   └── Strict JSON: 1 repair retry, reject batch on failure
   └── Stage C: _generate_explanations() — LLM generates explanation
       └── Strict JSON: 1 repair retry, reject if explanation < 20 chars
   │
   ▼
[AdversaryAgent.validate_quiz()]
   ├── ThreadPoolExecutor (max 3 workers), batches of 5
   ├── LLM scores each question 0–100 with deterministic rules
   ├── Merges scores onto original question dicts (preserves metadata)
   ├── Filters: score ≥ acceptance_threshold (default 60)
   └── _final_validation_pass(): checks required fields
   │
   ▼
[AnswerConsistencyValidator.validate_batch()]
   └── Structural checks only (no LLM). Source chunks are now propagated from validated questions when available, enabling source-based support and explanation alignment checks.
       ├── answer index valid and matches correct_answer
       ├── exactly 4 options, no duplicates
       └── explanation exists, ≥ 10 chars, no placeholder text
   │
   ▼
[ExplainerAgent.generate_explanations()]  ← SKIPPED in fast mode
   ├── Only processes questions with adversary_flag = False
   ├── ThreadPoolExecutor (max 2 workers), batches of 8
   └── Single-call fallback per question on batch failure
   │
   ▼
[MetricsCollector.save()]
   └── outputs/metrics.json
   │
   ▼
[PedagogueAgent.save_as_markdown()]
   └── outputs/Generated_Quiz.md
```

### 1.2 Shared Infrastructure

| Component | File | Used by |
|---|---|---|
| `LLMProvider` | `backend/llm_provider.py` | All agents (single shared instance) |
| `safe_parse_json()` | `backend/utils/json_utils.py` | All agents |
| `clean_markdown_output()` | `backend/utils/markdown_cleaner.py` | `PedagogueAgent.save_as_markdown()` |
| `MetricsCollector` | `backend/utils/metrics.py` | `api.py`, `main.py`, all agents |

---

## 2. Verified Components

### 2.1 PDFExtractor
- **File**: `backend/utils/text_extractor.py`
- **fast_extract()**: `fitz.open()` + `page.get_text("text")`. Zero OCR. Falls back to `pymupdf4llm.to_markdown()` if native text is sparse (< 500 chars total or < 30 chars/page). Falls back to raw fitz text as last resort.
- **precision_extract()**: Marker `PdfConverter` with surya OCR engine. Lazy-initialized on first call. Supports CUDA via `torch.cuda.is_available()`.
- **Decision in accuracy mode**: fast first; if result ≥ 3000 chars AND no LaTeX patterns (`\[a-zA-Z]`, `$`, `\(`, `\)`) → use fast result. Otherwise run precision.
- **Timing**: Records `native_time` and `ocr_time` for metrics.

### 2.2 RAGIndexer
- **File**: `backend/utils/rag.py`
- **Embedding model**: `all-MiniLM-L6-v2` (sentence-transformers)
- **Index type**: `faiss.IndexFlatIP` (inner product on L2-normalized vectors = cosine similarity)
- **Default retrieval**: MMR with λ=0.6, pool size = top_k × 3
- **Fallback**: Keyword overlap (token intersection count) when FAISS or sentence-transformers unavailable
- **Source traceability**: `retrieve_with_ids()` returns `(chunk_id, chunk_text)` tuples

### 2.3 CuratorAgent
- **File**: `backend/curator.py`
- **Input**: Full Markdown text + RAGIndexer
- **RAG queries**: 5 fixed broad queries covering concepts, formulas, terminology, processes, objectives
- **Batch size**: ~3000 chars per LLM call
- **Parallelism**: ThreadPoolExecutor, max 3 workers
- **Output**: Markdown string of knowledge bricks (also saved as JSON)
- **Deduplication**: By concept name, case-insensitive

### 2.4 PedagogueAgent
- **File**: `backend/pedagogue.py`
- **Three-stage design**: Separates question generation, answer verification, and explanation generation into independent LLM calls
- **Stage A parallelism**: ThreadPoolExecutor, max 4 workers, batches of 5
- **Stage B/C**: Sequential per source chunk group, batches of 10
- **JSON enforcement**: `safe_parse_json()` + one repair retry per batch; reject on second failure
- **Overgeneration**: `num_candidates = int(num_questions × candidate_multiplier)`
- **Diversity**: `covered_topics` list passed as hint to subsequent batches

### 2.5 AdversaryAgent
- **File**: `backend/adversary.py`
- **Scoring**: 0–100 with deterministic override rules (score=0 on inconsistency, score≤20 on unsupported)
- **Acceptance**: `supported_by_source AND answer_consistent AND explanation_consistent AND score ≥ 50` (internal) AND `score ≥ acceptance_threshold` (configurable, default 60)
- **Parallelism**: ThreadPoolExecutor, max 3 workers, batches of 5
- **Metadata preservation**: Scores merged onto original question dicts via `q2 = dict(q)` before applying score fields
- **Final gatekeeper**: `_final_validation_pass()` checks required fields after threshold filtering

### 2.6 AnswerConsistencyValidator
- **File**: `backend/validators.py`
- **No LLM**: Pure structural validation
- **Checks executed in pipeline**: answer index validity, option count (4), no duplicate options, explanation length ≥ 10 chars, no placeholder text
- **Checks conditionally executed**: source support and explanation-source alignment run when `source_chunk_id` metadata is available and source chunks are propagated into the validator.

### 2.7 ExplainerAgent
- **File**: `backend/explainer.py`
- **Condition**: Only runs in accuracy mode; skipped in fast mode
- **Scope**: Only questions with `adversary_flag = False`
- **Batch size**: 8 questions per LLM call, 2 parallel workers
- **Fallback**: `_explain_single()` per question if batch fails

### 2.8 LLMProvider
- **File**: `backend/llm_provider.py`
- **Model**: `qwen3:4b` (default and configured)
- **Availability check**: Once at `__init__`, cached. No repeated `ollama.list()` calls.
- **keep_alive**: 3600 seconds (1 hour) — model stays resident for entire pipeline
- **Timeout**: 600 seconds per call (configurable)
- **Batch generation helper**: `generate_batch()` exists, but current agents still use per-agent executor loops and do not call this helper.

### 2.9 MetricsCollector
- **File**: `backend/utils/metrics.py`
- **Timing**: `start_timer()` / `stop_timer()` using `time.perf_counter()`
- **LLM latency**: `record_llm_call(phase, duration_ms)` per agent
- **Token estimation**: `len(text) // 4` (rough approximation)
- **Output**: `outputs/metrics.json` via `json.dumps(asdict(self.metrics))`

---

## 3. Resolved Issues (Compared to Original Architecture)

The original architecture document described problems and proposed fixes. The following have been implemented:

| Issue | Resolution | Evidence |
|---|---|---|
| Multiple separate LLM models causing swap delays | Single `LLMProvider` shared across all agents | `api.py` — one `llm = LLMProvider(model=model_name)` |
| No RAG — full document to every agent | FAISS RAG with sentence-transformers | `backend/utils/rag.py` |
| Sequential Explainer calls | Batch processing (8/call) + parallel workers | `ExplainerAgent.generate_explanations()` |
| Sequential Adversary validation | Batch validation (5/call) + parallel workers | `AdversaryAgent.validate_quiz()` |
| `time.sleep(10)` in main.py | Removed — not present in current `main.py` | `main.py` |
| `await asyncio.sleep(5)` in api.py | Removed — not present in current `api.py` | `api.py` |
| Duplicate JSON sanitizer across agents | Moved to `backend/utils/json_utils.py` | `json_utils.py` — `safe_parse_json()` |
| Curator sending full document | RAG chunking before Curator | `CuratorAgent._get_rag_contexts()` |
| No candidate overgeneration | `candidate_multiplier` (default 2.0) | `config.ini`, `PedagogueAgent.generate_quiz()` |
| Adversary binary flag only | 0–100 score with configurable threshold | `AdversaryAgent._parse_scores()` |
| Explainer wastes tokens on rejected questions | Only explains `adversary_flag = False` questions | `ExplainerAgent.generate_explanations()` |
| No metrics collection | Full `MetricsCollector` with 30+ fields | `backend/utils/metrics.py` |
| Source-based consistency validation | Source chunks propagated into `AnswerConsistencyValidator` | `main.py`, `api.py`, `backend/validators.py` |
| Retrieval latency metrics | `RAGIndexer` records retrieval latency into `MetricsCollector` | `backend/utils/rag.py`, `backend/utils/metrics.py` |
| Extraction/logging configuration support | `[extraction]` and `[logging]` values are now read and applied | `main.py`, `api.py`, `config.ini` |
| Frontend metrics typing | Added `metrics?: PipelineMetricsSummary` to result typing | `frontend/src/types/index.ts`, `frontend/src/services/api.ts` |
| Free-form Curator output | Structured JSON knowledge bricks | `CuratorAgent._parse_knowledge_bricks()` |

---

## 4. Open Issues

### 4.1 No Fallback Model
`docs/archive/Instruction.md` specifies a fallback from `qwen3:4b` to `qwen3:1.7b` if the primary model is unavailable. This is not implemented. `LLMProvider` logs a warning if the model is not found but does not attempt a fallback.

### 4.2 No Startup Validation
`docs/archive/Instruction.md` specifies a `RuntimeError` at startup if `qwen3:4b` is not installed. This is not implemented. The pipeline will fail at the first LLM call instead.

### 4.3 No Test Suite
No `tests/` directory exists. No automated tests for any component.

### 4.4 In-Memory Job Store
API jobs are stored in a module-level dict. All jobs are lost on server restart. No persistence layer.

---

## 5. Evolution and Changelog

This report is aligned with the current codebase and the change history documented in `CHANGELOG.md`.

Key evolution milestones:

* `2026-06-01` — Runtime consistency fixes and documentation consolidation.
   - Added `AnswerConsistencyValidator` to the CLI pipeline in `main.py`, matching the API flow.
   - Propagated source chunks from validated questions into `AnswerConsistencyValidator` in both `api.py` and `main.py`.
   - Enabled retrieval latency tracking by passing `MetricsCollector` into `RAGIndexer` and calling `record_retrieval()`.
   - Read and applied `[extraction]` and `[logging]` configuration values in both CLI and API entry points.
   - Added frontend `ResultResponse.metrics` typing and cleaned API upload handling.
* `2025-06-10` — Initial documentation audit and architecture alignment.
   - Corrected stale claims about models, pipeline stages, and configuration keys.
   - Consolidated documentation into `CHANGELOG.md`, `docs/ARCHITECTURE_REPORT.md`, and `docs/CONSISTENCY_AUDIT.md`.

## 6. Architecture Diagram (Verified from Code)

```
┌─────────────────────────────────────────────────────────────────┐
│                         QuizGenApp                              │
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │  main.py │    │   api.py     │    │  frontend/ (Next.js) │  │
│  │  (CLI)   │    │  (FastAPI)   │    │  React 19 + Zustand  │  │
│  └────┬─────┘    └──────┬───────┘    └──────────────────────┘  │
│       │                 │                        │              │
│       └────────┬────────┘              HTTP/JSON (axios)        │
│                │                                │              │
│                ▼                                ▼              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Pipeline                             │   │
│  │                                                         │   │
│  │  PDFExtractor ──► RAGIndexer ──► CuratorAgent           │   │
│  │       │               │               │                 │   │
│  │  fitz/Marker    FAISS+MMR       RAG-grounded            │   │
│  │                               JSON bricks               │   │
│  │                                    │                    │   │
│  │                               PedagogueAgent            │   │
│  │                               Stage A (parallel)        │   │
│  │                               Stage B (strict)          │   │
│  │                               Stage C (strict)          │   │
│  │                                    │                    │   │
│  │                               AdversaryAgent            │   │
│  │                               (batch, parallel)         │   │
│  │                               score 0–100               │   │
│  │                                    │                    │   │
│  │                          AnswerConsistencyValidator      │   │
│  │                          (structural checks only)        │   │
│  │                                    │                    │   │
│  │                               ExplainerAgent            │   │
│  │                          (accuracy mode only, parallel)  │   │
│  │                                    │                    │   │
│  │                               MetricsCollector          │   │
│  │                               outputs/metrics.json      │   │
│  │                                    │                    │   │
│  │                          outputs/Generated_Quiz.md       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Shared Infrastructure                  │   │
│  │  LLMProvider (qwen3:4b, keep_alive=3600s)               │   │
│  │  json_utils.py (safe_parse_json + repair)               │   │
│  │  markdown_cleaner.py                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  External: Ollama (local, port 11434)                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Comparison: Original vs Actual Architecture

### Original architecture document claimed (as "After" state):
```
All agents share a single LLMProvider(model="qwen3:1.7b")
```

### Actual implementation:
```
All agents share a single LLMProvider(model="qwen3:4b")
```

The model was migrated from `qwen3:1.7b` to `qwen3:4b` per `docs/archive/Instruction.md`. The original architecture document was written before this migration and still references `qwen3:1.7b`.

### Original pipeline (proposed):
```
Extraction → RAG Indexing → Curator → Pedagogue → Adversary → Explainer → Metrics
```

### Actual pipeline:
```
Extraction → RAG Indexing → Curator → Pedagogue (Stage A → B → C) → Adversary → AnswerConsistencyValidator → Explainer → Metrics
```

The `AnswerConsistencyValidator` stage and the three-stage Pedagogue design were added after the original report was written.

---

## 7. Feature Verification Matrix

Every feature listed below was verified against source code. No claim is assumed.

| Feature | Documented | Implemented | Status | Evidence |
|---|---|---|---|---|
| PDF fast extraction (fitz) | Yes | Yes | VERIFIED | `backend/utils/text_extractor.py` — `fast_extract()` |
| PDF precision extraction (Marker OCR) | Yes | Yes | VERIFIED | `backend/utils/text_extractor.py` — `precision_extract()` |
| pymupdf4llm fallback in fast_extract | No | Yes | VERIFIED (undocumented) | `text_extractor.py` ~line 120–135 |
| GPU detection for Marker | Yes | Yes | VERIFIED | `PDFExtractor.__init__()` via `torch.cuda.is_available()` |
| Markdown cleaning | Yes | Yes | VERIFIED | `backend/utils/markdown_cleaner.py` |
| Document chunking | Yes | Yes | VERIFIED | `backend/utils/rag.py` — `chunk_document()` |
| FAISS vector index | Yes | Yes | VERIFIED | `RAGIndexer.build_index()` — `faiss.IndexFlatIP` |
| sentence-transformers embeddings | Yes | Yes | VERIFIED | `RAGIndexer._init_embedder()` — `all-MiniLM-L6-v2` |
| MMR retrieval | Yes | Yes | VERIFIED | `RAGIndexer._mmr_retrieve()` / `_mmr_retrieve_indices()` |
| Keyword fallback retrieval | Yes | Yes | VERIFIED | `RAGIndexer._keyword_retrieve()` |
| Source traceability (chunk IDs) | Yes | Yes | VERIFIED | `RAGIndexer.retrieve_with_ids()` |
| CuratorAgent | Yes | Yes | VERIFIED | `backend/curator.py` |
| Curator RAG-grounded extraction | Yes | Yes | VERIFIED | `CuratorAgent._get_rag_contexts()` |
| Curator parallel processing | Yes | Yes | VERIFIED | `ThreadPoolExecutor(max_workers=3)` in `extract_knowledge()` |
| Curator JSON output (knowledge bricks) | Yes | Yes | VERIFIED | `_parse_knowledge_bricks()`, `outputs/knowledge_bricks.json` |
| Curator deduplication | Yes | Yes | VERIFIED | `_deduplicate_bricks()` |
| Pedagogue Stage A (question generation) | Yes | Yes | VERIFIED | `PedagogueAgent._generate_batch()` |
| Pedagogue Stage B (answer verification) | Yes | Yes | VERIFIED | `PedagogueAgent._verify_answers()` |
| Pedagogue Stage C (explanation generation) | Yes | Yes | VERIFIED | `PedagogueAgent._generate_explanations()` |
| Pedagogue parallel batches | Yes | Yes | VERIFIED | `ThreadPoolExecutor(max_workers=4)` in `generate_quiz()` |
| Pedagogue question deduplication | Yes | Yes | VERIFIED | `_deduplicate_questions()` |
| Pedagogue topic diversity hint | Yes | Yes | VERIFIED | `covered_topics` list passed to batches |
| Pedagogue repair prompt (JSON retry) | Yes | Yes | VERIFIED | `_REPAIR_PROMPT` used in Stage A, B, C |
| Candidate overgeneration (N × multiplier) | Yes | Yes | VERIFIED | `num_candidates = int(num_questions * candidate_multiplier)` |
| AdversaryAgent scoring (0–100) | Yes | Yes | VERIFIED | `backend/adversary.py` — `_parse_scores()` |
| Adversary deterministic scoring rules | Yes | Yes | VERIFIED | `_parse_scores()` — forced score=0 on inconsistency |
| Adversary batch validation | Yes | Yes | VERIFIED | `ThreadPoolExecutor(max_workers=3)`, batches of 5 |
| Adversary acceptance threshold | Yes | Yes | VERIFIED | `above_threshold` filter in `validate_quiz()` |
| Adversary final gatekeeper | Yes | Yes | VERIFIED | `_final_validation_pass()` |
| Adversary JSON repair retry | Yes | Yes | VERIFIED | repair prompt in `_validate_batch()` |
| AnswerConsistencyValidator | Yes | Yes | VERIFIED | `backend/validators.py` |
| Consistency check: answer in options | Yes | Yes | VERIFIED | `_check_answer_in_options()` |
| Consistency check: unique answer | Yes | Yes | VERIFIED | `_check_unique_answer()` |
| Consistency check: explanation format | Yes | Yes | VERIFIED | `_check_explanation_format()` |
| Consistency check: source support | Yes | Yes | VERIFIED | `api.py`, `main.py`, `backend/validators.py` — source chunks propagated when source_chunk_id is available |
| ExplainerAgent | Yes | Yes | VERIFIED | `backend/explainer.py` |
| Explainer batch processing | Yes | Yes | VERIFIED | `_explain_batch()`, batches of 8, 2 workers |
| Explainer single-call fallback | Yes | Yes | VERIFIED | `_explain_single()` called on batch failure |
| Explainer skipped in fast mode | Yes | Yes | VERIFIED | `if mode == "fast": ... final_quiz = validated` |
| Explainer only for accepted questions | Yes | Yes | VERIFIED | `questions_to_explain = [q for q in quiz_data if not q.get("adversary_flag", False)]` |
| MetricsCollector | Yes | Yes | VERIFIED | `backend/utils/metrics.py` |
| Metrics: timing per phase | Yes | Yes | VERIFIED | `start_timer()` / `stop_timer()` per phase |
| Metrics: per-agent LLM latency | Yes | Yes | VERIFIED | `record_llm_call()` in each agent |
| Metrics: token usage (estimated) | Yes | Yes | VERIFIED | `add_token_usage()` — chars ÷ 4 estimate |
| Metrics: OCR sub-timings | Yes | Yes | VERIFIED | `set_ocr_times()` called in `api.py` and `main.py` |
| Metrics saved to JSON | Yes | Yes | VERIFIED | `metrics.save()` → `outputs/metrics.json` |
| Shared JSON utilities | Yes | Yes | VERIFIED | `backend/utils/json_utils.py` |
| Single shared LLM model | Yes | Yes | VERIFIED | One `LLMProvider` instance in `api.py` and `main.py` |
| Model: qwen3:4b | Yes | Yes | VERIFIED | `config.ini` `model = qwen3:4b`; default in all agents |
| LLM availability cached at init | Yes | Yes | VERIFIED | `LLMProvider._check_and_log()` called once in `__init__` |
| LLM keep_alive = 3600s | Yes | Yes | VERIFIED | `_KEEP_ALIVE_SECONDS = 3600` in `llm_provider.py` |
| CLI mode | Yes | Yes | VERIFIED | `main.py` |
| API mode | Yes | Yes | VERIFIED | `api.py` — FastAPI |
| Frontend (Next.js) | Yes | Yes | VERIFIED | `frontend/` directory |
| Frontend PDF upload | Yes | Yes | VERIFIED | `UploadZone.tsx`, `react-dropzone` |
| Frontend mode selection | Yes | Yes | VERIFIED | `QuizForm.tsx` — accuracy/fast toggle |
| Frontend progress polling | Yes | Yes | VERIFIED | `page.tsx` — `setInterval` every 2s |
| Frontend KaTeX math rendering | Yes | Yes | VERIFIED | `package.json` — `react-katex`, `rehype-katex`, `remark-math` |
| Frontend export (Markdown download) | Yes | Yes | VERIFIED | `ExportButtons.tsx` — `downloadMarkdown()` |
| Frontend export (PDF via print) | Yes | Yes | VERIFIED | `ExportButtons.tsx` — `window.print()` |
| Frontend dark/light theme | Yes | Yes | VERIFIED | `ThemeProvider.tsx`, `ThemeToggle.tsx`, `next-themes` |
| GPU support (extraction) | Yes | Yes | VERIFIED | `PDFExtractor` uses CUDA if available |
| GPU support (LLM inference) | Yes | Yes | VERIFIED | `options.setdefault("num_gpu", -1)` in `LLMProvider.generate()` |
| Fallback model (qwen3:1.7b) | Yes (archive/Instruction.md) | No | NOT IMPLEMENTED | No fallback logic in `llm_provider.py` |
| Startup validation / RuntimeError | Yes (archive/Instruction.md) | No | NOT IMPLEMENTED | No startup check in `main.py` or `api.py` |
| Startup model config log banner | Yes (archive/Instruction.md) | No | NOT IMPLEMENTED | No banner in `main.py` or `api.py` |
| Tests directory | No | No | NOT PRESENT | No `tests/` directory found |

---

## 8. Features Not Implemented

The following items appear in `docs/archive/Instruction.md` or prior documentation but are not present in the codebase:

| Claimed Feature | Source | Reality |
|---|---|---|
| Fallback model (qwen3:1.7b if qwen3:4b unavailable) | `docs/archive/Instruction.md` | Not implemented. `LLMProvider` has no fallback logic. |
| Startup validation with RuntimeError | `docs/archive/Instruction.md` | Not implemented. No startup check in `main.py` or `api.py`. |
| Startup model config log banner | `docs/archive/Instruction.md` | Not implemented. No banner printed at startup. |
| Tests directory / test suite | Standard practice | No `tests/` directory. No test files found. |
| Per-model configuration (curator_model, etc.) | `config.ini` legacy keys | Keys exist but are explicitly ignored. All agents use the single `model` key. |

---

## 9. Partial Implementations

| Feature | Status | Detail |
|---|---|---|
| Source-based consistency validation | Yes | Yes | VERIFIED | `api.py`, `main.py`, `backend/validators.py` |
| `model_used`, `num_questions_requested`, `rag_chunks_used`, `ocr_skipped` metrics | Yes | Yes | VERIFIED | Declared in `backend/utils/metrics.py` and set in `api.py`/`main.py`/`curator.py` |

---

## 10. Model Configuration

The active model is `qwen3:4b`, set in `config.ini`:

```ini
[models]
model = qwen3:4b
```

The legacy per-agent keys (`curator_model`, `pedagogue_model`, `adversary_model`, `explainer_model`) exist in `config.ini` but are not read by the pipeline. The pipeline reads only `models_cfg.get("model", "qwen3:4b")`.

All agents default to `qwen3:4b` in their constructors:
- `CuratorAgent.__init__(model: str = "qwen3:4b")`
- `PedagogueAgent.__init__(model: str = "qwen3:4b")`
- `AdversaryAgent.__init__(model: str = "qwen3:4b")`
- `ExplainerAgent.__init__(model: str = "qwen3:4b")`
- `LLMProvider.__init__(model: str = "qwen3:4b")`

---

## 11. Output Files Reference

| File | Written by | Always present |
|---|---|---|
| `outputs/Generated_Quiz.md` | `PedagogueAgent.save_as_markdown()` | Yes (on success) |
| `outputs/knowledge_bricks.json` | `CuratorAgent.extract_knowledge()` | Yes (on success) |
| `outputs/knowledge_bricks.md` | `CuratorAgent.extract_knowledge()` | Yes (on success) |
| `outputs/pedagogue_candidates.json` | `PedagogueAgent.generate_quiz()` | Yes (on success) |
| `outputs/pedagogue_response_batch{n}.txt` | `PedagogueAgent._generate_batch()` | Yes, one per batch |
| `outputs/adversary_scored.json` | `AdversaryAgent.validate_quiz()` | Yes (on success) |
| `outputs/adversary_batch{n}.txt` | `AdversaryAgent._validate_batch()` | Yes, one per batch |
| `outputs/final_quiz.json` | `ExplainerAgent.generate_explanations()` | Only in accuracy mode |
| `outputs/explainer_batch{n}.txt` | `ExplainerAgent._explain_batch()` | Only in accuracy mode |
| `outputs/metrics.json` | `MetricsCollector.save()` | Yes (on success) |
| `outputs/{stem}_fast.md` | `PDFExtractor.fast_extract()` | Yes |
| `outputs/{stem}_marker.md` | `PDFExtractor.precision_extract()` | Only when OCR triggered |
