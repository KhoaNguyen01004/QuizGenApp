import os
import uuid
import asyncio
from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from pathlib import Path
import logging

from backend.utils.text_extractor import PDFExtractor
from backend import curator, pedagogue
from backend.adversary import AdversaryAgent
from backend.explainer import ExplainerAgent
from configparser import ConfigParser

# Job internal state map
jobs: Dict[str, Dict[str, Any]] = {}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)

async def _process_quiz(job_id: str, file_path: str, mode: str, num_questions: int):
    # Base paths
    base_path = Path(".")
    
    def log(msg, level="info"):
        if level == "info":
            logging.info(msg)
        elif level == "error":
            logging.error(msg)
        jobs[job_id]["logs"].append(f"[{level.upper()}] {msg}")

    try:
        jobs[job_id]["stage"] = "Extracting PDF"
        jobs[job_id]["progress"] = 10
        log(f"Processing started for job {job_id} in mode {mode}.")

        extractor = PDFExtractor()
        
        if mode == "fast":
            md_content = extractor.fast_extract(file_path) or ""
            if not md_content:
                raise Exception("Fast extraction returned no content.")
        else:
            md_content = extractor.fast_extract(file_path) or ""
            need_precision = True
            if md_content:
                if len(md_content) >= 3000:
                    import re
                    if not re.search(r"\\\[a-zA-Z]|\$|\\\(|\\\)", md_content):
                        need_precision = False
            
            if need_precision:
                log("Running precision extraction for accuracy.")
                md_content = extractor.precision_extract(file_path)
                if not md_content:
                    raise Exception("Precision extraction failed.")
                    
        jobs[job_id]["stage"] = "Curating Knowledge"
        jobs[job_id]["progress"] = 30
        log(f"Extracted {len(md_content)} chars of MD.")
        
        curator_agent = curator.CuratorAgent()
        knowledge_bricks = curator_agent.extract_knowledge(md_content)
        if not knowledge_bricks:
            raise Exception("Knowledge extraction failed.")
            
        jobs[job_id]["stage"] = "Generating Questions"
        jobs[job_id]["progress"] = 50
        
        cfg = ConfigParser()
        cfg.read(str(base_path / "config.ini"), encoding="utf-8")
        models = cfg["models"] if cfg.has_section("models") else {}
        
        pedagogue_model = models.get("pedagogue_model", "llama3.2:3b")
        adversary_model = models.get("adversary_model", "llama3.2:3b")
        explainer_model = models.get("explainer_model", "llama3.2:3b")
        
        teacher = pedagogue.PedagogueAgent(model=pedagogue_model, timeout=600)
        
        # Async delay
        await asyncio.sleep(5)
        
        quiz_data = teacher.generate_quiz(
            knowledge_bricks=knowledge_bricks, 
            output_path=None, 
            num_questions=num_questions
        )
        
        if not quiz_data:
            raise Exception("Failed to generate quiz data.")
            
        jobs[job_id]["stage"] = "Validating Questions"
        jobs[job_id]["progress"] = 70
        log(f"Generated {len(quiz_data)} questions. Validating...")
        
        adversary = AdversaryAgent(model=adversary_model, timeout=600)
        validated_quiz = adversary.validate_quiz(
            knowledge_bricks=knowledge_bricks,
            quiz_data=quiz_data,
            output_path=None
        )
        
        if not validated_quiz:
            raise Exception("Adversary validation returned an empty quiz.")
            
        jobs[job_id]["stage"] = "Creating Explanations"
        jobs[job_id]["progress"] = 85
        log("Validation complete. Generating explanations...")
        
        explainer = ExplainerAgent(model=explainer_model, timeout=600)
        final_quiz = explainer.generate_explanations(
            knowledge_bricks=knowledge_bricks,
            quiz_data=validated_quiz,
            output_path=None
        )
        
        if not final_quiz:
            raise Exception("Explainer generation returned an empty quiz.")
            
        jobs[job_id]["stage"] = "Complete"
        jobs[job_id]["progress"] = 100
        
        OUTPUT_DIR = base_path / "outputs"
        OUTPUT_DIR.mkdir(exist_ok=True)
        final_md_path = OUTPUT_DIR / f"{job_id}.md"
        teacher.save_as_markdown(final_quiz, str(final_md_path))
        
        with open(final_md_path, "r", encoding="utf-8") as f:
            jobs[job_id]["result_markdown"] = f.read()

        log("Generation finished successfully.")

    except Exception as e:
        jobs[job_id]["stage"] = "Error"
        jobs[job_id]["progress"] = 100
        log(str(e), "error")


@app.post("/generate")
async def generate_quiz(
    background_tasks: BackgroundTasks,
    pdf: UploadFile = File(...),
    mode: str = Form("accuracy"),
    num_questions: int = Form(20)
):
    job_id = str(uuid.uuid4())
    
    # Save uploaded file
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / f"{job_id}_{pdf.filename}"
    
    with open(file_path, "wb") as f:
        f.write(await pdf.read())

    # Initialize job state
    jobs[job_id] = {
        "stage": "Pending",
        "progress": 0,
        "logs": [],
        "result_markdown": None
    }

    # Start processing in background
    background_tasks.add_task(_process_quiz, job_id, str(file_path), mode, num_questions)

    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "stage": jobs[job_id]["stage"],
        "progress": jobs[job_id]["progress"],
        "logs": jobs[job_id]["logs"]
    }

@app.get("/result/{job_id}")
async def get_result(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if jobs[job_id]["result_markdown"] is None:
        raise HTTPException(status_code=400, detail="Result not ready yet")
        
    return {"markdown": jobs[job_id]["result_markdown"]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)