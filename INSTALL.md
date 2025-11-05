# Installation Guide for NVIDIA DGX Spark

This guide provides step-by-step instructions for setting up the Terrarium IRC Bot on your NVIDIA DGX Spark machine.

## Prerequisites

- NVIDIA DGX Spark with CUDA-capable GPU(s)
- Ubuntu 20.04+ or similar Linux distribution
- Python 3.10 or higher
- Internet connection for downloading models
- Access to an IRC server

## Installation Steps

### 1. System Preparation

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required system packages
sudo apt install -y python3 python3-pip python3-venv git sqlite3

# Verify GPU is available
nvidia-smi
```

### 2. Clone Repository

```bash
git clone <your-repository-url>
cd terrarium-irc
```

### 3. Run Setup Script

```bash
./setup.sh
```

This will:
- Create a Python virtual environment
- Install all required dependencies
- Create a `.env` configuration file
- Set up the data directory

### 4. Choose and Setup LLM Backend

#### Option A: Ollama (Easiest)

Ollama is recommended for getting started quickly:

```bash
./setup_ollama.sh
```

This will:
- Install Ollama
- Start the Ollama service
- Download the Qwen 2.5 7B model (default)
- Optionally download larger models

**Manual Ollama Installation:**

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
sudo systemctl enable ollama
sudo systemctl start ollama

# Pull models
ollama pull qwen2.5:7b      # 7B model (recommended)
ollama pull qwen2.5:14b     # 14B model (better quality)
ollama pull qwen2.5:32b     # 32B model (best quality)

# Verify installation
ollama list
```

#### Option B: vLLM (Best Performance)

vLLM is recommended for production use on DGX Spark:

```bash
./setup_vllm.sh
```

This will:
- Create a separate vLLM virtual environment
- Install vLLM with CUDA support
- Create a startup script for vLLM server

**Starting vLLM Server:**

```bash
# Start vLLM server (created by setup script)
./start_vllm.sh

# Or manually:
source venv-vllm/bin/activate
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-7B-Instruct \
    --host 0.0.0.0 \
    --port 8000 \
    --gpu-memory-utilization 0.9 \
    --max-model-len 4096
```

### 5. Configure the Bot

Edit the `.env` file with your settings:

```bash
nano .env
```

**For IRC Configuration:**

```ini
IRC_SERVER=irc.libera.chat    # Your IRC server
IRC_PORT=6667                  # Port (6667 for plain, 6697 for SSL)
IRC_USE_SSL=false             # Use true for SSL/TLS
IRC_NICK=terrarium-bot        # Your bot's nickname
IRC_CHANNELS=#test,#mychannel # Comma-separated channel list
```

**For Ollama:**

```ini
LLM_BACKEND=ollama
LLM_MODEL=qwen2.5:7b
LLM_API_URL=http://localhost:11434
```

**For vLLM:**

```ini
LLM_BACKEND=vllm
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
LLM_API_URL=http://localhost:8000/v1
```

### 6. Test the Bot

```bash
# Activate virtual environment
source venv/bin/activate

# Run the bot
python main.py
```

You should see output like:

```
============================================================
Terrarium IRC Bot
============================================================
Server: irc.libera.chat:6667 (SSL: False)
Nick: terrarium-bot
Channels: #test, #mychannel
LLM: ollama (qwen2.5:7b)
Database: ./data/irc_logs.db
============================================================

Initializing database...
Database ready.

Initializing LLM client (ollama)...
LLM client ready.

Starting bot...

Connecting to irc.libera.chat:6667...
Connected as terrarium-bot
Joining channels: #test, #mychannel
Joined #test
Joined #mychannel
```

### 7. Test Commands in IRC

Join the channel(s) with your IRC client and test:

```
.ping
.help
.ask What is 2 + 2?
.terrarium What are we talking about?
```

## Running as a Service (Production)

### 1. Edit the Service File

```bash
cp terrarium-bot.service /etc/systemd/system/
nano /etc/systemd/system/terrarium-bot.service
```

Update the following lines:
- Replace `USER_TO_REPLACE` with your username
- Replace `/path/to/terrarium-irc` with actual path

### 2. Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable terrarium-bot
sudo systemctl start terrarium-bot
```

### 3. Check Status

```bash
sudo systemctl status terrarium-bot
sudo journalctl -u terrarium-bot -f  # Follow logs
```

## GPU Memory Considerations

### Model Size vs. VRAM

| Model | VRAM Required | Notes |
|-------|---------------|-------|
| Qwen 2.5 7B | ~14GB | Recommended for most use cases |
| Qwen 2.5 14B | ~28GB | Better quality, needs more VRAM |
| Qwen 2.5 32B | ~64GB | Best quality, requires high-end GPU |
| Llama 3.1 8B | ~16GB | Alternative to Qwen |
| Llama 3.1 70B | ~140GB | Requires multiple GPUs |

### Check GPU Memory

```bash
# Monitor GPU usage
watch -n 1 nvidia-smi

# Or use detailed monitoring
nvidia-smi dmon
```

## Troubleshooting

### Bot won't start

```bash
# Check Python version
python3 --version  # Should be 3.10+

# Check virtual environment
source venv/bin/activate
which python  # Should point to venv

# Check dependencies
pip list | grep -E "miniirc|ollama|openai|aiosqlite"
```

### LLM backend not responding

**For Ollama:**

```bash
# Check Ollama status
systemctl status ollama

# Test Ollama
curl http://localhost:11434/api/tags

# Check models
ollama list
```

**For vLLM:**

```bash
# Check if vLLM is running
curl http://localhost:8000/v1/models

# Check vLLM logs
./start_vllm.sh  # Check output for errors
```

### Database issues

```bash
# Check database file
ls -lh data/irc_logs.db

# Test database
sqlite3 data/irc_logs.db "SELECT COUNT(*) FROM messages;"

# Reset database (WARNING: deletes all logs)
rm data/irc_logs.db
```

### IRC connection issues

```bash
# Test IRC server connectivity
telnet irc.libera.chat 6667

# For SSL:
openssl s_client -connect irc.libera.chat:6697

# Check firewall
sudo ufw status
```

## Performance Tuning

### For vLLM

Adjust in `start_vllm.sh`:

```bash
# Increase batch size for throughput
--max-num-batched-tokens 2048

# Reduce memory usage
--gpu-memory-utilization 0.8

# Enable tensor parallelism (multi-GPU)
--tensor-parallel-size 2
```

### For Bot

Adjust in `.env`:

```ini
# More context for better responses
MAX_CONTEXT_MESSAGES=100

# Faster responses (less context)
MAX_CONTEXT_MESSAGES=25
```

## Upgrading

```bash
# Pull latest code
git pull

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Restart bot
sudo systemctl restart terrarium-bot
```

## Next Steps

- Customize commands in `bot/commands.py`
- Adjust system prompt in `llm/context.py`
- Set up log rotation for the database
- Configure backup for IRC logs
- Monitor performance with `nvidia-smi`

For more information, see the main [README.md](README.md).
