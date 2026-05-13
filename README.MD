# Multi-Agent AI Quiz Generator

## Overview
A local-first, multi-agent system that converts academic lecture PDFs into high-quality, validated quizzes.

The system is designed to run on consumer hardware (optimized for approximately 4GB VRAM GPUs) and avoids external APIs.

## Core idea
Instead of relying on a single model, the project uses a modular multi-agent architecture where each agent specializes in a specific cognitive task. This improves answer reliability and helps reduce hallucinations.

## Pipeline
1. Extraction: Converts lecture slides (PDF) into structured Markdown.
2. Curator: Extracts key concepts ("knowledge bricks") and filters irrelevant content.
3. Pedagogue: Generates quiz questions (multiple-choice) using a pedagogical approach.
4. Adversary: Validates questions against the extracted source material.
5. Explainer: Produces detailed explanations for the correct answers.

## Repository layout
- main.py: Entry point.
- backend/: Agent implementations.
- outputs/: Generated artifacts and debug outputs.
- config.ini: Model configuration.
- requirements.txt: Python dependencies.

## Requirements
- Python 3.12+
- Ollama installed and running locally
- (Recommended) NVIDIA GPU with sufficient VRAM

## Install and run
### 1) Install and run Ollama
1. Install Ollama: https://ollama.com/download
2. Start the Ollama server (keep it running):
   - On Windows you can run it from the Ollama app, or via the CLI if you prefer.
3. Pull required models (adjust as needed):
   ```bash
   ollama pull qwen3:1.7b
   ollama pull phi4-mini:latest
   ollama pull gemma3:4b
   ollama pull llama3.2:1b
   ```
4. Verify:
   ```bash
   ollama list
   ```

### 2) Set up Python
From this project directory:
```bash
python -m venv .venv
```
Activate:
- Windows PowerShell:
  ```powershell
  .venv\Scripts\Activate.ps1
  ```

- Linux/macOS:
  ```bash
  source .venv/bin/activate
  ```

Install dependencies:
```bash
pip install -r requirements.txt
```

### 3) Prepare your PDF
Place a lecture PDF in the project directory (the directory where main.py is located).

Important: the app processes the first PDF it finds in the current directory matching `*.pdf`.

Example: `Chapter 2. Transformation.pdf`

### 4) Run
Default mode (accuracy):
```bash
python main.py
```
Fast mode (skips precision extraction):
```bash
python main.py --mode fast
```
Choose number of questions (default is 30 if not provided):
```bash
python main.py --mode fast --num 20
```

## Outputs
- outputs/Generated_Quiz.md: Final quiz with explanations.
- outputs/: Additional debug artifacts are written by the backend components.

## Configuration
Models are controlled by config.ini:
- curator_model
- pedagogue_model
- adversary_model
- explainer_model

If you want to use different Ollama models, update config.ini accordingly.

## Troubleshooting
- No PDF found: ensure there is at least one `*.pdf` in the project directory.
- Ollama/model errors: confirm Ollama is running and models exist with `ollama list`.
- Performance issues: use `--mode fast` and/or ensure your GPU/VRAM are sufficient.

## Development notes (for contributors)
- main.py is the only entry point required to generate a quiz.
- The pipeline order is Extraction -> Curator -> Pedagogue -> Adversary -> Explainer.
- The app writes final results only after the Explainer phase.

