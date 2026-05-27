# V-Glass Auto — Voice Agent v3

AI voice agent for a windshield replacement business. Streaming architecture with ~800ms-1.2s latency to first audio response.

## Architecture

```
Browser (WebSocket, continuous mic)
    |  PCM 16kHz int16
    v
Silero VAD (end of speech detection, ~100ms)
    |
    v
Whisper large-v3-turbo (STT, ~200ms)
    |  text
    v
vLLM + Qwen3 8B (streaming LLM, ~150ms TTFT)
    |  sentence chunks
    v
vLLM + Orpheus 3B FR (streaming TTS)
    |  SNAC tokens
    v
SNAC decoder (audio, ~10ms)
    |  PCM 24kHz int16
    v
Browser (instant playback)
```

## Quick Start (RunPod A40 48GB)

```bash
git clone https://github.com/mohcin95/parebrise-ai.git
cd parebrise-ai
python3 setup_v3.py
```

Open **port 8880** in RunPod settings, then open the URL in your browser.

## VRAM Usage

| Service | VRAM |
|---------|------|
| vLLM Qwen3 8B (30%) | ~14GB |
| vLLM Orpheus 3B FR (20%) | ~10GB |
| Whisper large-v3-turbo | ~2GB |
| SNAC decoder | ~0.5GB |
| Silero VAD | ~0.1GB |
| **Total** | **~27GB / 48GB** |

## Files

```
parebrise-ai/
├── setup_v3.py          # One-click installer
├── start.sh             # Launch all services
├── stop.sh              # Stop all services
├── voice_agent.py       # WebSocket voice pipeline
├── orpheus_tts.py       # Orpheus TTS + SNAC streaming decoder
├── static/index.html    # Browser client
├── prompts/inbound.txt  # Agent personality + script
└── logs/                # Service logs
```

## Ports

| Port | Service |
|------|---------|
| 8880 | Voice Chat UI |
| 8000 | vLLM Qwen3 8B API |
| 8001 | vLLM Orpheus TTS API |

## Commands

```bash
# Start
bash start.sh

# Stop
bash stop.sh

# Logs
tail -f logs/voice-agent.log
tail -f logs/vllm-qwen.log
tail -f logs/vllm-orpheus.log

# Check GPU
nvidia-smi

# Test LLM
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen3-8B","messages":[{"role":"user","content":"Bonjour"}],"max_tokens":50}'

# Test TTS
curl http://localhost:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"canopylabs/3b-fr-ft-research_release","prompt":"tara: Bonjour","max_tokens":100}'
```

## Troubleshooting

### vLLM won't start
```bash
cat logs/vllm-qwen.log | tail -30
cat logs/vllm-orpheus.log | tail -30
```

### Voice agent crashes
```bash
cat logs/voice-agent.log | tail -30
```

### Out of VRAM
Reduce gpu-memory-utilization in start.sh (currently 0.30 + 0.20 = 50%)

### No audio in browser
- Check that URL is HTTPS (RunPod proxy handles this)
- Allow microphone access when browser asks
- Try Chrome instead of Safari
