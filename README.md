# 🔧 V-Glass Auto — AI Voice Agent

Full AI agent for a windshield replacement business. Handles voice conversations, appointment scheduling, lead qualification, and client communication — all self-hosted, zero subscription.

## 🎤 Test Version (No Telephony)

Voice chat via browser — no SIP trunk or phone number needed.

```bash
git clone https://github.com/mohcin95/parebrise-ai.git
cd parebrise-ai
chmod +x scripts/install-test.sh
./scripts/install-test.sh
```

Open **port 8880** in your browser → talk to the agent.

## 📞 Full Version (With Telephony)

Adds Asterisk SIP, Evolution API (WhatsApp), Cal.com scheduling.

```bash
chmod +x scripts/install-full.sh
./scripts/install-full.sh
```

## Architecture

```
🎤 Browser Mic / Téléphone
       ↓
🗣️ Faster-Whisper (STT) → texte
       ↓
🧠 Qwen3 8B / Llama 70B (Ollama) + mémoire Qdrant
       ↓
🔊 Kokoro TTS → audio
       ↓
🎧 Réponse vocale dans le browser / téléphone

⚙️ n8n orchestre: planning, confirmations, prospection
```

## Services

| Service | Port | Usage |
|---------|------|-------|
| Voice Chat UI | 8880 | Web interface micro + chat |
| n8n | 5678 | Workflow orchestration |
| Ollama | 11434 | LLM inference |
| Qdrant | 6333 | Vector memory |
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Cache |

### Full version adds:
| Service | Port | Usage |
|---------|------|-------|
| Evolution API | 8084 | WhatsApp |
| Cal.com | 3100 | Scheduling |
| Asterisk | 5060 | SIP telephony |

## Hardware

- **Minimum**: 16GB VRAM (Qwen3 8B + Whisper + Kokoro)
- **Recommended**: 48GB VRAM (Llama 70B Q4 + everything)
- **Tested on**: NVIDIA A40 48GB / RunPod

## VRAM Budget (A40 48GB)

| Mode | Model | VRAM |
|------|-------|------|
| Fast | Qwen3 8B + Whisper + Kokoro | ~13GB |
| Heavy | Llama 70B Q4 + Whisper + Kokoro | ~47GB |

Dynamic loading: only 1 LLM at a time, auto-swap in ~15s.

## Commands

```bash
# Service management
supervisorctl status
supervisorctl restart voice
supervisorctl tail -f voice

# Test TTS
curl http://localhost:8880/speak -H 'Content-Type: application/json' \
  -d '{"input":"Bonjour, V-Glass Auto"}' -o test.wav

# Test LLM
curl http://localhost:11434/api/chat \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"Salut"}]}'

# Test STT
curl http://localhost:8880/listen -F file=@test.wav

# Pull heavy model when needed
ollama pull llama3:70b-instruct-q4_K_M
```

## Configuration

Edit `data/config.json` for your business info, technician details, and pricing.
Edit `prompts/*.txt` for AI agent behavior.
Edit `data/prospects.csv` for outbound call lists.

## License

MIT
