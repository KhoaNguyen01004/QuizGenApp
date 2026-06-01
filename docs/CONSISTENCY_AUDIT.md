# Code Consistency Audit — QuizGenApp

**Audit Date**: 2025-06-10
**Method**: Full source code inspection against documented expected behavior.
**Scope**: All Python backend files, frontend TypeScript, config.ini, requirements.txt.

---

## Executive Summary

| Category | Count |
|---|---|
| Critical issues | 1 |
| High severity issues | 3 |
| Medium severity issues | 9 |
| Low severity issues | 6 |
| Resolved issues | 7 |
| **Total issues** | **26** |

---

## Resolved Issues

### C-1 · `_log_summary()` crashes at runtime — AttributeError on undeclared fields

Status: RESOLVED

Files:
- backend/utils/metrics.py
- api.py
- main.py

Changes:
- Added `model_used` field
- Added `num_questions_requested` field
- Added `rag_chunks_used` field
- Added `ocr_skipped` field

Impact:
- Prevents `AttributeError` in `_log_summary()`
- Metrics now appear in `metrics.json`

---

### C-2 · Source-based consistency checks are dead code — never executed in pipeline

Status: RESOLVED

Files:
- backend/validators.py
- backend/pedagogue.py
- api.py
- main.py

Changes:
- Added `source_chunks_by_id` propagation
- Enabled source support validation
- Enabled explanation-source alignment validation

Impact:
- Unsupported answers can now be detected
- Hallucinated explanations can now be rejected

---

### C-4 · `main.py` missing `AnswerConsistencyValidator` phase — CLI and API pipelines diverge

Status: RESOLVED

Files:
- main.py

Changes:
- Added `AnswerConsistencyValidator` phase to CLI pipeline

Impact:
- CLI and API pipelines now execute identical validation steps

---

### H-2 · `MetricsCollector.record_retrieval()` is never called

Status: RESOLVED

Files:
- backend/utils/metrics.py
- backend/utils/rag.py

Changes:
- Passed `MetricsCollector` into `RAGIndexer`
- Called `record_retrieval()` in `retrieve()` and `retrieve_with_ids()`

Impact:
- `retrieval_latency_ms` now populates in `metrics.json`
- Retrieval latency metrics are tracked during RAG queries

---

### H-4 · `[extraction]` config section is read but `use_gpu` and `batch_multiplier` are ignored

Status: RESOLVED

Files:
- config.ini
- api.py
- main.py
- backend/utils/text_extractor.py

Changes:
- Read `[extraction]` configuration
- Passed `use_gpu` to `PDFExtractor`
- Passed `batch_multiplier` through extraction initialization

Impact:
- Extraction configuration values now take effect
- GPU and batch multiplier settings can be controlled from config.ini

---

### H-5 · `[logging]` config section is read but `level` value is ignored

Status: RESOLVED

Files:
- config.ini
- api.py
- main.py

Changes:
- Read log level from `[logging].level`
- Applied configured logging level via `logging.basicConfig`

Impact:
- Log verbosity now follows configuration
- Logging section is functional

---

### H-6 · `ResultResponse` type missing `metrics` field — frontend silently drops metrics

Status: RESOLVED

Files:
- frontend/src/types/index.ts
- frontend/src/services/api.ts

Changes:
- Added `PipelineMetricsSummary`
- Added `metrics?: PipelineMetricsSummary` to `ResultResponse`
- Wired metrics data through API result typing

Impact:
- Frontend can access backend metrics safely
- Metrics are no longer discarded by the client

---

## CRITICAL Issues


### C-3 · Frontend `api.ts` contains dead `formData` object and developer confusion comment

**Severity**: Critical
**File**: `frontend/src/services/api.ts`

**Evidence**:
```typescript
const formData = new FormData();
formData.append('file', file);      // ← built but never sent
formData.append('mode', mode);
formData.append('num_questions', numQuestions.toString());

// ... developer comment expressing uncertainty ...

const formData2 = new FormData();
formData2.append('pdf', file);      // ← this one is actually sent
formData2.append('mode', mode);
formData2.append('num_questions', numQuestions.toString());

const response = await axios.post<GenerateResponse>(`${API_URL}/generate`, formData2, ...);
```
`formData` (with field name `'file'`) is constructed but never used. `formData2` (with field
name `'pdf'`) is the one sent. The backend expects `pdf: UploadFile = File(...)`.

**Impact**: The dead `formData` object wastes memory on every upload call. The developer
comment ("I'll use 'file' but maybe we should check") indicates this was left in accidentally
and creates confusion about which field name is correct. If a future developer removes
`formData2` and uses `formData` instead, uploads will break with a 422 Unprocessable Entity.

**Recommended fix**: Remove `formData` entirely. Keep only `formData2`, rename it to
`formData`, and remove the confusion comment.

---

## HIGH Severity Issues


### H-1 · `_build_merge_prompt()` is dead code — never called

**Severity**: High
**File**: `backend/curator.py`, `CuratorAgent._build_merge_prompt()`

**Evidence**:
```python
def _build_merge_prompt(self, partials_json: str) -> str:
    return _MERGE_SYSTEM + "\n\n" + _MERGE_USER.format(partials=partials_json)
```
`_MERGE_SYSTEM` and `_MERGE_USER` prompt templates are defined at module level.
`_build_merge_prompt()` is defined as an instance method. Neither the method nor the
prompt templates are called anywhere in `curator.py`, `api.py`, or `main.py`.
The deduplication strategy used is `_deduplicate_bricks()` (concept-name dedup), not
an LLM merge call.

**Impact**: Dead code. The merge prompts and method occupy space and imply a merge
strategy that does not exist. A developer reading the code may assume LLM-based merging
is happening when it is not.

**Recommended fix**: Remove `_build_merge_prompt()`, `_MERGE_SYSTEM`, and `_MERGE_USER`
from `curator.py`, or implement the merge call if LLM-based deduplication is desired.

---

### H-3 · `LLMProvider.generate_batch()` is never called

**Severity**: High
**File**: `backend/llm_provider.py`, `LLMProvider.generate_batch()`

**Evidence**:
```python
def generate_batch(
    self,
    prompts: list[str],
    ...
) -> list[Optional[str]]:
    """Generate responses for multiple prompts in parallel."""
```
All agents (Curator, Pedagogue, Adversary, Explainer) implement their own
`ThreadPoolExecutor` loops calling `self.llm.generate()` individually. None call
`generate_batch()`. Searching the codebase confirms zero call sites.

**Impact**: Dead code. The method exists but provides no value. Agents duplicate the
parallel dispatch logic that `generate_batch()` was meant to centralize.

**Recommended fix**: Either remove `generate_batch()` and accept the duplicated
`ThreadPoolExecutor` pattern in each agent, or refactor agents to use `generate_batch()`
and remove their individual executor loops.

---

### H-7 · `input_ids` variable computed but never used in `ExplainerAgent`

**Severity**: High
**File**: `backend/explainer.py`, `ExplainerAgent.generate_explanations()`

**Evidence**:
```python
# Instrumentation: log Stage C input completeness before generation
input_ids = [q.get("id") for q in quiz_data if isinstance(q, dict)]
missing_expl_before = [...]
logger.info(f"Stage C input: {len(quiz_data)} questions; ...")
```
`input_ids` is assigned but never read. It is not logged, not used in any computation,
and not passed anywhere. Only `len(quiz_data)` is used in the log message.

**Impact**: Unnecessary list comprehension on every Explainer call. Minor performance
waste proportional to quiz size.

**Recommended fix**: Remove the `input_ids` assignment entirely.

---

## MEDIUM Severity Issues


### M-1 · `duplicate_topics` metric field is declared but never written

**Severity**: Medium
**File**: `backend/utils/metrics.py`, `PipelineMetrics`

**Evidence**:
```python
duplicate_topics: int = 0
```
Searching the entire codebase for `duplicate_topics`: defined in `PipelineMetrics`,
never assigned anywhere in `curator.py`, `pedagogue.py`, `adversary.py`, `explainer.py`,
`api.py`, or `main.py`. It is always 0 in `metrics.json`.

**Impact**: The metric appears in `metrics.json` but is meaningless. It implies topic
deduplication is tracked when it is not.

**Recommended fix**: Either populate it in `PedagogueAgent._deduplicate_questions()`
by counting removed duplicates, or remove the field.

---

### M-2 · `missing_explanations` metric field is declared but never written

**Severity**: Medium
**File**: `backend/utils/metrics.py`, `PipelineMetrics`

**Evidence**:
```python
missing_explanations: int = 0
```
Never assigned anywhere in the codebase. Always 0 in `metrics.json`.

**Impact**: Misleading metric. The Explainer does track missing explanations via
`missing_expl_before` list but never writes the count to this field.

**Recommended fix**: In `ExplainerAgent.generate_explanations()`, after computing
`missing_expl_before`, add:
```python
if self.metrics:
    self.metrics.metrics.missing_explanations = len(missing_expl_before)
```

---

### M-3 · Legacy config keys `curator_model`, `pedagogue_model`, etc. create false expectations

**Severity**: Medium
**File**: `config.ini`

**Evidence**:
```ini
# Legacy keys kept for backward compatibility (ignored by new pipeline)
curator_model = qwen3:4b
pedagogue_model = qwen3:4b
adversary_model = qwen3:4b
explainer_model = qwen3:4b
```
These keys are never read by `api.py` or `main.py`. The pipeline reads only
`models_cfg.get("model", "qwen3:4b")`.

**Impact**: A user who changes `curator_model = phi4-mini` expecting the Curator to
use a different model will see no effect. The config file is misleading.

**Recommended fix**: Remove the legacy keys entirely, or add a prominent comment
warning that changing them has no effect and directing users to the `model` key.

---

### M-4 · `rag_indexer` parameter accepted by `ExplainerAgent.generate_explanations()` but never used

**Severity**: Medium
**File**: `backend/explainer.py`, `ExplainerAgent.generate_explanations()`

**Evidence**:
```python
def generate_explanations(
    self,
    knowledge_bricks: str,
    quiz_data: List[Dict[str, Any]],
    output_path: Optional[str] = None,
    batch_size: int = 8,
    max_workers: int = 2,
    rag_indexer: Optional[RAGIndexer] = None,   # ← accepted
) -> List[Dict[str, Any]]:
```
`rag_indexer` is accepted as a parameter but never referenced in the method body.
The Explainer uses `knowledge_bricks` (the full Markdown string) as its knowledge
source for all questions, regardless of whether a RAG index is available.

**Impact**: The parameter signature implies per-question RAG retrieval is possible,
but it is not implemented. Callers in `api.py` and `main.py` pass `rag_indexer=rag_indexer`
which is silently ignored.

**Recommended fix**: Either implement per-question RAG context retrieval using
`rag_indexer`, or remove the parameter from the signature and update callers.

---

### M-5 · `_faiss_retrieve()` is unreachable when MMR is enabled (default)

**Severity**: Medium
**File**: `backend/utils/rag.py`, `RAGIndexer._faiss_retrieve()`

**Evidence**:
```python
def retrieve(self, query, top_k=5, use_mmr=True, mmr_lambda=0.6):
    if self._use_faiss and self.index is not None and self._embedder is not None:
        if use_mmr:
            return self._mmr_retrieve(query, top_k, mmr_lambda)
        return self._faiss_retrieve(query, top_k)   # ← only reached if use_mmr=False
```
All callers in the codebase use the default `use_mmr=True`:
- `CuratorAgent._get_rag_contexts()` → `rag_indexer.retrieve(query, top_k=top_k)` (default)
- `AdversaryAgent._validate_batch()` → `rag_indexer.retrieve(query, top_k=1)` (default)
- `PedagogueAgent.generate_quiz()` → `rag_indexer.retrieve_for_topic(...)` → `retrieve(...)` (default)

`_faiss_retrieve()` and `_faiss_retrieve_indices()` are only reachable if a caller
explicitly passes `use_mmr=False`, which no caller does.

**Impact**: `_faiss_retrieve()` and `_faiss_retrieve_indices()` are effectively dead
code in the current pipeline. They are not wrong, but they are untested in practice.

**Recommended fix**: Either document that `use_mmr=False` is an intentional escape
hatch, or remove the non-MMR FAISS path if it is not needed.

---

### M-6 · `_check_unique_answer()` references `correct_answer_idx` but never uses it

**Severity**: Medium
**File**: `backend/validators.py`, `AnswerConsistencyValidator._check_unique_answer()`

**Evidence**:
```python
def _check_unique_answer(self, q: Dict[str, Any]) -> Tuple[bool, str]:
    options = q.get("options", [])
    correct_answer_idx = q.get("correct_answer", 0)   # ← assigned

    if len(options) < 4:
        ...
    unique_options = set(str(opt).lower().strip() for opt in options)
    if len(unique_options) < len(options):
        ...
    return True, ""
    # correct_answer_idx is never used
```
`correct_answer_idx` is assigned but never referenced in the method body.

**Impact**: Minor dead assignment. No functional impact, but adds noise.

**Recommended fix**: Remove the `correct_answer_idx` assignment from `_check_unique_answer()`.

---

### M-7 · `validators.py` `reset_failures()` method is never called

**Severity**: Medium
**File**: `backend/validators.py`, `AnswerConsistencyValidator.reset_failures()`

**Evidence**:
```python
def reset_failures(self):
    """Reset failure counters."""
    self.failures = {k: 0 for k in self.failures}
```
`AnswerConsistencyValidator` is instantiated fresh each pipeline run, so `reset_failures()`
has no practical use. It is never called in `api.py` or `main.py`.

**Impact**: Dead method. Not harmful, but adds surface area.

**Recommended fix**: Remove `reset_failures()` since the validator is always instantiated
fresh. If the validator is ever reused across runs, add it back.

---

### M-8 · `_marker_config_parser` stored but never read after initialization

**Severity**: Medium
**File**: `backend/utils/text_extractor.py`, `PDFExtractor`

**Evidence**:
```python
self._marker_config_parser = None   # in __init__

# in _ensure_marker_initialized():
self._marker_config_parser = config_parser   # stored
```
`self._marker_config_parser` is assigned in `_ensure_marker_initialized()` but never
read anywhere else in the class. The `config_parser` object is only needed to call
`config_parser.generate_config_dict()` during initialization, after which it serves
no purpose.

**Impact**: Holds a reference to the Marker `ConfigParser` object for the lifetime of
the `PDFExtractor` instance, preventing garbage collection. Minor memory waste.

**Recommended fix**: Remove `self._marker_config_parser = None` from `__init__` and
`self._marker_config_parser = config_parser` from `_ensure_marker_initialized()`.

---

### M-9 · `answer in "ABCD"` check in validators is logically incorrect

**Severity**: Medium
**File**: `backend/validators.py`, `AnswerConsistencyValidator._check_answer_in_options()`

**Evidence**:
```python
if answer not in "ABCD":
    self.failures["answer_not_in_options"] += 1
    return False, f"answer '{answer}' not in ABCD"
```
`answer not in "ABCD"` checks if `answer` is a substring of the string `"ABCD"`, not
if it is one of the characters `{'A', 'B', 'C', 'D'}`. For single-character answers
this works correctly. However, if `answer` is an empty string `""`, `"" in "ABCD"` is
`True` (empty string is a substring of everything), so an empty answer passes this check.

**Impact**: An empty string answer `""` passes the `answer not in "ABCD"` guard but
would fail `chr(65 + correct_answer_idx)` comparison. The bug is partially masked by
the subsequent check, but the intent is not correctly expressed.

**Recommended fix**: Change to `if answer not in {"A", "B", "C", "D"}:` for clarity
and correctness.

---

## LOW Severity Issues


### L-1 · `field` imported but unused in `metrics.py`

**Severity**: Low
**File**: `backend/utils/metrics.py`

**Evidence**:
```python
from dataclasses import dataclass, field, asdict
```
`field` is imported but never used. No `PipelineMetrics` field uses `field(default_factory=...)`.

**Impact**: Unused import. Minor noise.

**Recommended fix**: Remove `field` from the import.

---

### L-2 · `Dict` imported but unused in `json_utils.py`

**Severity**: Low
**File**: `backend/utils/json_utils.py`

**Evidence**:
```python
from typing import Any, Dict, List, Optional
```
`Dict` is imported but not used in any function signature or type annotation in the file.

**Impact**: Unused import. Minor noise.

**Recommended fix**: Remove `Dict` from the import.

---

### L-3 · Indentation inconsistency in agent `__init__` signatures

**Severity**: Low
**File**: `backend/curator.py`, `backend/pedagogue.py`, `backend/adversary.py`, `backend/explainer.py`

**Evidence**:
```python
# curator.py
def __init__(
    self,
    llm: Optional[LLMProvider] = None,
model: str = "qwen3:4b",    # ← missing 4-space indent
    timeout: int = 600,
```
The `model` parameter in all four agent `__init__` methods is missing its leading
4-space indent. This is a formatting artifact, likely from a find-and-replace operation.
Python parses it correctly (it is still valid syntax), but it violates PEP 8 and looks
broken in any editor.

**Impact**: Cosmetic. No functional impact. Confusing to read.

**Recommended fix**: Add the missing 4-space indent to `model: str = "qwen3:4b"` in
all four agent constructors.

---

### L-4 · `accepted` and `rejected` lists computed in `AdversaryAgent.validate_quiz()` but only `len(rejected)` is used

**Severity**: Low
**File**: `backend/adversary.py`, `AdversaryAgent.validate_quiz()`

**Evidence**:
```python
accepted = [q for q in scored_questions if not q.get("adversary_flag", True)]
rejected = [q for q in scored_questions if q.get("adversary_flag", False)]

if self.metrics:
    self.metrics.metrics.questions_rejected = len(rejected)
    # accepted list is never used — only len(rejected) matters
```
`accepted` is built as a full list but only `len(rejected)` is used for metrics.
`accepted` itself is never iterated or returned.

**Impact**: Unnecessary list construction. Minor performance waste.

**Recommended fix**: Replace with `rejected_count = sum(1 for q in scored_questions if q.get("adversary_flag", False))` and use that directly.

---

### L-5 · `_REPAIR_PROMPT` in `pedagogue.py` requests fields that Stage B/C don't produce

**Severity**: Low
**File**: `backend/pedagogue.py`, `_REPAIR_PROMPT`

**Evidence**:
```python
_REPAIR_PROMPT = """Extract ONLY the JSON array of MCQ objects from this text.
Each object needs: id, question, options (4 items), correct_answer (0-3), answer (A-D), explanation, difficulty, topic.
Return ONLY valid JSON array.
```
This repair prompt is used in three contexts:
1. Stage A repair — asks for `answer`, `explanation`, `correct_answer` which Stage A
   intentionally does NOT produce (they are stripped in `_parse_questions()`).
2. Stage B repair — asks for `question`, `options`, `explanation` which Stage B does
   not produce (it only produces `id`, `answer`, `reasoning`).
3. Stage C repair — asks for `answer`, `correct_answer` which Stage C does not produce.

The repair prompt schema does not match the actual expected output of any stage.

**Impact**: When repair is triggered, the LLM is asked for a schema that doesn't match
what the calling code expects. The repair may produce output that `_parse_questions()`
or `_verify_answers()` partially accepts but with unexpected fields, or rejects entirely.

**Recommended fix**: Create stage-specific repair prompts:
- `_REPAIR_PROMPT_STAGE_A`: asks for `id, question, options, topic, difficulty`
- `_REPAIR_PROMPT_STAGE_B`: asks for `id, answer, reasoning`
- `_REPAIR_PROMPT_STAGE_C`: asks for `id, explanation`

---

### L-6 · `setup_gpu.ps1` exists but is undocumented

**Severity**: Low
**File**: `setup_gpu.ps1`

**Evidence**: File exists in the repository root. Not mentioned in `README.MD`,
`docs/vi/Project.md`, or any other documentation.

**Impact**: Users on Windows with GPU may not know this script exists or what it does.

**Recommended fix**: Add a brief mention in `README.MD` under Installation, explaining
what `setup_gpu.ps1` does and when to run it.

---

## Summary Tables

### Dead Code Inventory

| Item | File | Type | Severity |
|---|---|---|---|
| `_build_merge_prompt()` | `curator.py` | Dead method | High |
| `_MERGE_SYSTEM`, `_MERGE_USER` | `curator.py` | Dead constants | High |
| `generate_batch()` | `llm_provider.py` | Dead method | High |
| `record_retrieval()` | `metrics.py` | Dead method | High |
| `_faiss_retrieve()` | `rag.py` | Unreachable method | Medium |
| `_faiss_retrieve_indices()` | `rag.py` | Unreachable method | Medium |
| `reset_failures()` | `validators.py` | Dead method | Medium |
| `input_ids` variable | `explainer.py` | Dead variable | High |
| `correct_answer_idx` in `_check_unique_answer` | `validators.py` | Dead variable | Medium |
| `accepted` list in `validate_quiz` | `adversary.py` | Dead list | Low |
| `self._marker_config_parser` | `text_extractor.py` | Dead attribute | Medium |
| `formData` (first one) | `api.ts` | Dead object | Critical |
| `field` import | `metrics.py` | Unused import | Low |
| `Dict` import | `json_utils.py` | Unused import | Low |

---

### Metrics Never Written

| Field | Declared in | Should be written by | Severity |
|---|---|---|---|
| `model_used` | `PipelineMetrics` (dynamic) | `api.py`, `main.py` | Critical |
| `num_questions_requested` | `PipelineMetrics` (dynamic) | `api.py`, `main.py` | Critical |
| `rag_chunks_used` | `PipelineMetrics` (dynamic) | `curator.py` | Critical |
| `ocr_skipped` | `PipelineMetrics` (dynamic) | `set_ocr_times()` | Critical |
| `duplicate_topics` | `PipelineMetrics` | `pedagogue.py` | Medium |
| `missing_explanations` | `PipelineMetrics` | `explainer.py` | Medium |
| `retrieval_latency_ms` | `PipelineMetrics` | `rag.py` (via `record_retrieval`) | High |

---

### Configuration Values Ignored

| Key | Section | Read by pipeline | Effect of changing |
|---|---|---|---|
| `use_gpu` | `[extraction]` | No | None |
| `batch_multiplier` | `[extraction]` | No | None |
| `level` | `[logging]` | No | None |
| `curator_model` | `[models]` | No | None |
| `pedagogue_model` | `[models]` | No | None |
| `adversary_model` | `[models]` | No | None |
| `explainer_model` | `[models]` | No | None |

---

### Validation Stages: Documented vs Executed

| Check | Implemented | Executed in API | Executed in CLI |
|---|---|---|---|
| Answer index valid | Yes | Yes | No (CLI missing Phase 5.5) |
| 4 options, no duplicates | Yes | Yes | No |
| Explanation format | Yes | Yes | No |
| Source support (keyword) | Yes | **No** (source_chunks=None) | No |
| Explanation-source alignment | Yes | **No** (source_chunks=None) | No |

---

### Frontend/Backend API Mismatches

| Issue | Frontend | Backend | Severity |
|---|---|---|---|
| Upload field name confusion | `formData` (unused, `'file'`) + `formData2` (used, `'pdf'`) | expects `pdf` | Critical |
| `ResultResponse.metrics` missing | Not declared in type | Returned in response | High |
| `QuizQuestion.answer` missing | Not in interface | Present in quiz JSON | Medium |
| `QuizQuestion.adversary_score` missing | Not in interface | Present in quiz JSON | Low |
| `QuizQuestion.source_chunk_id` missing | Not in interface | Present in quiz JSON | Low |


---

## Technical Debt Report

### Debt Category 1: Broken Metrics Subsystem

The metrics system has a structural flaw: four fields that are logged and expected in
`metrics.json` (`model_used`, `num_questions_requested`, `rag_chunks_used`, `ocr_skipped`)
are not declared in the `PipelineMetrics` dataclass. They are set as dynamic attributes
which `dataclasses.asdict()` silently ignores. Additionally, `_log_summary()` references
`m.model_used` and `m.ocr_skipped` which will raise `AttributeError` if the pipeline
crashes before those attributes are set. Two more fields (`duplicate_topics`,
`missing_explanations`) are declared but never populated. One method (`record_retrieval`)
exists to populate `retrieval_latency_ms` but is never called.

**Debt estimate**: ~2 hours to fix all metrics issues.

---

### Debt Category 2: Incomplete Validation Pipeline

The `AnswerConsistencyValidator` was designed with five checks but only three execute
in production. The two source-based checks are implemented but unwired. The CLI path
skips the validator entirely. This means the documented "source support validation"
feature does not exist in practice.

**Debt estimate**: ~3 hours to wire source chunks through the pipeline and add Phase 5.5
to `main.py`.

---

### Debt Category 3: Dead Code Accumulation

Fourteen dead code items were identified: methods, constants, variables, and imports
that are defined but never used. The most significant are `generate_batch()` in
`LLMProvider` (which was meant to centralize parallel dispatch but was never adopted),
`_build_merge_prompt()` in `CuratorAgent` (a planned LLM-merge strategy that was
replaced by simple deduplication), and `record_retrieval()` in `MetricsCollector`.

**Debt estimate**: ~1 hour to remove all dead code.

---

### Debt Category 4: Configuration Facade

Seven configuration keys in `config.ini` have no effect when changed. Three entire
sections (`[extraction]`, `[logging]`, and the legacy model keys in `[models]`) are
either not read or not applied. Users who attempt to tune the system via config will
be confused when their changes have no effect.

**Debt estimate**: ~2 hours to wire `[extraction]` and `[logging]` sections.

---

### Debt Category 5: Frontend/Backend Contract Drift

The frontend TypeScript types do not match the backend JSON responses. The `metrics`
object is returned but has no type definition. The `QuizQuestion` interface is missing
several fields that the backend includes (`answer`, `adversary_score`, `source_chunk_id`,
`source_excerpt`, `status`). The `api.ts` file contains a dead `formData` object and
a developer confusion comment that should have been cleaned up.

**Debt estimate**: ~1 hour to align TypeScript types with backend responses.

---

## Prioritized Fix List

Priority order based on severity and impact on correctness:

| Priority | Issue ID | Description | Effort |
|---|---|---|---|
| 1 | C-1 | Declare missing `PipelineMetrics` fields to prevent `AttributeError` crash | 30 min |
| 2 | C-4 | Add `AnswerConsistencyValidator` phase to `main.py` | 30 min |
| 3 | C-2 | Wire `source_chunks` into `validate_batch()` in both `api.py` and `main.py` | 2 hr |
| 4 | C-3 | Remove dead `formData` from `api.ts`, clean up comment | 15 min |
| 5 | H-4 | Read `[extraction]` config and pass `use_gpu`/`batch_multiplier` to `PDFExtractor` | 1 hr |
| 6 | H-5 | Read `[logging]` config and apply log level | 30 min |
| 7 | H-2 | Call `record_retrieval()` in `RAGIndexer` or remove the method | 30 min |
| 8 | H-6 | Add `metrics` field to `ResultResponse` TypeScript interface | 30 min |
| 9 | H-7 | Remove unused `input_ids` variable in `ExplainerAgent` | 5 min |
| 10 | H-1 | Remove dead `_build_merge_prompt()`, `_MERGE_SYSTEM`, `_MERGE_USER` | 10 min |
| 11 | H-3 | Remove or adopt `generate_batch()` in `LLMProvider` | 1 hr |
| 12 | M-1 | Populate `duplicate_topics` metric in `PedagogueAgent` | 30 min |
| 13 | M-2 | Populate `missing_explanations` metric in `ExplainerAgent` | 15 min |
| 14 | M-3 | Remove or clearly mark legacy config keys as no-ops | 15 min |
| 15 | M-4 | Implement or remove `rag_indexer` param in `ExplainerAgent` | 1 hr |
| 16 | M-6 | Remove unused `correct_answer_idx` in `_check_unique_answer` | 5 min |
| 17 | M-7 | Remove unused `reset_failures()` method | 5 min |
| 18 | M-8 | Remove unused `self._marker_config_parser` storage | 5 min |
| 19 | M-9 | Fix `answer not in "ABCD"` to `answer not in {"A","B","C","D"}` | 5 min |
| 20 | M-5 | Document or remove non-MMR FAISS path | 15 min |
| 21 | L-5 | Create stage-specific repair prompts for Pedagogue | 1 hr |
| 22 | L-4 | Replace `accepted`/`rejected` lists with counters in `AdversaryAgent` | 10 min |
| 23 | L-3 | Fix indentation of `model` param in all four agent `__init__` methods | 5 min |
| 24 | L-1 | Remove unused `field` import from `metrics.py` | 2 min |
| 25 | L-2 | Remove unused `Dict` import from `json_utils.py` | 2 min |
| 26 | L-6 | Document `setup_gpu.ps1` in `README.MD` | 10 min |

**Total estimated effort**: ~10 hours for all 26 issues.
**Critical + High only**: ~5 hours for the 11 most impactful issues.
