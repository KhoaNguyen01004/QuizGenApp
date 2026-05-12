# 🎯 Multi-Agent AI Quiz Generator

## 📌 Overview
A **local-first, multi-agent AI system** that converts academic lecture slides (PDFs) into **high-quality, validated quizzes**.

Designed for students and educators, the system runs entirely on **consumer hardware** (optimized for 4GB VRAM GPUs), ensuring:
- 🔒 Full data privacy (no external APIs)
- 💰 Zero inference cost
- ⚡ Efficient on-device performance

---

## 🧠 Core Idea

Instead of relying on a single large model, this project adopts a **modular multi-agent architecture** where each agent specializes in a specific cognitive task.

This design:
- Reduces hallucination
- Improves answer reliability
- Enables fine-grained debugging and optimization

---

## 🏗️ Architecture

### 🔁 Sequential Relay Orchestration

The system processes data through a pipeline of specialized agents:

---

## ⚙️ Pipeline Flow

### 1. 📄 Extraction
- Converts lecture slides (PDF) into structured Markdown
- Preserves layout (headers, tables, sections)

### 2. 🧩 Analysis — *Curator*
- Extracts key concepts (\"Knowledge Bricks\")
- Filters noise and irrelevant content

### 3. ✍️ Generation — *Pedagogue*
- Generates multiple-choice questions
- Applies Bloom’s Taxonomy for deeper understanding
- Creates realistic distractors

### 4. 🛡️ Validation — *Adversary*
- Cross-checks questions against source material
- Detects hallucinations and logical inconsistencies

### 5. 📚 Explanation — *Explainer*
- Produces detailed answer explanations
- Enhances learning and retention

---

## 🤖 Agent Stack

| Agent | Model | Responsibility | Approx. VRAM |
|------|------|----------------|-------------|
| **Curator** | `qwen3:1.7b` | Knowledge extraction | ~1.1 GB |
| **Pedagogue** | `llama3.2:3b` | Question generation | ~1.8 GB |
| **Adversary** | `llama3.2:3b` | Fact-checking & validation | ~1.8 GB |
| **Explainer** | `llama3.2:3b` | Answer explanation | ~1.8 GB |

> ⚠️ Models are loaded sequentially to stay within 4GB VRAM constraints.

---

## 🛠️ Technical Details

### 📄 PDF → Markdown Extraction

We use layout-aware parsing to maintain document structure:

```python
import pymupdf4llm
from pathlib import Path

def extract_pdf_to_md(path):
    content = pymupdf4llm.to_markdown(path)
    Path(\"extracted_lecture.md\").write_text(content, encoding=\"utf-8\")
    return content
```

---

## 🚀 Quick Start Guide

Follow these step-by-step instructions to set up and run QuizGenApp.

### Prerequisites
- **Python 3.12+** (check with `python --version`)
- **NVIDIA GPU with ≥4GB VRAM** (recommended for speed)
- **Ollama** (for AI model inference)

---

### Step 1: Install Ollama (AI Models)
1. Download Ollama from [https://ollama.com/download](https://ollama.com/download)
2. Install and run Ollama
3. Pull required models:
   ```bash
   ollama pull qwen3:1.7b
   ollama pull phi4-mini:latest
   ```
4. Verify installation:
   ```bash
   ollama list
   ollama serve  # Start Ollama server (keep running in background)
   ```

---

### Step 2: Set Up Python Environment
1. Clone or download the project
2. Navigate to project directory:
   ```bash
   cd path/to/QuizGenApp
   ```
3. Create virtual environment:
   ```bash
   python -m venv .venv
   ```
4. Activate virtual environment:
   ```powershell
   # Windows PowerShell
   .venv\Scripts\Activate.ps1
   ```
   ```bash
   # Linux/Mac
   source .venv/bin/activate
   ```

---

### Step 3: Install Python Dependencies
```bash
pip install -r requirements.txt
```

---

### Step 4: Enable GPU Acceleration (Optional but Recommended)
GPU acceleration speeds up PDF processing and AI generation significantly.

#### For PDF Extraction (PyTorch CUDA):
```bash
# Remove CPU-only PyTorch
pip uninstall torch torchvision torchaudio -y

# Install CUDA-enabled PyTorch (CUDA 12.1)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

#### Verify GPU Setup:
```bash
# Check PyTorch CUDA
python -c "import torch; print('PyTorch CUDA available:', torch.cuda.is_available())"

# Check NVIDIA GPU
nvidia-smi
```

**Note:** You may see dependency conflicts with `marker-pdf` requiring torch>=2.7.0, but torch 2.5.1+cu121 works correctly. These warnings are safe to ignore.

#### For Ollama GPU (Automatic):
Ollama automatically uses GPU if:
- NVIDIA drivers are installed
- CUDA is available
- GPU has sufficient VRAM

Verify with:
```bash
ollama ps  # Shows GPU usage
```

**Note:** If GPU setup fails, the app will run on CPU (slower but functional).

---

### Step 5: Prepare Your PDF
1. Place your lecture PDF file in the project root directory
   - Example: `Chapter 2. Transformation.pdf`
2. Ensure the PDF contains academic content (equations, text, etc.)

---

### Step 6: Run the Application
```bash
python main.py
```

**Expected Output:**
```
2026-04-28 XX:XX:XX - INFO - Processing Chapter 2. Transformation.pdf
2026-04-28 XX:XX:XX - INFO - GPU detected and will be used for PDF extraction.
2026-04-28 XX:XX:XX - INFO - Ollama GPU status: Ollama running (GPU support depends on installation)
...processing logs...
2026-04-28 XX:XX:XX - INFO - Quiz saved to Generated_Quiz.md
```

---

### Step 7: View Results
- **Quiz file**: `Generated_Quiz.md` (in project root)
- **Debug files** (in `outputs/` folder):
  - `knowledge_bricks.md` (extracted concepts)
  - `pedagogue_response.txt` (raw AI response)
  - `raw_extracted_pedagogue.json` (parsed quiz data)

---

## 📋 Alternative: Automated GPU Setup
Run the provided setup script:
```powershell
.\setup_gpu.ps1
```

This script handles PyTorch CUDA installation and provides Ollama GPU instructions.
```


### 2. Confirm Ollama Models (already pulled)
```
qwen3:1.7b     ✓
phi4-mini      ✓
gemma3:4b      ✓
llama3.2:1b    ✓
```
```bash
ollama list  # Verify
```

### 3. Run
Place PDF in project root (e.g., `Chapter 2. Transfomation.pdf`), then:
```bash
python main.py
```

**Output:** `Generated_Quiz.md` in project root.

---

## 📋 Usage

**Simple:**
1. Drop PDF file(s) in `d:/Code/QuizGenApp/`
2. `python main.py`
3. Check `Generated_Quiz.md`

**Notes:**
- Processes **first** PDF found in current directory
- Debug files: `knowledge_bricks.md`, `pedagogue_response.txt`
- Ensure `ollama serve` running in background

---

## 🧪 Troubleshooting

1. **No PDF found**: Place lecture PDF in project directory
2. **Ollama errors**: `ollama serve` + check models with `ollama list`
3. **VRAM issues**: Models load one-by-one automatically
4. **Extraction fails**: `pip install --upgrade pymupdf4llm marker-pdf`
5. **PDFExtractor using CPU?** Run GPU setup above + verify `torch.cuda.is_available()`. Check `nvidia-smi`.

## 📈 Next Steps
- [ ] Add CLI args (e.g., --pdf path)
- [ ] Streamlit UI
- [ ] OCR for image slides
- [ ] Export to Anki

---
*Built with ❤️ for academic excellence*

