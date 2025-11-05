#!/bin/bash
# vLLM setup script for DGX Spark

set -e

echo "================================"
echo "vLLM Setup for DGX Spark"
echo "================================"

# Check for NVIDIA GPU
echo -e "\nChecking for NVIDIA GPU..."
nvidia-smi

# Create vLLM virtual environment
echo -e "\nCreating vLLM virtual environment..."
python3 -m venv venv-vllm
source venv-vllm/bin/activate

# Install vLLM
echo -e "\nInstalling vLLM..."
pip install vllm

# Model selection
echo -e "\n================================"
echo "Model Selection"
echo "================================"
echo ""
echo "Recommended models for DGX Spark:"
echo "1. Qwen/Qwen2.5-7B-Instruct (7B params, ~14GB VRAM)"
echo "2. Qwen/Qwen2.5-14B-Instruct (14B params, ~28GB VRAM)"
echo "3. Qwen/Qwen2.5-32B-Instruct (32B params, ~64GB VRAM)"
echo "4. meta-llama/Llama-3.1-8B-Instruct"
echo "5. mistralai/Mistral-7B-Instruct-v0.3"
echo ""

read -p "Enter model name (default: Qwen/Qwen2.5-7B-Instruct): " MODEL_NAME
MODEL_NAME=${MODEL_NAME:-"Qwen/Qwen2.5-7B-Instruct"}

# Create startup script
echo -e "\nCreating vLLM startup script..."
cat > start_vllm.sh << EOF
#!/bin/bash
# Start vLLM server

source venv-vllm/bin/activate

python -m vllm.entrypoints.openai.api_server \\
    --model $MODEL_NAME \\
    --host 0.0.0.0 \\
    --port 8000 \\
    --gpu-memory-utilization 0.9 \\
    --max-model-len 4096

EOF

chmod +x start_vllm.sh

echo -e "\n================================"
echo "vLLM setup complete!"
echo "================================"
echo ""
echo "To start vLLM server:"
echo "  ./start_vllm.sh"
echo ""
echo "Update your .env file:"
echo "  LLM_BACKEND=vllm"
echo "  LLM_API_URL=http://localhost:8000/v1"
echo "  LLM_MODEL=$MODEL_NAME"
echo ""
