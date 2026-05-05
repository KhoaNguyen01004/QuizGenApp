import sys
import logging
from pathlib import Path
from backend.utils.text_extractor import PDFExtractor
from backend import curator, pedagogue

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    base_path = Path(".")
    OUTPUT_DIR = base_path / "outputs"
    OUTPUT_DIR.mkdir(exist_ok=True)
    pdf_files = list(base_path.glob("*.pdf"))
    if not pdf_files:
        logging.error("No PDF files found in current directory. Aborting.")
        return
    
    pdf_file = pdf_files[0]  # First PDF
    output_md = OUTPUT_DIR / "Generated_Quiz.md"
    
    logging.info(f"Processing {pdf_file.name}...")
    
    # 1. Fast extraction first, precision only if needed
    extractor = PDFExtractor()
    md_content = extractor.fast_extract(str(pdf_file))

    need_precision = False
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
    
    # 3. Generate quiz
    teacher = pedagogue.PedagogueAgent()
    quiz_data = teacher.generate_quiz(
        knowledge_bricks=knowledge_bricks,
        output_path=str(output_md)
    )
    
    # 4. Check
    if quiz_data and len(quiz_data) > 0:
        logging.info("Quiz saved to Generated_Quiz.md")
        logging.info(f"Generated {len(quiz_data)} questions.")
        logging.info(f"Preview Q1: {quiz_data[0].get('question', 'N/A')[:100]}...")
    else:
        logging.error("Failed to generate quiz data.")
        logging.info("Check pedagogue_response.txt and knowledge_bricks.md for debug.")

if __name__ == "__main__":
    main()

