#!/bin/bash
############################################
# PARE-BRISE PRO — FULL VERSION
# Voice + Telephony + WhatsApp + Scheduling
# Ubuntu + NVIDIA GPU (Docker required)
############################################
set -e
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
step(){ echo -e "\n${GREEN}[✓]${NC} $1"; }

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║  🔧 PARE-BRISE PRO — FULL INSTALL       ║"
echo "║  Voice + Telephony + WhatsApp + Cal.com  ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INSTALL_DIR"

# --- Check Docker ---
if ! command -v docker &>/dev/null; then
    echo "Docker required for full version. Installing..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "Docker installed. Log out, log back in, re-run."
    exit 1
fi

# --- Generate secrets ---
step "Generating secrets..."
PG_PASS=$(openssl rand -hex 16)
EVO_KEY=$(openssl rand -hex 24)
CALCOM_SECRET=$(openssl rand -hex 32)
CALCOM_ENC=$(openssl rand -hex 16)
LK_KEY=$(openssl rand -hex 16)
LK_SECRET=$(openssl rand -hex 32)

cat > .secrets <<EOF
POSTGRES_PASSWORD=$PG_PASS
EVOLUTION_API_KEY=$EVO_KEY
CALCOM_SECRET=$CALCOM_SECRET
LIVEKIT_KEY=$LK_KEY
LIVEKIT_SECRET=$LK_SECRET
EOF
chmod 600 .secrets

# --- Create docker-compose ---
step "Creating docker-compose.yml..."
mkdir -p asterisk

cat > docker-compose.yml <<EOF
services:
  n8n:
    image: n8nio/n8n:latest
    container_name: n8n
    restart: always
    ports: ["5678:5678"]
    environment:
      - N8N_HOST=0.0.0.0
      - N8N_PORT=5678
      - GENERIC_TIMEZONE=Europe/Paris
      - N8N_AI_ENABLED=true
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres
      - DB_POSTGRESDB_PORT=5432
      - DB_POSTGRESDB_DATABASE=n8n
      - DB_POSTGRESDB_USER=agent
      - DB_POSTGRESDB_PASSWORD=$PG_PASS
    volumes: ["n8n_data:/home/node/.n8n"]
    depends_on: [postgres]

  postgres:
    image: pgvector/pgvector:pg16
    container_name: postgres
    restart: always
    environment:
      - POSTGRES_USER=agent
      - POSTGRES_PASSWORD=$PG_PASS
      - POSTGRES_DB=n8n
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql
    ports: ["5432:5432"]

  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: always
    ports: ["11434:11434"]
    volumes: ["ollama_data:/root/.ollama"]
    deploy:
      resources:
        reservations:
          devices: [{driver: nvidia, count: 1, capabilities: [gpu]}]
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - OLLAMA_NUM_PARALLEL=2
      - OLLAMA_MAX_LOADED_MODELS=1
      - OLLAMA_KEEP_ALIVE=5m

  whisper:
    image: fedirz/faster-whisper-server:latest-cuda
    container_name: whisper
    restart: always
    ports: ["8100:8000"]
    environment:
      - WHISPER__MODEL=Systran/faster-whisper-large-v3
      - WHISPER__DEVICE=cpu
      - WHISPER__COMPUTE_TYPE=int8

  kokoro-tts:
    image: hwdsl2/tts-server:latest
    container_name: kokoro-tts
    restart: always
    ports: ["8880:8880"]
    environment: ["KOKORO_DEVICE=cuda"]
    deploy:
      resources:
        reservations:
          devices: [{driver: nvidia, count: 1, capabilities: [gpu]}]

  qdrant:
    image: qdrant/qdrant:latest
    container_name: qdrant
    restart: always
    ports: ["6333:6333"]
    volumes: ["qdrant_data:/qdrant/storage"]

  redis:
    image: redis:7-alpine
    container_name: redis
    restart: always
    ports: ["6379:6379"]
    volumes: ["redis_data:/data"]

  evolution-api:
    image: atendai/evolution-api:latest
    container_name: evolution-api
    restart: always
    ports: ["8084:8084"]
    environment:
      - SERVER_URL=http://evolution-api:8084
      - AUTHENTICATION_API_KEY=$EVO_KEY
      - DATABASE_PROVIDER=postgresql
      - DATABASE_CONNECTION_URI=postgresql://agent:${PG_PASS}@postgres:5432/evolution
      - CACHE_REDIS_ENABLED=true
      - CACHE_REDIS_URI=redis://redis:6379/1
    depends_on: [postgres, redis]

  calcom:
    image: calcom/cal.com:latest
    container_name: calcom
    restart: always
    ports: ["3100:3000"]
    environment:
      - DATABASE_URL=postgresql://agent:${PG_PASS}@postgres:5432/calcom
      - NEXTAUTH_SECRET=$CALCOM_SECRET
      - CALENDSO_ENCRYPTION_KEY=$CALCOM_ENC
      - NEXT_PUBLIC_WEBAPP_URL=http://localhost:3100
    depends_on: [postgres]

  asterisk:
    image: andrius/asterisk:latest
    container_name: asterisk
    restart: always
    network_mode: host
    volumes:
      - ./asterisk/sip.conf:/etc/asterisk/sip.conf
      - ./asterisk/extensions.conf:/etc/asterisk/extensions.conf

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: always
    ports: ["3000:8080"]
    environment: ["OLLAMA_BASE_URL=http://ollama:11434"]
    volumes: ["openwebui_data:/app/backend/data"]
    depends_on: [ollama]

volumes:
  n8n_data:
  postgres_data:
  ollama_data:
  qdrant_data:
  redis_data:
  openwebui_data:
EOF

cat > init-db.sql <<'EOF'
CREATE DATABASE evolution;
CREATE DATABASE calcom;
CREATE EXTENSION IF NOT EXISTS vector;
EOF

# --- Asterisk configs ---
cat > asterisk/sip.conf <<'EOF'
[general]
context=default
allowoverlap=no
udpbindaddr=0.0.0.0
tcpenable=yes
transport=udp
srvlookup=yes
allowguest=no
;[trunk]
;type=peer
;host=sip.ovh.net
;username=YOUR_USER
;secret=YOUR_PASS
;context=inbound
;disallow=all
;allow=ulaw
;allow=alaw
[softphone]
type=friend
context=default
host=dynamic
secret=test1234
disallow=all
allow=ulaw
allow=alaw
EOF

cat > asterisk/extensions.conf <<'EOF'
[general]
static=yes
[default]
exten => _X.,1,Answer()
same => n,Wait(1)
same => n,AGI(agi://localhost:8088/voice-agent)
same => n,Hangup()
[inbound]
exten => _X.,1,Goto(default,${EXTEN},1)
EOF

# --- Launch ---
step "Launching Docker stack..."
docker compose up -d

step "Pulling models..."
sleep 15
until curl -s http://localhost:11434/api/tags >/dev/null 2>&1; do sleep 2; done
docker exec ollama ollama pull qwen3:8b
echo "Pulling Llama 70B Q4 (30-60 min)..."
docker exec ollama ollama pull llama3:70b-instruct-q4_K_M

# --- Status ---
echo ""
IP=$(hostname -I | awk '{print $1}')
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════╗"
echo "║  ✅ FULL VERSION READY                       ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  n8n         → http://$IP:5678           ║"
echo "║  Open WebUI  → http://$IP:3000           ║"
echo "║  Cal.com     → http://$IP:3100           ║"
echo "║  WhatsApp    → http://$IP:8084           ║"
echo "║  Ollama      → http://$IP:11434          ║"
echo "║  Qdrant      → http://$IP:6333           ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo "Secrets: $INSTALL_DIR/.secrets"
