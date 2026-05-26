"""
V-Glass Auto — Voice AI Server
Unified STT (Whisper) + LLM (Ollama) + TTS (Kokoro)

Endpoints:
  POST /listen      → audio in, text out (STT)
  POST /speak       → text in, audio out (TTS)
  POST /chat        → text in, text out (LLM)
  POST /voice-chat  → audio in, audio out (full pipeline)
  GET  /            → Web voice chat UI
"""
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
import tempfile, os, io, json, base64
import numpy as np
import soundfile as sf
import httpx

app = FastAPI(title="V-Glass Auto Voice AI")

whisper_model = None
tts_pipeline = None
OLLAMA_URL = "http://localhost:11434"
SYSTEM_PROMPT = ""

@app.on_event("startup")
def load_models():
    global whisper_model, tts_pipeline, SYSTEM_PROMPT

    print("🔄 Loading Whisper large-v3...")
    from faster_whisper import WhisperModel
    whisper_model = WhisperModel("medium", device="cuda", compute_type="float16")
    print("✅ Whisper ready")

    print("🔄 Loading Kokoro TTS...")
    from kokoro import KPipeline
    tts_pipeline = KPipeline(lang_code="f")
    print("✅ Kokoro TTS ready (French)")

    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "inbound.txt")
    if os.path.exists(prompt_path):
        with open(prompt_path) as f:
            SYSTEM_PROMPT = f.read()
    else:
        SYSTEM_PROMPT = "Tu es l'assistant de V-Glass Auto, service de remplacement de pare-brise. Réponds en français, sois concis. On ne fait pas de réparation, uniquement du remplacement."
    print("✅ System prompt loaded")


# ---- STT ----
@app.post("/listen")
async def listen(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        segments, info = whisper_model.transcribe(tmp_path, language="fr")
        text = " ".join([s.text for s in segments])
        return {"text": text.strip(), "language": info.language}
    finally:
        os.unlink(tmp_path)


# ---- TTS ----
class SpeakRequest(BaseModel):
    input: str
    voice: str = "ff_siwis"
    speed: float = 1.0

@app.post("/speak")
async def speak(req: SpeakRequest):
    audio_chunks = []
    for _, _, audio in tts_pipeline(req.input, voice=req.voice, speed=req.speed):
        audio_chunks.append(audio)
    if not audio_chunks:
        return {"error": "No audio generated"}
    full_audio = np.concatenate(audio_chunks)
    buf = io.BytesIO()
    sf.write(buf, full_audio, 24000, format="WAV")
    buf.seek(0)
    return StreamingResponse(buf, media_type="audio/wav")


# ---- LLM Chat ----
class ChatRequest(BaseModel):
    message: str
    history: list = []

@app.post("/chat")
async def chat(req: ChatRequest):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(req.history)
    messages.append({"role": "user", "content": req.message})
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json={
            "model": "qwen3:8b",
            "messages": messages,
            "stream": False
        })
        data = resp.json()
        return {"response": data.get("message", {}).get("content", "")}


# ---- FULL VOICE PIPELINE ----
@app.post("/voice-chat")
async def voice_chat(file: UploadFile = File(...), history: str = Form(default="[]")):
    # 1. STT
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        segments, _ = whisper_model.transcribe(tmp_path, language="fr")
        user_text = " ".join([s.text for s in segments]).strip()
    finally:
        os.unlink(tmp_path)

    if not user_text:
        return {"error": "Could not understand audio", "user_text": "", "ai_text": "", "audio_base64": ""}

    # 2. LLM
    hist = json.loads(history) if history else []
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(hist)
    messages.append({"role": "user", "content": user_text})

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json={
            "model": "qwen3:8b",
            "messages": messages,
            "stream": False
        })
        data = resp.json()
        ai_text = data.get("message", {}).get("content", "Désolé, une erreur est survenue.")

    # 3. TTS
    audio_chunks = []
    for _, _, audio in tts_pipeline(ai_text, voice="ff_siwis", speed=1.0):
        audio_chunks.append(audio)
    full_audio = np.concatenate(audio_chunks) if audio_chunks else np.zeros(24000)
    buf = io.BytesIO()
    sf.write(buf, full_audio, 24000, format="WAV")
    buf.seek(0)
    audio_b64 = base64.b64encode(buf.read()).decode()

    return {
        "user_text": user_text,
        "ai_text": ai_text,
        "audio_base64": audio_b64
    }


# ---- WEB UI ----
@app.get("/")
async def web_ui():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>V-Glass Auto AI</h1><p>static/index.html not found</p>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8880)
