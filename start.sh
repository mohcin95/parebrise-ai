#!/bin/bash
#############################################
# V-Glass Auto — Voice Agent v3 Launcher
# Starts: vLLM Qwen3 + vLLM Orpheus + Voice Agent
# GPU: A40 48GB
#############################################

DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS="$DIR/logs"
mkdir -p "$LOGS"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  =================================="
echo "  V-GLASS AUTO — VOICE AGENT v3"
echo "  =================================="
echo -e "${NC}"

# Kill any existing instances
echo "Stopping existing services..."
pkill -f "vllm serve" 2>/dev/null
pkill -f "voice_agent" 2>/dev/null
sleep 2

# ---- 1. Start vLLM for Qwen3 8B (Chat LLM) ----
echo -e "${GREEN}[1/3]${NC} Starting vLLM — Qwen3 8B on port 8000..."
nohup python3 -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen3-8B \
    --port 8000 \
    --host 0.0.0.0 \
    --dtype float16 \
    --gpu-memory-utilization 0.30 \
    --max-model-len 4096 \
    --enable-prefix-caching \
    --disable-log-requests \
    > "$LOGS/vllm-qwen.log" 2>&1 &
QWEN_PID=$!
echo "  PID: $QWEN_PID"

# ---- 2. Start vLLM for Orpheus 3B FR (TTS) ----
echo -e "${GREEN}[2/3]${NC} Starting vLLM — Orpheus 3B FR on port 8001..."
nohup python3 -m vllm.entrypoints.openai.api_server \
    --model canopylabs/3b-fr-ft-research_release \
    --port 8001 \
    --host 0.0.0.0 \
    --dtype bfloat16 \
    --gpu-memory-utilization 0.20 \
    --max-model-len 2048 \
    --disable-log-requests \
    > "$LOGS/vllm-orpheus.log" 2>&1 &
ORPHEUS_PID=$!
echo "  PID: $ORPHEUS_PID"

# ---- Wait for vLLM servers to be ready ----
echo ""
echo "Waiting for vLLM servers to load models..."
echo "(This takes 2-5 minutes on first run as models download)"
echo ""

# Wait for Qwen3
echo -n "  Qwen3 8B: "
for i in $(seq 1 120); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}ready${NC}"
        break
    fi
    if [ $i -eq 120 ]; then
        echo "TIMEOUT - check $LOGS/vllm-qwen.log"
        exit 1
    fi
    echo -n "."
    sleep 3
done

# Wait for Orpheus
echo -n "  Orpheus FR: "
for i in $(seq 1 120); do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo -e "${GREEN}ready${NC}"
        break
    fi
    if [ $i -eq 120 ]; then
        echo "TIMEOUT - check $LOGS/vllm-orpheus.log"
        exit 1
    fi
    echo -n "."
    sleep 3
done

# ---- 3. Start Voice Agent ----
echo ""
echo -e "${GREEN}[3/3]${NC} Starting Voice Agent on port 8880..."
nohup python3 "$DIR/voice_agent.py" \
    > "$LOGS/voice-agent.log" 2>&1 &
VOICE_PID=$!
echo "  PID: $VOICE_PID"

# Wait for voice agent
echo -n "  Voice Agent: "
for i in $(seq 1 60); do
    if curl -s http://localhost:8880/health > /dev/null 2>&1; then
        echo -e "${GREEN}ready${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "TIMEOUT - check $LOGS/voice-agent.log"
    fi
    echo -n "."
    sleep 2
done

# ---- Save PIDs ----
cat > "$DIR/.pids" << EOF
QWEN_PID=$QWEN_PID
ORPHEUS_PID=$ORPHEUS_PID
VOICE_PID=$VOICE_PID
EOF

# ---- Done ----
echo ""
echo -e "${CYAN}"
echo "  =================================="
echo "  V-GLASS AUTO v3 — READY!"
echo "  =================================="
echo ""
echo "  Voice Chat  ->  port 8880"
echo "  vLLM Qwen3  ->  port 8000"
echo "  vLLM Orpheus -> port 8001"
echo ""
echo "  Open port 8880 in your browser"
echo "  Turn on mic and start talking!"
echo ""
echo "  Logs:"
echo "    tail -f $LOGS/voice-agent.log"
echo "    tail -f $LOGS/vllm-qwen.log"
echo "    tail -f $LOGS/vllm-orpheus.log"
echo ""
echo "  Stop:"
echo "    bash $DIR/stop.sh"
echo "  =================================="
echo -e "${NC}"
