# Documentation Changelog

---

## 2026-06-01

### Documentation Consolidation

**Type**: RESTRUCTURED

**Reason**:
Repository contained multiple overlapping documents describing the same architecture and
implementation details. `IMPLEMENTATION_SUMMARY.md` duplicated content already in
`ARCHITECTURE_REPORT.md`. `Project.md` duplicated `README.MD` and architecture content.
`Instruction.md` was a historical task specification with no ongoing documentation value.
This created a risk of documentation drift and contradictory information.

**Actions**:
- Moved `Project.md` → `docs/vi/Project.md`
- Moved `Instruction.md` → `docs/archive/Instruction.md`
- Moved `ARCHITECTURE_REPORT.md` → `docs/ARCHITECTURE_REPORT.md`
- Moved `CONSISTENCY_AUDIT.md` → `docs/CONSISTENCY_AUDIT.md`
- Audited `IMPLEMENTATION_SUMMARY.md` for unique content
- Merged unique sections into `docs/ARCHITECTURE_REPORT.md`:
  - Section 7: Feature Verification Matrix (full table with evidence)
  - Section 8: Features Not Implemented
  - Section 9: Partial Implementations
  - Section 10: Model Configuration (agent constructor defaults)
  - Section 11: Output Files Reference
- Deleted `IMPLEMENTATION_SUMMARY.md` after confirming all content was preserved
- Updated `README.MD` with Documentation section and `setup_gpu.ps1` mention
- Updated all internal cross-references to use new file paths
- Established `docs/ARCHITECTURE_REPORT.md` as the single technical source of truth
- Established `docs/CONSISTENCY_AUDIT.md` as the implementation issue tracker

**Result**:
Documentation now follows a single-source-of-truth model.

| File | Role |
|---|---|
| `README.MD` | Project overview, installation, usage, configuration |
| `docs/ARCHITECTURE_REPORT.md` | Current architecture, verified components, feature matrix, open issues |
| `docs/CONSISTENCY_AUDIT.md` | Known implementation issues and technical debt |
| `docs/vi/Project.md` | Vietnamese technical documentation |
| `CHANGELOG.md` | History of documentation changes |
| `docs/archive/Instruction.md` | Archived historical task specification |

**Status**: Completed

---

### Runtime Consistency Fixes

**Type**: FIXED

#### C-1 PipelineMetrics Dataclass

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

#### C-2 Source-Based Validation

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

#### C-4 CLI/API Pipeline Consistency

Status: RESOLVED

Files:
- main.py

Changes:
- Added `AnswerConsistencyValidator` phase

Impact:
- CLI and API pipelines now execute identical validation steps

---

### High Severity Issues Resolved

* H-2 Retrieval Metrics
* H-4 Extraction Config
* H-5 Logging Config
* H-6 Frontend Metrics

### Verification

Validation:

✓ Confirmed source changes in `main.py`, `api.py`, `backend/utils/rag.py`, `backend/utils/metrics.py`, and frontend type files
✓ Verified `RAGIndexer` now passes `MetricsCollector` and tracks retrieval latency
✓ Verified `AnswerConsistencyValidator` and source chunk propagation exist in both CLI and API paths
✓ Verified `ResultResponse` type includes `metrics`
✓ Full system runtime execution intentionally skipped per request

---

### Documentation Updates

Updated:

* docs/CONSISTENCY_AUDIT.md

Moved fixed issues from:

* Critical Issues
* High Severity Issues

to:

* Resolved Issues

Do not delete historical information. Keep audit history intact.

---

## 2025-06-10

### Initial Documentation Audit

**Type**: CORRECTED + RESTRUCTURED

**Reason**:
Full repository audit revealed multiple documentation files contained false claims,
wrong model names, missing pipeline stages, and unverifiable assertions. All files
were rewritten to match the actual implementation.

**Summary**:
A complete documentation audit was performed. All documentation files were compared
against the actual implementation. Four major documentation files were rewritten.
`docs/DOCUMENTATION_CHANGELOG.md` was created. All false claims were removed.
All retained claims were verified against source code.

**Documentation Accuracy Before/After**:

| File | Before | After |
|---|---|---|
| `README.MD` | Outdated — wrong model, wrong defaults, missing pipeline stages, missing RAG | Verified |
| `Project.md` | Partially correct — missing RAG, missing 3-stage Pedagogue, wrong model references | Verified |
| `IMPLEMENTATION_SUMMARY.md` | Mostly correct but contained unverifiable claims and missing limitations | Verified (now merged into ARCHITECTURE_REPORT.md) |
| `ARCHITECTURE_REPORT.md` | Historical — described proposed fixes as if current, wrong model name | Updated to current |
| `docs/DOCUMENTATION_CHANGELOG.md` | Did not exist | Created |

**Removed False Claims**:

| Document | Claim | Result | Actual |
|---|---|---|---|
| `README.MD` | `ollama pull qwen3:1.7b` required | False | Only `qwen3:4b` is used |
| `README.MD` | `ollama pull phi4-mini:latest`, `gemma3:4b`, `llama3.2:1b` required | False | Not referenced in any code |
| `README.MD` | Default is 30 questions | False | Default is 20 in `main.py` and `api.py` |
| `README.MD` | `curator_model` etc. are active config keys | False | Legacy keys, explicitly ignored |
| `README.MD` | Pipeline is 5 stages | Incomplete | 7 stages including RAG and ConsistencyValidator |
| `ARCHITECTURE_REPORT.md` | `LLMProvider(model="qwen3:1.7b")` | False | Model is `qwen3:4b` |
| `Project.md` | `ollama pull qwen3:1.7b` required | False | Only `qwen3:4b` is used |
| `Project.md` | Pipeline is 5 stages | Incomplete | 7 stages |
| `IMPLEMENTATION_SUMMARY.md` | "Production-ready with educational rigor improvements" | Unverifiable | No test suite exists |

**Architecture Changes**:

Documented architecture (original "After" state):
```
Extraction → RAG Indexing → Curator → Pedagogue → Adversary → Explainer → Metrics
Model: qwen3:1.7b (single shared)
```

Actual architecture (verified from code):
```
Extraction → RAG Indexing → Curator → Pedagogue (Stage A → B → C) → Adversary → AnswerConsistencyValidator → Explainer → Metrics
Model: qwen3:4b (single shared)
```

**Files Modified**:

| File | Change Type | Description |
|---|---|---|
| `README.MD` | CORRECTED + RESTRUCTURED | Removed wrong model references. Corrected default question count. Added RAG and ConsistencyValidator to pipeline. Added outputs table. Added troubleshooting. |
| `Project.md` | CORRECTED + RESTRUCTURED | Rewrote as full technical document. Added RAG, 3-stage Pedagogue, all utility modules, API docs, frontend architecture, limitations. |
| `IMPLEMENTATION_SUMMARY.md` | CORRECTED + RESTRUCTURED | Replaced unverifiable claims. Added feature verification matrix. Added partial implementations section. |
| `ARCHITECTURE_REPORT.md` | CORRECTED + RESTRUCTURED | Corrected model name. Updated pipeline. Added Open Issues section. Added verified component details. |
| `docs/DOCUMENTATION_CHANGELOG.md` | ADDED | Created this file. |

**Not Implemented (per `docs/archive/Instruction.md` requirements)**:

| Requirement | Status |
|---|---|
| Fallback model: qwen3:1.7b if qwen3:4b unavailable | Not implemented |
| Startup validation with RuntimeError if model missing | Not implemented |
| Startup log banner showing active model configuration | Not implemented |
| Logging "Using model: qwen3:4b" before every Ollama call | Not implemented |

These are documented as open issues in `docs/ARCHITECTURE_REPORT.md` Section 4.

**Status**: Completed

---

## 2026-06-01 (Reference Audit)

### Documentation Refactor — Reference Audit

**Type**: CORRECTED

**Date**: 2026-06-01

**Changes**:
- Renamed `docs/DOCUMENTATION_CHANGELOG.md` → `CHANGELOG.md` (moved to repository root)
- `Project.md` is at `docs/vi/Project.md`
- `Instruction.md` is at `docs/archive/Instruction.md`
- `IMPLEMENTATION_SUMMARY.md` was deleted; content merged into `docs/ARCHITECTURE_REPORT.md`
- Updated all internal references across all live documentation files

**Files audited for stale references**:

| File | Stale reference found | Action |
|---|---|---|
| `README.MD` | `docs/DOCUMENTATION_CHANGELOG.md` | Updated → `CHANGELOG.md` |
| `CHANGELOG.md` (2026-06-01 Result table) | `docs/DOCUMENTATION_CHANGELOG.md` | Updated → `CHANGELOG.md` |
| `docs/ARCHITECTURE_REPORT.md` Section 9 (×3) | `CONSISTENCY_AUDIT.md` (missing `docs/` prefix) | Updated → `docs/CONSISTENCY_AUDIT.md` |
| `CHANGELOG.md` (2025-06-10 historical entries) | `docs/DOCUMENTATION_CHANGELOG.md`, `IMPLEMENTATION_SUMMARY.md` | Preserved — historical records, not live links |
| `docs/CONSISTENCY_AUDIT.md` | No stale references found | No change |
| `docs/vi/Project.md` | No stale references found | No change |
| `docs/archive/Instruction.md` | No stale references found | No change |

**Verification**:
- No broken documentation references found in live files.
- Documentation tree validated against filesystem.
- All `docs/DOCUMENTATION_CHANGELOG.md` references in live files updated to `CHANGELOG.md`.
- All `CONSISTENCY_AUDIT.md` bare references in `docs/ARCHITECTURE_REPORT.md` updated to `docs/CONSISTENCY_AUDIT.md`.
- Historical entries in `CHANGELOG.md` (2025-06-10) preserved unchanged — they record what existed at that time.

**Final documentation tree**:

```
README.MD                          — Project overview, installation, usage
CHANGELOG.md                       — Documentation change history
docs/
├── ARCHITECTURE_REPORT.md         — Technical architecture, feature matrix, open issues
├── CONSISTENCY_AUDIT.md           — Technical debt and implementation issues
├── vi/
│   └── Project.md                 — Vietnamese technical documentation
└── archive/
    └── Instruction.md             — Archived historical task specification
```

**Status**: Completed

---

### Evaluation: Rename `docs/ARCHITECTURE_REPORT.md` → `docs/ARCHITECTURE.md`

**Recommendation**: **Approved.**

`docs/ARCHITECTURE_REPORT.md` is the permanent technical source of truth for this project. The `_REPORT` suffix implies a one-time deliverable rather than a living document. `docs/ARCHITECTURE.md` is a cleaner, more conventional name for a permanent architecture reference.

**Impact of rename**:
- All cross-references in `README.MD`, `CHANGELOG.md`, `docs/CONSISTENCY_AUDIT.md`, and `docs/vi/Project.md` would need updating.
- No code files reference this document.
- The rename is low-risk and purely cosmetic.

**Decision**: Rename is approved. Execute as a separate commit to keep the diff clean.
