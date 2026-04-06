import sys
from pathlib import Path
from backend.utils.text_extractor import PDFExtractor
from backend import curator, pedagogue

def main():
    base_path = Path(".")
    OUTPUT_DIR = base_path / "outputs"
    OUTPUT_DIR.mkdir(exist_ok=True)
    pdf_files = list(base_path.glob("*.pdf"))
    if not pdf_files:
        print("No PDF files found in current directory. Aborting.")
        return
    
    pdf_file = pdf_files[0]  # First PDF
    output_md = OUTPUT_DIR / "Generated_Quiz.md"
    
    print(f"Processing {pdf_file.name}...")
    
    # 1. Advanced extraction
    extractor = PDFExtractor()
    md_content = extractor.precision_extract(str(pdf_file))
    if not md_content:
        print("Extraction failed. Aborting.")
        return
    
    print(f"Extracted {len(md_content)} chars of MD.")
    
    # 2. Curate knowledge
    curator_agent = curator.CuratorAgent()
    knowledge_bricks = curator_agent.extract_knowledge(md_content)
    
    # 3. Generate quiz
    teacher = pedagogue.PedagogueAgent()
    quiz_data = teacher.generate_quiz(
        knowledge_bricks=knowledge_bricks,
        output_path=str(output_md)
    )
    
    # 4. Check
    if quiz_data and len(quiz_data) > 0:
        print("\\n--- [SUCCESS] Quiz saved to Generated_Quiz.md ---")
        print(f"Generated {len(quiz_data)} questions.")
        print(f"Preview Q1: {quiz_data[0].get('question', 'N/A')[:100]}...")
    else:
        print("Failed to generate quiz data.")
        print("Check pedagogue_response.txt and knowledge_bricks.md for debug.")

if __name__ == "__main__":
    main()

