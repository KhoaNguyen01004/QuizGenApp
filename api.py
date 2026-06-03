import os
import uuid
import asyncio
import json
import time
from datetime import datetime, timezone
from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

from backend.utils.text_extractor import PDFExtractor
from backend import curator, pedagogue
from backend.adversary import AdversaryAgent
from backend.explainer import ExplainerAgent
from configparser import ConfigParser

# Job internal state map
jobs: Dict[str, Dict[str, Any]] = {}

HISTORY_DIR = Path("history")
HISTORY_DIR.mkdir(exist_ok=True)


def _save_history(job_id: str, data: Dict[str, Any]) -> None:
    path = HISTORY_DIR / f"{job_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_history(job_id: str) -> Optional[Dict[str, Any]]:
    path = HISTORY_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _list_history() -> List[Dict[str, Any]]:
    entries = []
    for p in sorted(HISTORY_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            # Return lightweight metadata only (no quiz array, no markdown)
            entry = {k: data[k] for k in (
                "job_id", "pdf_filename", "created_at", "mode",
                "num_questions_requested", "num_questions", "metrics"
            ) if k in data}
            entries.append(entry)
        except Exception:
            continue
    return entries

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
    base_path = Path(".")
    start_time = time.monotonic()

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

        await asyncio.sleep(5)

        quiz_data = teacher.generate_quiz(
            knowledge_bricks=knowledge_bricks,
            output_path=None,
            num_questions=num_questions
        )

        if not quiz_data:
            raise Exception("Failed to generate quiz data.")

        candidates_generated = len(quiz_data)

        jobs[job_id]["stage"] = "Validating Questions"
        jobs[job_id]["progress"] = 70
        log(f"Generated {candidates_generated} questions. Validating...")

        adversary = AdversaryAgent(model=adversary_model, timeout=600)
        validated_quiz = adversary.validate_quiz(
            knowledge_bricks=knowledge_bricks,
            quiz_data=quiz_data,
            output_path=None
        )

        if not validated_quiz:
            raise Exception("Adversary validation returned an empty quiz.")

        # Compute adversary metrics from flagging data
        flagged_count = sum(1 for q in validated_quiz if q.get("adversary_flag", False))
        not_flagged_count = len(validated_quiz) - flagged_count
        avg_adversary_score = not_flagged_count / len(validated_quiz) if validated_quiz else 1.0

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
        final_md_path = OUTPUT_DIR / "Generate_Quiz.md"
        teacher.save_as_markdown(final_quiz, str(final_md_path))

        with open(final_md_path, "r", encoding="utf-8") as f:
            jobs[job_id]["result_markdown"] = f.read()

        jobs[job_id]["quiz"] = final_quiz

        total_time = time.monotonic() - start_time
        questions_accepted = len(final_quiz)
        questions_rejected = max(0, candidates_generated - questions_accepted)
        acceptance_rate = questions_accepted / candidates_generated if candidates_generated > 0 else 1.0
        estimated_tokens = int((len(md_content) + len(knowledge_bricks)) / 4 * 1.5)

        metrics = {
            "total_time": round(total_time, 1),
            "candidates_generated": candidates_generated,
            "questions_accepted": questions_accepted,
            "questions_rejected": questions_rejected,
            "acceptance_rate": round(acceptance_rate, 4),
            "average_adversary_score": round(avg_adversary_score * 10, 1),
            "estimated_tokens_total": estimated_tokens,
        }
        jobs[job_id]["metrics"] = metrics

        # Persist to history directory
        _save_history(job_id, {
            "job_id": job_id,
            "pdf_filename": jobs[job_id].get("pdf_filename", "unknown.pdf"),
            "created_at": jobs[job_id].get("created_at", datetime.now(timezone.utc).isoformat()),
            "mode": mode,
            "num_questions_requested": num_questions,
            "num_questions": questions_accepted,
            "metrics": metrics,
            "quiz": final_quiz,
            "markdown": jobs[job_id]["result_markdown"],
        })

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
        "pdf_filename": pdf.filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "num_questions_requested": num_questions,
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
        "logs": jobs[job_id]["logs"]
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


# ── History endpoints ──────────────────────────────────────────────────────

@app.get("/history")
async def get_history():
    return _list_history()


@app.get("/history/{job_id}")
async def get_history_entry(job_id: str):
    data = _load_history(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="History entry not found")
    return data


@app.delete("/history/{job_id}", status_code=204)
async def delete_history_entry(job_id: str):
    path = HISTORY_DIR / f"{job_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="History entry not found")
    path.unlink()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)