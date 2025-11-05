#!/bin/bash
# Ollama setup script for DGX Spark

set -e

echo "================================"
echo "Ollama Setup for DGX Spark"
echo "================================"

# Install Ollama
echo -e "\nInstalling Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
echo -e "\nStarting Ollama service..."
sudo systemctl enable ollama
sudo systemctl start ollama

# Wait for service to be ready
sleep 5

# Pull recommended models
echo -e "\nPulling recommended models..."
echo "This may take a while depending on your internet connection..."

# Qwen 2.5 - Excellent performance, various sizes
echo -e "\nPulling Qwen 2.5 7B (recommended for balance)..."
ollama pull qwen2.5:7b

# Optional: Pull other sizes
read -p "Pull Qwen 2.5 14B? (larger, better quality) [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ollama pull qwen2.5:14b
fi

read -p "Pull Qwen 2.5 32B? (largest, best quality, needs more VRAM) [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ollama pull qwen2.5:32b
fi

# List available models
echo -e "\nInstalled models:"
ollama list

echo -e "\n================================"
echo "Ollama setup complete!"
echo "================================"
echo ""
echo "Ollama is running on http://localhost:11434"
echo "You can now start the bot with: python main.py"
echo ""
