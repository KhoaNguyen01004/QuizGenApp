"""QuizGenApp — CLI entry point.

Pipeline:
  PDF → Extraction → RAG Index → Curator → Pedagogue → Adversary
      → ConsistencyValidator → Explainer → Quiz

Usage:
  python main.py                          # accuracy mode, 20 questions
  python main.py --mode fast --num 10     # fast mode, 10 questions
  python main.py --mode accuracy --num 30 # accuracy mode, 30 questions
"""

import logging
import sys
from configparser import ConfigParser
from pathlib import Path

from backend.adversary import AdversaryAgent
from backend.curator import CuratorAgent
from backend.explainer import ExplainerAgent
from backend.llm_provider import LLMProvider
from backend.pedagogue import PedagogueAgent
from backend.utils.metrics import MetricsCollector
from backend.utils.rag import RAGIndexer, chunk_document
from backend.utils.text_extractor import PDFExtractor
from backend.validators import AnswerConsistencyValidator


def main():
    # ── CLI argument parsing ──────────────────────────────────────────────────
    mode = "accuracy"
    if "--mode" in sys.argv:
        try:
            mode = sys.argv[sys.argv.index("--mode") + 1].strip().lower()
        except Exception:
            mode = "accuracy"
    elif "--fast" in sys.argv:
        mode = "fast"
    elif "--accuracy" in sys.argv:
        mode = "accuracy"

    if mode in {"precise"}:
        mode = "accuracy"
    if mode not in {"fast", "accuracy"}:
        mode = "accuracy"

    num_questions = 20
    if "--num" in sys.argv:
        try:
            num_questions = int(sys.argv[sys.argv.index("--num") + 1])
        except Exception:
            pass

    base_path = Path(".")
    OUTPUT_DIR = base_path / "outputs"
    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── Config ────────────────────────────────────────────────────────────────
    cfg = ConfigParser()
    cfg.read(str(base_path / "config.ini"), encoding="utf-8")

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

    # H-5: configure logging level from config
    log_level_str = logging_cfg.get("level", "INFO").strip().upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    # Re-apply to root logger in case basicConfig was already called
    logging.getLogger().setLevel(log_level)

    # ── Metrics ───────────────────────────────────────────────────────────────
    metrics = MetricsCollector()
    metrics.metrics.model_used = model_name
    metrics.metrics.num_questions_requested = num_questions

    # ── Find PDF ──────────────────────────────────────────────────────────────
    pdf_files = list(base_path.glob("*.pdf"))
    if not pdf_files:
        logging.error("No PDF files found in current directory. Aborting.")
        return

    pdf_file = pdf_files[0]
    output_md = OUTPUT_DIR / "Generated_Quiz.md"
    logging.info(f"Processing: {pdf_file.name} (mode={mode}, questions={num_questions})")

    # ── Phase 1: PDF Extraction ───────────────────────────────────────────────
    metrics.start_timer("extraction")
    # H-4: pass use_gpu and batch_multiplier from config
    extractor = PDFExtractor(use_gpu=use_gpu, batch_multiplier=batch_multiplier)

    if mode == "fast":
        md_content = extractor.fast_extract(str(pdf_file)) or ""
        if not md_content:
            logging.error("Fast extraction returned no content. Aborting.")
            return
    else:
        md_content = extractor.fast_extract(str(pdf_file)) or ""
        need_precision = True
        if md_content and len(md_content) >= 3000:
            import re
            if not re.search(r"\\[a-zA-Z]|\$|\\\(|\\\)", md_content):
                need_precision = False

        if need_precision:
            logging.info("Running precision extraction for accuracy...")
            md_content = extractor.precision_extract(str(pdf_file))
            if not md_content:
                logging.error("Extraction failed. Aborting.")
                return

    metrics.stop_timer("extraction")
    logging.info(f"Extracted {len(md_content):,} characters.")

    metrics.set_ocr_times(
        native_time=extractor.native_time,
        ocr_time=extractor.ocr_time,
        ocr_skipped=(extractor.ocr_time == 0.0),
    )

    # ── Phase 2: RAG Indexing ─────────────────────────────────────────────────
    metrics.start_timer("rag_index")
    logging.info("Building RAG index...")

    chunks = chunk_document(md_content, chunk_size=chunk_size, overlap=chunk_overlap)
    logging.info(f"Document chunked into {len(chunks)} segments.")

    # H-2: pass metrics so RAGIndexer can record retrieval latency
    rag_indexer = RAGIndexer(model_name=embedding_model, metrics=metrics)
    rag_indexer.build_index(chunks)

    metrics.stop_timer("rag_index")

    # ── Shared LLM Provider ───────────────────────────────────────────────────
    llm = LLMProvider(model=model_name, timeout=600)

    # ── Phase 3: Curator ──────────────────────────────────────────────────────
    curator = CuratorAgent(llm=llm, metrics=metrics)
    knowledge_bricks = curator.extract_knowledge(
        md_content=md_content,
        rag_indexer=rag_indexer,
        top_k=top_k,
    )
    if not knowledge_bricks:
        logging.error("Knowledge extraction failed. Aborting.")
        return

    # ── Phase 4: Pedagogue ────────────────────────────────────────────────────
    pedagogue = PedagogueAgent(llm=llm, metrics=metrics)
    candidates = pedagogue.generate_quiz(
        knowledge_bricks=knowledge_bricks,
        output_path=None,
        num_questions=num_questions,
        rag_indexer=rag_indexer,
        candidate_multiplier=candidate_multiplier,
    )
    if not candidates:
        logging.error("Failed to generate candidate questions. Aborting.")
        return

    logging.info(f"Generated {len(candidates)} candidate questions.")

    # ── Phase 5: Adversary ────────────────────────────────────────────────────
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
        logging.error("Adversary validation returned empty quiz. Aborting.")
        return

    accepted_count = sum(1 for q in validated if not q.get("adversary_flag", False))
    logging.info(f"Adversary: {accepted_count}/{len(validated)} questions accepted.")

    # ── Phase 5.5: Answer Consistency Validation (C-4 fix: mirrors api.py) ───
    # C-2 fix: build source_chunks mapping from question source_chunk_id fields
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

    logging.info(
        f"Consistency check: {len(passed_consistency)} passed, {len(rejected_consistency)} rejected."
    )
    validated = passed_consistency

    # ── Phase 6: Explainer ────────────────────────────────────────────────────
    if mode == "fast":
        logging.info("Fast mode: skipping Explainer (saves 10-15s).")
        final_quiz = validated
    else:
        explainer = ExplainerAgent(llm=llm, metrics=metrics)
        final_quiz = explainer.generate_explanations(
            knowledge_bricks=knowledge_bricks,
            quiz_data=validated,
            output_path=None,
            rag_indexer=rag_indexer,
        )
        if not final_quiz:
            logging.error("Explainer returned empty quiz. Aborting.")
            return

    # ── Save final quiz ───────────────────────────────────────────────────────
    pedagogue.save_as_markdown(final_quiz, str(output_md))
    logging.info(f"Quiz saved to: {output_md}")
    logging.info(f"Final quiz: {len(final_quiz)} questions.")

    if final_quiz:
        logging.info(f"Preview Q1: {final_quiz[0].get('question', 'N/A')[:100]}...")

    # ── Save metrics ──────────────────────────────────────────────────────────
    metrics.save(str(OUTPUT_DIR))


if __name__ == "__main__":
    main()
