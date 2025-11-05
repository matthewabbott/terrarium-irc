#!/bin/bash
# Setup script for Terrarium IRC Bot

set -e

echo "================================"
echo "Terrarium IRC Bot Setup"
echo "================================"

# Check Python version
echo -e "\nChecking Python version..."
python3 --version

if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Create virtual environment
echo -e "\nCreating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo -e "\nUpgrading pip..."
pip install --upgrade pip

# Install dependencies
echo -e "\nInstalling dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo -e "\nCreating .env file..."
    cp .env.example .env
    echo "Please edit .env file with your configuration"
fi

# Create data directory
mkdir -p data

echo -e "\n================================"
echo "Setup complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your IRC and LLM settings"
echo "2. Install and start your LLM backend (Ollama or vLLM)"
echo "3. Run the bot: python main.py"
echo ""
echo "For Ollama setup:"
echo "  curl -fsSL https://ollama.com/install.sh | sh"
echo "  ollama pull qwen2.5:7b"
echo ""
