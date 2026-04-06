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
| **Pedagogue** | `phi4-mini` | Question generation | ~2.3 GB |
| **Adversary** | `gemma3:4b` | Fact-checking & validation | ~2.6 GB |
| **Explainer** | `llama3.2:1b` | Answer explanation | ~0.8 GB |

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

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Ollama installed and running (`ollama serve`)
- NVIDIA GPU with ≥4GB VRAM (recommended)

#### 🔧 GPU Acceleration (for faster PDF extraction)
Marker library (used in PDFExtractor) requires PyTorch CUDA:

```
quizgenvenv\Scripts\activate
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**Verify:**
```
python -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.version.cuda)"
```
Expected: `CUDA: True 12.1`

**Note:** If `torch.cuda.is_available()` is False after install:
- Check `nvidia-smi` (driver/CUDA 12.1+)
- Restart terminal/VSCode

### 1. Virtual Environment & GPU Setup
```powershell
# Windows PowerShell
. quizgenvenv/Scripts/Activate.ps1
# Or CMD
quizgenvenv\\Scripts\\activate.bat

pip install -r requirements.txt

# GPU setup (if NVIDIA GPU)
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Verify GPU
python -c \"import torch; print('GPU ready:', torch.cuda.is_available())\"
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

