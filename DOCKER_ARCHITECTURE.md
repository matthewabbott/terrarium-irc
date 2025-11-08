# Docker Architecture & Orchestration

**Version**: 1.0
**Date**: 2025-11-08

## Executive Summary

This document defines the Docker containerization strategy for the Terrarium ecosystem running on the DGX Spark. All LLM-consuming services will be orchestrated via Docker Compose on a single machine.

**Key Decision**: **Yes, containerize terrarium-irc** and orchestrate all services together.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Why Docker Compose](#why-docker-compose)
3. [Service Catalog](#service-catalog)
4. [Docker Compose Configuration](#docker-compose-configuration)
5. [IRC Bot Containerization](#irc-bot-containerization)
6. [Graceful Degradation Strategy](#graceful-degradation-strategy)
7. [Development Workflow](#development-workflow)
8. [Deployment Guide](#deployment-guide)
9. [Future Services](#future-services)

---

## Architecture Overview

### The Terrarium Ecosystem

```
┌─────────────────────────────────────────────────────────────────┐
│ DGX Spark (Single Machine)                                      │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Docker Compose Network: terrarium-net                    │  │
│  │                                                           │  │
│  │  ┌─────────────┐         ┌──────────────────┐           │  │
│  │  │   vLLM      │────────→│ terrarium-agent  │           │  │
│  │  │ (GPU model) │ :8000   │ (HTTP API)       │           │  │
│  │  │             │         │ :8080            │           │  │
│  │  └─────────────┘         └──────────────────┘           │  │
│  │         ↑                        ↑                       │  │
│  │         │                        │                       │  │
│  │         │    ┌───────────────────┴──────────────┐       │  │
│  │         │    │                                   │       │  │
│  │  ┌──────┴────┴───┐  ┌───────────────┐  ┌───────┴──────┐│  │
│  │  │ terrarium-irc │  │terrarium-web  │  │terrarium-docs││  │
│  │  │ (IRC bot)     │  │(Web UI)       │  │(Doc reader)  ││  │
│  │  │               │  │:3000          │  │              ││  │
│  │  └───────────────┘  └───────────────┘  └──────────────┘│  │
│  │         │                                                │  │
│  │         ↓                                                │  │
│  │  ┌───────────────┐                                      │  │
│  │  │ SQLite Volume │  (irc_logs.db)                       │  │
│  │  └───────────────┘                                      │  │
│  │                                                           │  │
│  │  [Future: game harness, CLI tools, Discord bot, etc.]   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Host: /data/terrarium (persistent volumes)                     │
└─────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Single Orchestration Point**: One `docker-compose.yml` manages all services
2. **Shared Network**: All containers communicate via `terrarium-net`
3. **Graceful Degradation**: Services handle dependency failures gracefully
4. **Persistent Storage**: SQLite and configs stored in host volumes
5. **Development Friendly**: Easy to dev locally, deploy to production

---

## Why Docker Compose

### Rationale for Single-Machine Setup

**Perfect for DGX Spark because**:
- ✅ All services on one powerful machine
- ✅ Simple to manage and understand
- ✅ Low overhead compared to Kubernetes
- ✅ Easy dependency declaration
- ✅ Built-in networking and service discovery
- ✅ Volume management for persistence
- ✅ Easy to add new services

**Alternatives Considered**:

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Docker Compose** | Simple, declarative, single-file config | Single-host only | ✅ **Best fit** |
| **Kubernetes** | Production-grade, scales to clusters | Massive overkill for single machine | ❌ Too complex |
| **Systemd services** | Native to Linux, simple | No containerization, manual deps | ❌ Less portable |
| **Bare Python** | No overhead, direct execution | Manual dependency management | ❌ Hard to scale |

---

## Service Catalog

### Current Services

#### 1. vLLM (GPU Model Server)
- **Status**: Already containerized
- **Purpose**: Serves LLM model with GPU acceleration
- **Port**: 8000
- **Dependencies**: None (foundational service)
- **Resource**: GPU access required

#### 2. terrarium-agent (HTTP API Server)
- **Status**: Already containerized (or can be)
- **Purpose**: HTTP API for LLM access (stateless)
- **Port**: 8080
- **Dependencies**: vLLM (8000)
- **Resource**: Minimal (lightweight proxy)

#### 3. terrarium-irc (IRC Bot)
- **Status**: **NEW - To be containerized**
- **Purpose**: IRC logging + LLM chat bot
- **Port**: None (IRC client, outbound only)
- **Dependencies**:
  - terrarium-agent (8080) - Optional for LLM features
  - SQLite volume - Required for logging
- **Resource**: Minimal CPU/RAM

### Future Services

#### 4. terrarium-web (Web UI)
- **Purpose**: Browser-based chat interface
- **Port**: 3000
- **Dependencies**: terrarium-agent (8080)

#### 5. terrarium-docs (Document Processor)
- **Purpose**: Process technical docs, extract jargon, generate training data
- **Port**: None (batch processor)
- **Dependencies**: terrarium-agent (8080)

#### 6. terrarium-discord / terrarium-slack
- **Purpose**: Discord/Slack bots
- **Port**: None (clients)
- **Dependencies**: terrarium-agent (8080)

#### 7. terrarium-game-harness
- **Purpose**: Games/simulations using LLM
- **Port**: Varies
- **Dependencies**: terrarium-agent (8080)

---

## Docker Compose Configuration

### Master `docker-compose.yml`

**Location**: `~/Programming/terrarium-ecosystem/docker-compose.yml`

```yaml
version: '3.8'

networks:
  terrarium-net:
    driver: bridge

volumes:
  irc-data:
    driver: local
  web-data:
    driver: local

services:
  # ============================================================
  # Core LLM Infrastructure
  # ============================================================

  vllm:
    image: vllm/vllm-openai:latest
    container_name: vllm-server
    runtime: nvidia  # GPU access
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
    ports:
      - "8000:8000"
    volumes:
      - /data/models:/models:ro  # Model storage
    command: >
      --model /models/GLM-4.5-Air-AWQ-4bit
      --trust-remote-code
      --gpu-memory-utilization 0.9
      --dtype auto
      --api-key none
    networks:
      - terrarium-net
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  terrarium-agent:
    build:
      context: ./terrarium-agent
      dockerfile: Dockerfile
    container_name: terrarium-agent
    ports:
      - "8080:8080"
    environment:
      - VLLM_URL=http://vllm:8000
      - PORT=8080
    depends_on:
      - vllm
    networks:
      - terrarium-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # ============================================================
  # Client Services (LLM Consumers)
  # ============================================================

  terrarium-irc:
    build:
      context: ./terrarium-irc
      dockerfile: Dockerfile
    container_name: terrarium-irc
    environment:
      # IRC Configuration
      - IRC_SERVER=${IRC_SERVER:-irc.libera.chat}
      - IRC_PORT=${IRC_PORT:-6667}
      - IRC_USE_SSL=${IRC_USE_SSL:-false}
      - IRC_NICK=${IRC_NICK:-terrarium}
      - IRC_CHANNELS=${IRC_CHANNELS:-#test}

      # Agent Configuration
      - AGENT_API_URL=http://terrarium-agent:8080
      - AGENT_TEMPERATURE=0.8
      - AGENT_MAX_TOKENS=512

      # Context Management
      - MAX_CONVERSATION_TURNS=10
      - MAX_IRC_CONTEXT=30
      - CONTEXT_STALENESS_HOURS=2

      # Bot Configuration
      - COMMAND_PREFIX=.
      - DB_PATH=/data/irc_logs.db
    volumes:
      - irc-data:/data  # Persist SQLite database
    depends_on:
      - terrarium-agent
    networks:
      - terrarium-net
    restart: unless-stopped
    # Graceful degradation: Keep trying even if agent is down
    # IRC logging will continue, LLM features degrade gracefully

  # ============================================================
  # Future Services (Commented Out - Uncomment When Ready)
  # ============================================================

  # terrarium-web:
  #   build:
  #     context: ./terrarium-web
  #     dockerfile: Dockerfile
  #   container_name: terrarium-web
  #   ports:
  #     - "3000:3000"
  #   environment:
  #     - AGENT_API_URL=http://terrarium-agent:8080
  #   depends_on:
  #     - terrarium-agent
  #   networks:
  #     - terrarium-net
  #   restart: unless-stopped

  # terrarium-docs:
  #   build:
  #     context: ./terrarium-docs
  #     dockerfile: Dockerfile
  #   container_name: terrarium-docs
  #   environment:
  #     - AGENT_API_URL=http://terrarium-agent:8080
  #   volumes:
  #     - ./docs-input:/input:ro
  #     - ./docs-output:/output
  #   depends_on:
  #     - terrarium-agent
  #   networks:
  #     - terrarium-net
```

### Environment File (`.env`)

**Location**: `~/Programming/terrarium-ecosystem/.env`

```bash
# IRC Bot Configuration
IRC_SERVER=irc.libera.chat
IRC_PORT=6667
IRC_USE_SSL=false
IRC_NICK=terrarium
IRC_CHANNELS=#terrarium,#test

# Add more service configs as needed
```

---

## IRC Bot Containerization

### Dockerfile for terrarium-irc

**Location**: `~/Programming/terrarium-irc/Dockerfile`

```dockerfile
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite
RUN mkdir -p /data

# Run bot
CMD ["python", "main.py"]
```

### Directory Structure

```
terrarium-irc/
├── Dockerfile              # NEW
├── .dockerignore           # NEW
├── requirements.txt
├── main.py
├── bot/
├── llm/
├── storage/
└── data/                   # Mounted as volume, not copied
    └── irc_logs.db
```

### `.dockerignore`

```
# Don't copy these into the container
venv/
__pycache__/
*.pyc
.env
.git/
data/irc_logs.db  # Will be mounted as volume
*.md
tests/
.pytest_cache/
```

### Build and Run

```bash
# Build image
cd ~/Programming/terrarium-irc
docker build -t terrarium-irc:latest .

# Or use docker-compose (recommended)
cd ~/Programming/terrarium-ecosystem
docker-compose build terrarium-irc
docker-compose up terrarium-irc
```

---

## Graceful Degradation Strategy

### Design Philosophy

**Key Requirement**: IRC logging must continue even if LLM is unavailable.

### Implementation

#### 1. Health Check on Startup

```python
# main.py

async def main():
    # Initialize agent client
    agent_client = AgentClient(
        base_url=os.getenv('AGENT_API_URL', 'http://terrarium-agent:8080')
    )

    # Check agent health (non-blocking)
    agent_available = False
    try:
        agent_available = await agent_client.health_check()
        if agent_available:
            print("✓ Agent server is healthy - LLM features enabled")
        else:
            print("⚠ Agent server not available - LLM features disabled")
    except Exception as e:
        print(f"⚠ Agent health check failed: {e}")
        print("  IRC logging will continue, LLM commands will show error message")

    # Initialize bot (works regardless of agent status)
    bot = TerrariumBot(
        ...
        agent_client=agent_client,
        agent_available=agent_available,
        ...
    )

    await bot.run_forever()
```

#### 2. Graceful Command Handling

```python
# bot/commands.py

@staticmethod
async def cmd_terrarium(bot: 'TerrariumBot', channel: str, nick: str, args: str):
    """Handle .terrarium command with graceful degradation."""

    # Check if agent is available
    if not bot.agent_available:
        bot.send_message(
            channel,
            f"{nick}: Terra-irc is sleeping right now (LLM unavailable). "
            "Try again later or use .help for other commands."
        )
        return

    # Normal LLM processing
    try:
        # ... agent call ...
    except AgentConnectionError:
        # Agent went down mid-operation
        bot.agent_available = False  # Mark as unavailable
        bot.send_message(
            channel,
            f"{nick}: Terra-irc got too busy and needs a break. Try again in a moment."
        )
```

#### 3. Periodic Health Checks

```python
# bot/irc_client.py

class TerrariumBot:
    def __init__(self, ...):
        # ...
        self.health_check_interval = 60  # seconds

    async def run_forever(self):
        """Run bot with periodic health checks."""
        await self.connect()

        try:
            while self.running:
                # Sleep
                await asyncio.sleep(self.health_check_interval)

                # Check agent health
                try:
                    is_healthy = await self.agent_client.health_check()
                    if is_healthy and not self.agent_available:
                        print("✓ Agent server recovered - LLM features re-enabled")
                        self.agent_available = True
                    elif not is_healthy and self.agent_available:
                        print("⚠ Agent server went down - LLM features disabled")
                        self.agent_available = False
                except:
                    pass  # Ignore health check errors

        except KeyboardInterrupt:
            await self.shutdown()
```

### Degradation Matrix

| Component | When Agent Down | When Agent Up |
|-----------|----------------|---------------|
| **IRC Logging** | ✅ Works normally | ✅ Works normally |
| **`.help` command** | ✅ Works normally | ✅ Works normally |
| **`.ping` command** | ✅ Works normally | ✅ Works normally |
| **`.search` command** | ✅ Works (DB only) | ✅ Works (DB only) |
| **`.stats` command** | ✅ Works (DB only) | ✅ Works (DB only) |
| **`.ask` command** | ❌ "Terra-irc is sleeping" | ✅ Works with LLM |
| **`.terrarium` command** | ❌ "Terra-irc is sleeping" | ✅ Works with LLM |

---

## Development Workflow

### Local Development (Outside Docker)

For rapid development, you can still run services locally:

```bash
# Terminal 1: Start vLLM + agent (Docker)
cd ~/Programming/terrarium-ecosystem
docker-compose up vllm terrarium-agent

# Terminal 2: Run IRC bot locally (for faster iteration)
cd ~/Programming/terrarium-irc
source venv/bin/activate
export AGENT_API_URL=http://localhost:8080
python main.py
```

**Benefits**:
- Fast code changes (no rebuild)
- Easy debugging with print/breakpoints
- Direct access to SQLite file

### Testing in Docker

When ready to test containerized version:

```bash
# Build and run
cd ~/Programming/terrarium-ecosystem
docker-compose build terrarium-irc
docker-compose up terrarium-irc

# View logs
docker-compose logs -f terrarium-irc

# Shell into container
docker-compose exec terrarium-irc /bin/bash
```

### Hot Reload for Development

Add volume mount for live code updates during development:

```yaml
# docker-compose.override.yml (for development only)
version: '3.8'

services:
  terrarium-irc:
    volumes:
      - ./terrarium-irc:/app  # Mount source code
    environment:
      - DEBUG=true
```

```bash
# Use override file for dev
docker-compose -f docker-compose.yml -f docker-compose.override.yml up
```

---

## Deployment Guide

### Initial Setup

```bash
# 1. Create ecosystem directory
mkdir -p ~/Programming/terrarium-ecosystem
cd ~/Programming/terrarium-ecosystem

# 2. Clone/move repos
git clone <repo> terrarium-agent
git clone <repo> terrarium-irc
# (or move existing directories)

# 3. Create docker-compose.yml
cp <from this doc> docker-compose.yml

# 4. Create .env file
cp .env.example .env
vim .env  # Edit with your IRC settings

# 5. Build all services
docker-compose build

# 6. Start core infrastructure
docker-compose up -d vllm terrarium-agent

# 7. Wait for vLLM to load model
docker-compose logs -f vllm
# Wait for: "Application startup complete"

# 8. Start IRC bot
docker-compose up -d terrarium-irc

# 9. Check logs
docker-compose logs -f terrarium-irc
```

### Common Operations

```bash
# View all running services
docker-compose ps

# View logs
docker-compose logs -f [service-name]

# Restart a service
docker-compose restart terrarium-irc

# Stop all services
docker-compose down

# Update and rebuild
git pull
docker-compose build terrarium-irc
docker-compose up -d terrarium-irc

# Access SQLite database
docker-compose exec terrarium-irc sqlite3 /data/irc_logs.db
```

### Backup Strategy

```bash
# Backup IRC logs
docker cp terrarium-irc:/data/irc_logs.db ./backups/irc_logs_$(date +%Y%m%d).db

# Or use volume mount to host
docker-compose exec terrarium-irc cp /data/irc_logs.db /backup/
```

### Monitoring

```bash
# View resource usage
docker stats

# Health check all services
docker-compose ps
curl http://localhost:8000/health  # vLLM
curl http://localhost:8080/health  # agent

# IRC bot health (check logs for errors)
docker-compose logs --tail=50 terrarium-irc
```

---

## Future Services

### Adding New Services

When you're ready to add a new service (e.g., web UI):

#### 1. Create Service Directory

```bash
cd ~/Programming/terrarium-ecosystem
mkdir terrarium-web
cd terrarium-web
# ... create your web app ...
```

#### 2. Create Dockerfile

```dockerfile
FROM node:18-slim
WORKDIR /app
COPY package*.json .
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
```

#### 3. Add to docker-compose.yml

```yaml
services:
  # ... existing services ...

  terrarium-web:
    build:
      context: ./terrarium-web
    container_name: terrarium-web
    ports:
      - "3000:3000"
    environment:
      - AGENT_API_URL=http://terrarium-agent:8080
    depends_on:
      - terrarium-agent
    networks:
      - terrarium-net
    restart: unless-stopped
```

#### 4. Start Service

```bash
docker-compose build terrarium-web
docker-compose up -d terrarium-web
```

### Planned Services

#### terrarium-web (Web Chat UI)
```yaml
terrarium-web:
  build: ./terrarium-web
  ports: ["3000:3000"]
  environment:
    - AGENT_API_URL=http://terrarium-agent:8080
    - ENABLE_STREAMING=true
```

#### terrarium-docs (Document Processor)
```yaml
terrarium-docs:
  build: ./terrarium-docs
  volumes:
    - ./docs-input:/input:ro
    - ./docs-output:/output
  environment:
    - AGENT_API_URL=http://terrarium-agent:8080
    - BATCH_SIZE=10
```

#### terrarium-discord (Discord Bot)
```yaml
terrarium-discord:
  build: ./terrarium-discord
  environment:
    - DISCORD_TOKEN=${DISCORD_TOKEN}
    - AGENT_API_URL=http://terrarium-agent:8080
```

---

## Directory Structure

### Recommended Ecosystem Layout

```
~/Programming/terrarium-ecosystem/
├── docker-compose.yml          # Master orchestration file
├── .env                        # Environment variables
├── .env.example                # Example config
├── README.md                   # Overview of ecosystem
│
├── terrarium-agent/            # HTTP API server
│   ├── Dockerfile
│   ├── server.py
│   └── ...
│
├── terrarium-irc/              # IRC bot
│   ├── Dockerfile
│   ├── main.py
│   ├── bot/
│   ├── llm/
│   └── storage/
│
├── terrarium-web/              # Web UI (future)
│   ├── Dockerfile
│   └── ...
│
├── terrarium-docs/             # Doc processor (future)
│   ├── Dockerfile
│   └── ...
│
└── data/                       # Persistent data (host volume)
    ├── irc/
    │   └── irc_logs.db
    ├── models/                 # LLM models
    └── backups/
```

---

## Migration Steps

### From Current Setup to Docker

#### Phase 1: Containerize terrarium-agent (if not already done)

```bash
cd ~/Programming/terrarium-agent
# Create Dockerfile (if needed)
docker build -t terrarium-agent:latest .
```

#### Phase 2: Create Ecosystem Directory

```bash
mkdir ~/Programming/terrarium-ecosystem
cd ~/Programming/terrarium-ecosystem

# Move or symlink existing repos
ln -s ~/Programming/terrarium-agent terrarium-agent
ln -s ~/Programming/terrarium-irc terrarium-irc
```

#### Phase 3: Create docker-compose.yml

Copy the master configuration from this document.

#### Phase 4: Test Core Services

```bash
# Start just vLLM and agent first
docker-compose up vllm terrarium-agent

# Verify agent works
curl http://localhost:8080/health
```

#### Phase 5: Add terrarium-irc

```bash
# Create Dockerfile in terrarium-irc
cd terrarium-irc
# ... create Dockerfile ...

# Build and test
cd ~/Programming/terrarium-ecosystem
docker-compose build terrarium-irc
docker-compose up terrarium-irc
```

#### Phase 6: Migrate Data

```bash
# Copy existing SQLite database to volume
docker cp ~/Programming/terrarium-irc/data/irc_logs.db terrarium-irc:/data/
```

---

## Comparison: Pre-Docker vs. Post-Docker

| Aspect | Before (Manual) | After (Docker Compose) |
|--------|----------------|------------------------|
| **Startup** | 3 manual commands in 3 terminals | `docker-compose up -d` |
| **Dependencies** | Manual venv, pip installs | Handled by Dockerfile |
| **Service Discovery** | Hardcoded localhost:8000 | Docker DNS (vllm:8000) |
| **Adding Services** | Manual setup each time | Add to compose, rebuild |
| **Isolation** | Shared system Python | Containerized |
| **Portability** | "Works on my machine" | Consistent across envs |
| **Resource Limits** | No limits | Can set memory/CPU caps |
| **Monitoring** | Manual ps/top | `docker stats` |
| **Logs** | Scattered across terminals | `docker-compose logs` |
| **Restart on Crash** | Manual | `restart: unless-stopped` |

---

## Conclusion

**Recommendation**: ✅ **Containerize terrarium-irc and use Docker Compose**

**Benefits**:
1. **Single Orchestration Point**: Manage all services from one file
2. **Easy to Add Services**: Web UI, doc processor, other bots - just add to compose
3. **Graceful Degradation**: IRC logging continues even if LLM is down
4. **Production Ready**: Restart policies, health checks, resource limits
5. **Development Friendly**: Can still dev locally, deploy with Docker

**Next Steps**:
1. Create `Dockerfile` for terrarium-irc
2. Set up ecosystem directory structure
3. Create master `docker-compose.yml`
4. Test with IRC bot + agent
5. Migrate existing SQLite data
6. Document for future services

This architecture scales gracefully as you add more LLM-consuming services!
