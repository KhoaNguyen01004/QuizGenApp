import sys
import logging
from pathlib import Path
from backend.utils.text_extractor import PDFExtractor
from backend import curator, pedagogue
from backend.adversary import AdversaryAgent
from backend.explainer import ExplainerAgent
from configparser import ConfigParser


# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    # -----------------------------
    # Mode selection (CLI)
    # -----------------------------
    # Default: accuracy (preserves existing behavior)
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

    # Allow historical/alias modes
    if mode in {"precise"}:
        mode = "accuracy"

    if mode not in {"fast", "accuracy"}:
        logging.warning(f"Unknown mode '{mode}', falling back to 'accuracy'.")
        mode = "accuracy"

    num_questions = 30  # minimum target when caller does not specify --num
    if "--num" in sys.argv:
        try:
            num_questions = int(sys.argv[sys.argv.index("--num") + 1])
        except Exception:
            pass
    # If --num is provided, honor it exactly for fast/smaller tests.
    # Default remains 30 when --num is not passed.
    # (Previously this was forced up to a minimum of 30.)

    base_path = Path(".")


    OUTPUT_DIR = base_path / "outputs"
    OUTPUT_DIR.mkdir(exist_ok=True)
    pdf_files = list(base_path.glob("*.pdf"))
    if not pdf_files:
        logging.error("No PDF files found in current directory. Aborting.")
        return

    pdf_file = pdf_files[0]  # First PDF
    output_md = OUTPUT_DIR / "Generated_Quiz.md"

    logging.info(f"Processing {pdf_file.name} (mode={mode})...")

    # 1. Extraction
    extractor = PDFExtractor()

    if mode == "fast":
        # Performance guarantee: NEVER call precision_extract in fast mode.
        md_content = extractor.fast_extract(str(pdf_file)) or ""

        if not md_content:
            logging.error("Fast extraction returned no content; aborting (Marker is intentionally skipped in fast mode).")
            return
    else:
        # accuracy mode: fast first, precision only if needed
        md_content = extractor.fast_extract(str(pdf_file)) or ""

        need_precision = True
        if not md_content:
            logging.info("Fast extraction returned nothing, falling back to precision extraction.")
            need_precision = True
        else:
            # Heuristics: if content is short or contains LaTeX/math markers, use precision
            if len(md_content) < 3000:
                logging.info("Fast extraction produced small output; will run precision extraction for accuracy.")
                need_precision = True
            else:
                import re
                if re.search(r"\\[a-zA-Z]|\$|\\\(|\\\)", md_content):
                    logging.info("Math-like content detected in fast extraction; running precision extraction for accuracy.")
                    need_precision = True

        if need_precision:
            md_content = extractor.precision_extract(str(pdf_file))
            if not md_content:
                logging.error("Extraction failed. Aborting.")
                return

    
    logging.info(f"Extracted {len(md_content)} chars of MD.")

    
    # 2. Curate knowledge
    curator_agent = curator.CuratorAgent()
    knowledge_bricks = curator_agent.extract_knowledge(md_content)
    if not knowledge_bricks:
        logging.error("Knowledge extraction failed. Aborting.")
        return
    
    # 3. Generate quiz (Pedagogue)
    cfg = ConfigParser()
    cfg.read(str(base_path / "config.ini"), encoding="utf-8")
    models = cfg["models"] if cfg.has_section("models") else {}

    pedagogue_model = models.get("pedagogue_model", "llama3.2:3b")
    adversary_model = models.get("adversary_model", "llama3.2:3b")
    explainer_model = models.get("explainer_model", "llama3.2:3b")

    # Pedagogue can be slow on CPU/GPU; increase to avoid phase-1 lockups.
    teacher = pedagogue.PedagogueAgent(model=pedagogue_model, timeout=600)

    # Give Ollama a short cooldown between model swaps (helps on low-VRAM GPUs / Windows).
    import time
    time.sleep(10)

    quiz_data = teacher.generate_quiz(
        knowledge_bricks=knowledge_bricks,
        output_path=None,  # Save only after Explainer phase
        num_questions=num_questions,
    )

    if not quiz_data:

        logging.error("Failed to generate quiz data.")
        logging.info("Check pedagogue_response.txt and knowledge_bricks.md for debug.")
        return

    logging.info(f"Generated {len(quiz_data)} questions (pre-validation).")

    # 4. Validation (Adversary)
    adversary = AdversaryAgent(model=adversary_model, timeout=600)

    validated_quiz = adversary.validate_quiz(
        knowledge_bricks=knowledge_bricks,
        quiz_data=quiz_data,
        output_path=None,
    )

    if not validated_quiz:
        logging.error("Adversary validation returned empty quiz.")
        return

    logging.info(
        "Validation complete. Flagged items: %s",
        sum(1 for q in validated_quiz if isinstance(q, dict) and bool(q.get("adversary_flag"))),
    )

    # 5. Explanation (Explainer)


    explainer = ExplainerAgent(model=explainer_model, timeout=600)

    final_quiz = explainer.generate_explanations(
        knowledge_bricks=knowledge_bricks,
        quiz_data=validated_quiz,
        output_path=None,
    )

    if not final_quiz:
        logging.error("Explainer generation returned empty quiz.")
        return

    # Save only after Explainer phase
    teacher.save_as_markdown(final_quiz, str(output_md))

    logging.info("Quiz saved to Generated_Quiz.md")
    logging.info(f"Generated {len(final_quiz)} questions.")
    logging.info(f"Preview Q1: {final_quiz[0].get('question', 'N/A')[:100]}...")


if __name__ == "__main__":
    main()

