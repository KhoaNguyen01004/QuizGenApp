"""QuizGenApp — FastAPI backend.

Exposes:
  POST /generate   — Upload PDF, start background job
  GET  /status/{job_id}  — Poll job progress
  GET  /result/{job_id}  — Retrieve final quiz
"""

import logging
import re
import uuid
from configparser import ConfigParser
from pathlib import Path
from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.adversary import AdversaryAgent
from backend.curator import CuratorAgent
from backend.explainer import ExplainerAgent
from backend.llm_provider import LLMProvider
from backend.pedagogue import PedagogueAgent
from backend.utils.metrics import MetricsCollector
from backend.utils.rag import RAGIndexer, chunk_document
from backend.utils.text_extractor import PDFExtractor
from backend.validators import AnswerConsistencyValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# In-memory job store
jobs: Dict[str, Dict[str, Any]] = {}

app = FastAPI(title="QuizGenApp API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_config() -> ConfigParser:
    cfg = ConfigParser()
    cfg.read("config.ini", encoding="utf-8")
    return cfg


async def _process_quiz(job_id: str, file_path: str, mode: str, num_questions: int):
    """Background task: run the full quiz generation pipeline."""

    def log(msg: str, level: str = "info"):
        if level == "info":
            logging.info(msg)
        elif level == "error":
            logging.error(msg)
        elif level == "warning":
            logging.warning(msg)
        jobs[job_id]["logs"].append(f"[{level.upper()}] {msg}")

    def set_stage(stage: str, progress: int):
        jobs[job_id]["stage"] = stage
        jobs[job_id]["progress"] = progress
        log(stage)

    try:
        cfg = _load_config()
        models_cfg = cfg["models"] if cfg.has_section("models") else {}
        rag_cfg = cfg["rag"] if cfg.has_section("rag") else {}
        adversary_cfg = cfg["adversary"] if cfg.has_section("adversary") else {}
        extraction_cfg = cfg["extraction"] if cfg.has_section("extraction") else {}
        logging_cfg = cfg["logging"] if cfg.has_section("logging") else {}

        model_name = models_cfg.get("model", "qwen3:4b")
        top_k = int(rag_cfg.get("top_k", "8"))
        chunk_size = int(rag_cfg.get("chunk_size", "512"))
        chunk_overlap = int(rag_cfg.get("chunk_overlap", "64"))
        candidate_multiplier = float(rag_cfg.get("candidate_multiplier", "2.0"))
        acceptance_threshold = int(adversary_cfg.get("acceptance_threshold", "60"))
        embedding_model = rag_cfg.get("embedding_model", "all-MiniLM-L6-v2")

        # H-4: read extraction config
        use_gpu = extraction_cfg.get("use_gpu", "true").strip().lower() == "true"
        batch_multiplier = int(extraction_cfg.get("batch_multiplier", "2"))

        # H-5: apply log level from config to root logger
        log_level_str = logging_cfg.get("level", "INFO").strip().upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        logging.getLogger().setLevel(log_level)

        metrics = MetricsCollector()
        metrics.metrics.model_used = model_name
        metrics.metrics.num_questions_requested = num_questions

        # ── Phase 1: Extraction ───────────────────────────────────────────────
        set_stage("Extracting PDF", 5)
        metrics.start_timer("extraction")

        # H-4: pass use_gpu and batch_multiplier from config
        extractor = PDFExtractor(use_gpu=use_gpu, batch_multiplier=batch_multiplier)
        if mode == "fast":
            md_content = extractor.fast_extract(file_path) or ""
            if not md_content:
                raise Exception("Fast extraction returned no content.")
        else:
            md_content = extractor.fast_extract(file_path) or ""
            need_precision = True
            if md_content and len(md_content) >= 3000:
                if not re.search(r"\\[a-zA-Z]|\$|\\\(|\\\)", md_content):
                    need_precision = False
            if need_precision:
                log("Running precision extraction for accuracy.")
                md_content = extractor.precision_extract(file_path)
                if not md_content:
                    raise Exception("Precision extraction failed.")

        metrics.stop_timer("extraction")
        log(f"Extracted {len(md_content):,} characters.")

        # Task 8: record OCR sub-timings
        metrics.set_ocr_times(
            native_time=extractor.native_time,
            ocr_time=extractor.ocr_time,
            ocr_skipped=(extractor.ocr_time == 0.0),
        )

        # ── Phase 2: RAG Indexing ─────────────────────────────────────────────
        set_stage("Building RAG Index", 15)
        metrics.start_timer("rag_index")

        chunks = chunk_document(md_content, chunk_size=chunk_size, overlap=chunk_overlap)
        log(f"Document chunked into {len(chunks)} segments.")

        # H-2: pass metrics so RAGIndexer records retrieval latency
        rag_indexer = RAGIndexer(model_name=embedding_model, metrics=metrics)
        rag_indexer.build_index(chunks)

        metrics.stop_timer("rag_index")

        # ── Shared LLM ────────────────────────────────────────────────────────
        llm = LLMProvider(model=model_name, timeout=600)

        # ── Phase 3: Curator ──────────────────────────────────────────────────
        set_stage("Curating Knowledge", 25)
        curator = CuratorAgent(llm=llm, metrics=metrics)
        knowledge_bricks = curator.extract_knowledge(
            md_content=md_content,
            rag_indexer=rag_indexer,
            top_k=top_k,
        )
        if not knowledge_bricks:
            raise Exception("Knowledge extraction failed.")

        # ── Phase 4: Pedagogue ────────────────────────────────────────────────
        set_stage("Generating Candidate Questions", 40)
        pedagogue = PedagogueAgent(llm=llm, metrics=metrics)
        candidates = pedagogue.generate_quiz(
            knowledge_bricks=knowledge_bricks,
            output_path=None,
            num_questions=num_questions,
            rag_indexer=rag_indexer,
            candidate_multiplier=candidate_multiplier,
        )
        if not candidates:
            raise Exception("Failed to generate candidate questions.")

        log(f"Generated {len(candidates)} candidate questions.")

        # ── Phase 5: Adversary ────────────────────────────────────────────────
        set_stage("Validating Questions", 60)
        adversary = AdversaryAgent(
            llm=llm,
            acceptance_threshold=acceptance_threshold,
            metrics=metrics,
        )
        validated = adversary.validate_quiz(
            knowledge_bricks=knowledge_bricks,
            quiz_data=candidates,
            output_path=None,
            num_questions=num_questions,
            rag_indexer=rag_indexer,
        )
        if not validated:
            raise Exception("Adversary validation returned empty quiz.")

        accepted = sum(1 for q in validated if not q.get("adversary_flag", False))
        log(f"Adversary: {accepted}/{len(validated)} questions accepted.")

        # ── Phase 5.5: Answer Consistency Validation ──────────────────────────
        set_stage("Checking Answer Consistency", 65)

        # C-2: build source_chunks mapping from each question's source_chunk_id
        source_chunks_for_validation = {}
        for q in validated:
            chunk_id = q.get("source_chunk_id")
            if chunk_id is not None and chunk_id >= 0 and chunk_id < len(rag_indexer.chunks):
                source_chunks_for_validation[q.get("id", 0)] = rag_indexer.chunks[chunk_id]

        consistency_validator = AnswerConsistencyValidator(strict=True)
        passed_consistency, rejected_consistency = consistency_validator.validate_batch(
            validated,
            source_chunks=source_chunks_for_validation if source_chunks_for_validation else None,
        )

        metrics.metrics.answer_consistency_failures = consistency_validator.get_failure_report().get(
            "answer_not_in_options", 0
        )
        metrics.metrics.explanation_consistency_failures = consistency_validator.get_failure_report().get(
            "explanation_mismatch", 0
        )
        metrics.metrics.unsupported_questions = (
            consistency_validator.get_failure_report().get("source_mismatch", 0)
            + consistency_validator.get_failure_report().get("unsupported_claim", 0)
        )
        metrics.metrics.ambiguity_failures = consistency_validator.get_failure_report().get("ambiguous_answer", 0)
        metrics.metrics.questions_with_issues = len(rejected_consistency)

        log(
            f"Consistency check: {len(passed_consistency)} passed, {len(rejected_consistency)} rejected."
        )
        validated = passed_consistency

        # ── Phase 6: Explainer ────────────────────────────────────────────────
        if mode == "fast":
            log("Fast mode: skipping Explainer (saves 10-15s).")
            final_quiz = validated
        else:
            set_stage("Generating Explanations", 80)
            explainer = ExplainerAgent(llm=llm, metrics=metrics)
            final_quiz = explainer.generate_explanations(
                knowledge_bricks=knowledge_bricks,
                quiz_data=validated,
                output_path=None,
                rag_indexer=rag_indexer,
            )
            if not final_quiz:
                raise Exception("Explainer returned empty quiz.")

        # ── Save outputs ──────────────────────────────────────────────────────
        set_stage("Saving Results", 95)
        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        final_md_path = OUTPUT_DIR / "Generated_Quiz.md"
        pedagogue.save_as_markdown(final_quiz, str(final_md_path))

        with open(final_md_path, "r", encoding="utf-8") as f:
            jobs[job_id]["result_markdown"] = f.read()

        jobs[job_id]["quiz"] = final_quiz

        metrics.save(str(OUTPUT_DIR))
        jobs[job_id]["metrics"] = {
            "total_time": metrics.metrics.total_time,
            "candidates_generated": metrics.metrics.candidates_generated,
            "questions_accepted": metrics.metrics.questions_accepted,
            "questions_rejected": metrics.metrics.questions_rejected,
            "acceptance_rate": metrics.metrics.acceptance_rate,
            "average_adversary_score": metrics.metrics.average_adversary_score,
            "estimated_tokens_total": metrics.metrics.estimated_tokens_total,
        }

        set_stage("Complete", 100)
        log(f"Generation complete. {len(final_quiz)} questions produced.")

    except Exception as e:
        jobs[job_id]["stage"] = "Error"
        jobs[job_id]["progress"] = 100
        log(str(e), "error")


@app.post("/generate")
async def generate_quiz(
    background_tasks: BackgroundTasks,
    pdf: UploadFile = File(...),
    mode: str = Form("accuracy"),
    num_questions: int = Form(20),
):
    job_id = str(uuid.uuid4())

    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / f"{job_id}_{pdf.filename}"

    with open(file_path, "wb") as f:
        f.write(await pdf.read())

    jobs[job_id] = {
        "stage": "Pending",
        "progress": 0,
        "logs": [],
        "result_markdown": None,
        "quiz": None,
        "metrics": None,
    }

    background_tasks.add_task(_process_quiz, job_id, str(file_path), mode, num_questions)

    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "stage": jobs[job_id]["stage"],
        "progress": jobs[job_id]["progress"],
        "logs": jobs[job_id]["logs"],
    }


@app.get("/result/{job_id}")
async def get_result(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    if jobs[job_id]["result_markdown"] is None:
        raise HTTPException(status_code=400, detail="Result not ready yet")

    return {
        "markdown": jobs[job_id]["result_markdown"],
        "quiz": jobs[job_id].get("quiz", []),
        "metrics": jobs[job_id].get("metrics"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)

