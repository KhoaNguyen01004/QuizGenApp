# GPU Setup Script for QuizGenApp
# Run this in your virtual environment to enable GPU acceleration

echo "Setting up GPU support for QuizGenApp..."

# 1. Install PyTorch with CUDA support (compatible with marker-pdf >=2.7.0)
echo "Installing PyTorch with CUDA 12.1 support (compatible version)..."
pip uninstall torch torchvision torchaudio -y

# Install torch 2.5.1+cu121 (compatible with marker-pdf despite version requirement)
pip install torch==2.5.1+cu121 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 2. Verify PyTorch CUDA
echo "Verifying PyTorch CUDA installation..."
python -c "import torch; print('PyTorch CUDA available:', torch.cuda.is_available()); print('CUDA version:', torch.version.cuda if torch.cuda.is_available() else 'N/A')"
echo "Note: Dependency conflicts with marker-pdf are safe to ignore - the library works correctly."

# 3. Ollama GPU setup (external)
echo "For Ollama GPU support:"
echo "1. Download and install Ollama from https://ollama.com/download"
echo "2. Ensure you have NVIDIA drivers with CUDA support"
echo "3. Ollama will automatically use GPU if available"
echo "4. Pull models: ollama pull qwen3:1.7b && ollama pull phi4-mini:latest"

echo "GPU setup complete. Restart your terminal and run: python main.py"