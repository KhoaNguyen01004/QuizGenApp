Write-Host ""
Write-Host "========================================"
Write-Host " QuizGenApp Automatic Setup"
Write-Host "========================================"
Write-Host ""

# Create venv if missing

if (!(Test-Path "venv")) {
Write-Host "[1/7] Creating virtual environment..."
python -m venv venv
}

Write-Host "[2/7] Activating virtual environment..."
& .\venv\Scripts\Activate.ps1

Write-Host "[3/7] Upgrading pip..."
python -m pip install --upgrade pip

Write-Host "[4/7] Installing PyTorch (CPU build)..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

Write-Host "[5/7] Installing project requirements..."
pip install --no-cache-dir -r requirements.txt

Write-Host "[6/7] Checking Ollama..."

$ollamaExists = Get-Command ollama -ErrorAction SilentlyContinue

if (-not $ollamaExists) {
Write-Host ""
Write-Host "ERROR: Ollama is not installed."
Write-Host "Install Ollama first:"
Write-Host "https://ollama.com/download"
exit
}

Write-Host "[7/7] Checking required model..."

$models = ollama list

if ($models -notmatch "qwen3:1.7b") {
Write-Host "Downloading qwen3:1.7b..."
ollama pull qwen3:1.7b
}

Write-Host ""
Write-Host "========================================"
Write-Host " Setup Complete"
Write-Host "========================================"
Write-Host ""

Write-Host "Run project with:"
Write-Host ""
Write-Host "python main.py --mode fast --num 5"
Write-Host ""
pause
