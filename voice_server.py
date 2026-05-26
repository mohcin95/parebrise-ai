"""
V-Glass Auto — Streaming Voice Server
WebSocket: STT stream -> LLM stream -> TTS stream
Target latency: 500-800ms first audio chunk
"""
import asyncio, json, io, os, base64, tempfile
from fastapi import FastAPI, WebSocket, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
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
    print("Loading Whisper small...")
    from faster_whisper import WhisperModel
    whisper_model = WhisperModel("small", device="cuda", compute_type="float16")
    print("Whisper ready")
    print("Loading Kokoro TTS...")
    from kokoro import KPipeline
    tts_pipeline = KPipeline(lang_code="f")
    print("Kokoro ready")
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "inbound.txt")
    if os.path.exists(prompt_path):
        with open(prompt_path, encoding="utf-8", errors="ignore") as f:
            SYSTEM_PROMPT = f.read()
    else:
        SYSTEM_PROMPT = "Tu es l assistant de V-Glass Auto. Reponds en francais, 1-2 phrases max."
    print("READY on port 8880")

async def stt_fast(audio_bytes):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        segments, _ = whisper_model.transcribe(tmp_path, language="fr",
            beam_size=1, best_of=1, vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300))
        return " ".join([s.text for s in segments]).strip()
    finally:
        os.unlink(tmp_path)

async def llm_stream(message, history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-6:])
    messages.append({"role": "user", "content": message})
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json={
            "model": "qwen3:8b", "messages": messages, "stream": True,
            "options": {"num_predict": 80, "temperature": 0.7}
        }) as resp:
            buffer = ""
            async for line in resp.aiter_lines():
                if not line: continue
                try:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        buffer += token
                        for sep in [".", "!", "?", ","]:
                            if sep in buffer:
                                parts = buffer.split(sep, 1)
                                sentence = parts[0] + sep
                                buffer = parts[1] if len(parts) > 1 else ""
                                if sentence.strip():
                                    yield sentence.strip()
                                break
                except: continue
            if buffer.strip():
                yield buffer.strip()

def tts_chunk(text):
    if not text or len(text) < 2: return None
    try:
        chunks = []
        for _, _, audio in tts_pipeline(text, voice="ff_siwis", speed=1.1):
            chunks.append(audio)
        if not chunks: return None
        buf = io.BytesIO()
        sf.write(buf, np.concatenate(chunks), 24000, format="WAV")
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"TTS error: {e}")
        return None

@app.websocket("/ws")
async def websocket_voice(ws: WebSocket):
    await ws.accept()
    history = []
    try:
        while True:
            data = await ws.receive_bytes()
            await ws.send_json({"type": "status", "text": "Ecoute..."})
            user_text = await stt_fast(data)
            if not user_text:
                await ws.send_json({"type": "status", "text": "Pas compris"})
                continue
            await ws.send_json({"type": "user_text", "text": user_text})
            await ws.send_json({"type": "status", "text": "Reflexion..."})
            full_response = ""
            first_chunk = True
            async for sentence in llm_stream(user_text, history):
                full_response += sentence + " "
                await ws.send_json({"type": "ai_text_chunk", "text": sentence})
                audio_data = await asyncio.to_thread(tts_chunk, sentence)
                if audio_data:
                    audio_b64 = base64.b64encode(audio_data).decode()
                    await ws.send_json({"type": "audio_chunk", "audio": audio_b64, "first": first_chunk})
                    first_chunk = False
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": full_response.strip()})
            await ws.send_json({"type": "done"})
    except Exception as e:
        print(f"WS error: {e}")

class ChatRequest(BaseModel):
    message: str
    history: list = []

@app.post("/chat")
async def chat(req: ChatRequest):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(req.history[-6:])
    messages.append({"role": "user", "content": req.message})
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/chat", json={
            "model": "qwen3:8b", "messages": messages, "stream": False,
            "options": {"num_predict": 80}
        })
        data = resp.json()
        return {"response": data.get("message", {}).get("content", "")}

class SpeakRequest(BaseModel):
    input: str

@app.post("/speak")
async def speak(req: SpeakRequest):
    audio = await asyncio.to_thread(tts_chunk, req.input)
    if audio: return StreamingResponse(io.BytesIO(audio), media_type="audio/wav")
    return {"error": "TTS failed"}

@app.post("/listen")
async def listen(file: UploadFile = File(...)):
    content = await file.read()
    text = await stt_fast(content)
    return {"text": text}

@app.get("/")
async def web_ui():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>V-Glass Auto</h1>")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8880)
