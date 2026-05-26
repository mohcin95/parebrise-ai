#!/bin/bash
############################################
# PARE-BRISE PRO — TEST VERSION
# Voice chat only, no telephony
# RunPod / Ubuntu + NVIDIA GPU
############################################
set -e
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
step(){ echo -e "\n${GREEN}[✓]${NC} $1"; }
err(){ echo -e "${RED}[✗]${NC} $1"; }

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║  🔧 PARE-BRISE PRO — TEST INSTALL       ║"
echo "║  Voice chat, no telephony               ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INSTALL_DIR"
mkdir -p logs

# --- 1. Check GPU ---
step "1/8 Checking GPU..."
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    err "No NVIDIA GPU found. Whisper/Kokoro will be slow on CPU."
fi

# --- 2. System deps ---
step "2/8 Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq curl wget nodejs npm redis-server postgresql postgresql-contrib ffmpeg supervisor jq zstd > /dev/null 2>&1
echo "  done"

# --- 3. Ollama ---
step "3/8 Installing Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
fi
nohup ollama serve > "$INSTALL_DIR/logs/ollama.log" 2>&1 &
sleep 3
echo "  done"

# --- 4. n8n ---
step "4/8 Installing n8n..."
if ! command -v n8n &>/dev/null; then
    npm install -g n8n > /dev/null 2>&1
fi
echo "  done"

# --- 5. Python deps ---
step "5/8 Installing Python packages..."
pip install faster-whisper fastapi uvicorn python-multipart httpx \
    kokoro soundfile scipy numpy aiofiles \
    --break-system-packages -q 2>/dev/null || \
pip install faster-whisper fastapi uvicorn python-multipart httpx \
    kokoro soundfile scipy numpy aiofiles -q
echo "  done"

# --- 6. Qdrant ---
step "6/8 Installing Qdrant..."
if ! command -v qdrant &>/dev/null; then
    cd /tmp
    wget -q https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-musl.tar.gz
    tar -xzf qdrant-x86_64-unknown-linux-musl.tar.gz 2>/dev/null
    mv qdrant /usr/local/bin/ 2>/dev/null
    cd "$INSTALL_DIR"
fi
echo "  done"

# --- 7. PostgreSQL + Redis ---
step "7/8 Starting PostgreSQL + Redis..."
service postgresql start 2>/dev/null || true
service redis-server start 2>/dev/null || true
su - postgres -c "psql -c \"CREATE USER agent WITH PASSWORD 'agent_pass';\"" 2>/dev/null || true
su - postgres -c "psql -c \"CREATE DATABASE n8n OWNER agent;\"" 2>/dev/null || true
echo "  done"

# --- 8. Supervisor config ---
step "8/8 Configuring services..."
cat > /etc/supervisor/conf.d/parebrise.conf <<SUPEOF
[program:ollama]
command=ollama serve
autostart=true
autorestart=true
stdout_logfile=$INSTALL_DIR/logs/ollama.log
stderr_logfile=$INSTALL_DIR/logs/ollama.err

[program:n8n]
command=n8n start
environment=N8N_HOST="0.0.0.0",N8N_PORT="5678",N8N_PROTOCOL="http",GENERIC_TIMEZONE="Europe/Paris",N8N_AI_ENABLED="true",DB_TYPE="postgresdb",DB_POSTGRESDB_HOST="localhost",DB_POSTGRESDB_PORT="5432",DB_POSTGRESDB_DATABASE="n8n",DB_POSTGRESDB_USER="agent",DB_POSTGRESDB_PASSWORD="agent_pass"
autostart=true
autorestart=true
stdout_logfile=$INSTALL_DIR/logs/n8n.log
stderr_logfile=$INSTALL_DIR/logs/n8n.err

[program:voice]
command=python $INSTALL_DIR/voice_server.py
directory=$INSTALL_DIR
autostart=true
autorestart=true
stdout_logfile=$INSTALL_DIR/logs/voice.log
stderr_logfile=$INSTALL_DIR/logs/voice.err

[program:qdrant]
command=/usr/local/bin/qdrant --storage-path $INSTALL_DIR/qdrant_data
autostart=true
autorestart=true
stdout_logfile=$INSTALL_DIR/logs/qdrant.log
stderr_logfile=$INSTALL_DIR/logs/qdrant.err
SUPEOF

# Launch
supervisord -c /etc/supervisor/supervisord.conf 2>/dev/null || true
supervisorctl reread
supervisorctl update
supervisorctl start all

# --- Pull model ---
echo ""
step "Pulling Qwen3 8B model..."
sleep 5
until curl -s http://localhost:11434/api/tags >/dev/null 2>&1; do sleep 2; done
ollama pull qwen3:8b

# --- Status ---
echo ""
step "Checking services..."
sleep 8
for svc in ollama n8n voice qdrant; do
    if supervisorctl status $svc 2>/dev/null | grep -q RUNNING; then
        echo -e "  ${GREEN}✓${NC} $svc"
    else
        echo -e "  ${RED}✗${NC} $svc — run: supervisorctl tail $svc stderr"
    fi
done

echo ""
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════╗"
echo "║  ✅ READY — TEST VERSION                     ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║  🎤 Voice Chat → port 8880                   ║"
echo "║  ⚙️  n8n        → port 5678                   ║"
echo "║  🧠 Ollama     → port 11434                  ║"
echo "║  📦 Qdrant     → port 6333                   ║"
echo "║                                              ║"
echo "║  RunPod: expose port 8880 in Settings        ║"
echo "║  Then open the public URL in your browser    ║"
echo "║  🎤 Speak or type to talk to the agent       ║"
echo "║                                              ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"
