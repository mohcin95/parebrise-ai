"""
V-Glass Auto — Voice Agent v3
Streaming voice pipeline: WebSocket + Silero VAD + Whisper + vLLM + Orpheus TTS

Flow:
  Browser mic → WebSocket PCM → Silero VAD (end of speech)
  → Whisper turbo (STT) → vLLM Qwen3 (LLM streaming)
  → Orpheus FR (TTS streaming via SNAC) → WebSocket → browser speaker

Target latency: ~800ms-1.2s to first audio on A40 48GB
"""

import asyncio
import json
import os
import io
import base64
import tempfile
import time
import uuid
import re
import struct
import wave
import numpy as np

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import httpx

# ============================================================
# Configuration
# ============================================================

WHISPER_MODEL = "deepdml/faster-whisper-large-v3-turbo-ct2"
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE = "float16"

LLM_URL = "http://localhost:8000/v1/chat/completions"
LLM_MODEL = "Qwen/Qwen3-8B"

TTS_URL = "http://localhost:8001/v1/completions"
TTS_MODEL = "canopylabs/3b-fr-ft-research_release"
TTS_VOICE = "tara"  # Try "speaker_0" if French model uses different voices

SAMPLE_RATE_IN = 16000   # Whisper expects 16kHz
SAMPLE_RATE_OUT = 24000  # SNAC outputs 24kHz

DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# App
# ============================================================

app = FastAPI(title="V-Glass Auto Voice Agent v3")

# Global model references
whisper_model = None
vad_model = None
orpheus = None
SYSTEM_PROMPT = ""


@app.on_event("startup")
def startup():
    global whisper_model, vad_model, orpheus, SYSTEM_PROMPT

    # --- Load system prompt ---
    prompt_path = os.path.join(DIR, "prompts", "inbound.txt")
    if os.path.exists(prompt_path):
        with open(prompt_path, encoding="utf-8", errors="ignore") as f:
            SYSTEM_PROMPT = f.read()
    else:
        SYSTEM_PROMPT = (
            "Tu es l assistant vocal de V-Glass Auto. "
            "Reponds en francais, 1-2 phrases max. Pas d emojis."
        )
    print(f"  System prompt: {len(SYSTEM_PROMPT)} chars")

    # --- Load Whisper ---
    print("  Loading Whisper large-v3-turbo...")
    from faster_whisper import WhisperModel
    whisper_model = WhisperModel(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE,
    )
    print("  Whisper ready")

    # --- Load Silero VAD ---
    print("  Loading Silero VAD...")
    import torch
    vad_model_data, vad_utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        trust_repo=True,
    )
    vad_model = vad_model_data
    print("  Silero VAD ready")

    # --- Load Orpheus TTS ---
    print("  Loading Orpheus TTS + SNAC decoder...")
    from orpheus_tts import OrpheusTTS
    orpheus = OrpheusTTS(
        vllm_url=TTS_URL,
        model_name=TTS_MODEL,
        frames_per_chunk=7,
    )
    orpheus.load_snac()
    print("  Orpheus TTS ready")

    print("\n  === V-GLASS AUTO VOICE AGENT v3 READY ===")
    print("  === Port 8880 ===\n")


# ============================================================
# STT: Whisper transcription
# ============================================================

async def transcribe(audio_bytes: bytes) -> str:
    """Transcribe audio bytes with Whisper large-v3-turbo."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        # Write WAV header + PCM data
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE_IN)
            wf.writeframes(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, info = whisper_model.transcribe(
            tmp_path,
            language="fr",
            beam_size=1,
            best_of=1,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=300,
                speech_pad_ms=200,
            ),
        )
        text = " ".join(s.text for s in segments).strip()
        return text
    finally:
        os.unlink(tmp_path)


# ============================================================
# LLM: Streaming chat via vLLM
# ============================================================

async def llm_stream(message: str, history: list) -> asyncio.Queue:
    """
    Stream LLM response, splitting at sentence boundaries.
    Returns an asyncio.Queue that yields (sentence, is_last) tuples.
    """
    queue = asyncio.Queue()

    async def _generate():
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history[-6:])
        messages.append({"role": "user", "content": message})

        buffer = ""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST",
                    LLM_URL,
                    json={
                        "model": LLM_MODEL,
                        "messages": messages,
                        "stream": True,
                        "max_tokens": 100,
                        "temperature": 0.7,
                        "top_p": 0.9,
                    },
                ) as resp:
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = (
                                data.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                        except (ValueError, IndexError, KeyError):
                            continue

                        if not delta:
                            continue

                        buffer_local = buffer + delta
                        # Split at sentence boundaries
                        for sep in ".!?,;:":
                            if sep in buffer_local:
                                parts = buffer_local.split(sep, 1)
                                sentence = parts[0] + sep
                                buffer_local = parts[1] if len(parts) > 1 else ""
                                sentence = sentence.strip()
                                if sentence and len(sentence) > 2:
                                    await queue.put((sentence, False))
                                break
                        buffer = buffer_local

            # Flush remaining buffer
            if buffer.strip() and len(buffer.strip()) > 2:
                await queue.put((buffer.strip(), False))
        except Exception as e:
            print(f"  LLM error: {e}")
        finally:
            await queue.put((None, True))  # Signal done

    asyncio.create_task(_generate())
    return queue


# ============================================================
# VAD: Silero Voice Activity Detection
# ============================================================

class VADProcessor:
    """Processes incoming audio and detects speech boundaries."""

    def __init__(self, sample_rate=16000, min_silence_ms=500, min_speech_ms=250):
        self.sample_rate = sample_rate
        self.min_silence_samples = int(min_silence_ms * sample_rate / 1000)
        self.min_speech_samples = int(min_speech_ms * sample_rate / 1000)
        self.audio_buffer = bytearray()
        self.is_speaking = False
        self.silence_counter = 0
        self.speech_counter = 0
        self.chunk_size = 512  # Silero VAD needs 512 samples at 16kHz

    def reset(self):
        """Reset state for new utterance."""
        self.audio_buffer = bytearray()
        self.is_speaking = False
        self.silence_counter = 0
        self.speech_counter = 0
        if vad_model is not None:
            vad_model.reset_states()

    def process_chunk(self, pcm_bytes: bytes) -> tuple[bool, bytes]:
        """
        Feed PCM audio (int16, 16kHz, mono).
        Returns (utterance_complete, audio_bytes).
        """
        import torch

        self.audio_buffer.extend(pcm_bytes)

        # Process in 512-sample chunks
        while len(self.audio_buffer) >= self.chunk_size * 2:  # *2 for int16
            chunk_bytes = bytes(self.audio_buffer[: self.chunk_size * 2])
            del self.audio_buffer[: self.chunk_size * 2]

            # Convert to float tensor
            samples = np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            tensor = torch.from_numpy(samples)

            # Run VAD
            try:
                speech_prob = vad_model(tensor, self.sample_rate).item()
            except Exception:
                speech_prob = 0.0

            if speech_prob > 0.5:
                self.speech_counter += self.chunk_size
                self.silence_counter = 0
                if self.speech_counter >= self.min_speech_samples:
                    self.is_speaking = True
            else:
                if self.is_speaking:
                    self.silence_counter += self.chunk_size
                    if self.silence_counter >= self.min_silence_samples:
                        # End of speech detected
                        return True, b""

        return False, b""


# ============================================================
# WebSocket: Bidirectional audio streaming
# ============================================================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    history = []
    vad = VADProcessor()
    audio_accumulator = bytearray()
    is_agent_speaking = False

    await ws.send_json({"type": "ready"})

    try:
        while True:
            # Receive audio frame from browser
            data = await ws.receive()

            if "bytes" in data:
                pcm_data = data["bytes"]
                audio_accumulator.extend(pcm_data)

                # If agent is speaking and user starts talking, handle interruption
                if is_agent_speaking:
                    # Simple energy-based check for barge-in
                    samples = np.frombuffer(pcm_data, dtype=np.int16)
                    energy = np.sqrt(np.mean(samples.astype(float) ** 2))
                    if energy > 500:  # User is talking over agent
                        is_agent_speaking = False
                        await ws.send_json({"type": "interrupted"})
                        audio_accumulator = bytearray()
                        vad.reset()
                        continue

                # Run VAD
                utterance_done, _ = vad.process_chunk(pcm_data)

                if utterance_done and len(audio_accumulator) > SAMPLE_RATE_IN:
                    t0 = time.time()

                    # --- 1. STT ---
                    await ws.send_json({"type": "status", "text": "Ecoute..."})
                    user_text = await transcribe(bytes(audio_accumulator))
                    t_stt = time.time()

                    audio_accumulator = bytearray()
                    vad.reset()

                    if not user_text or len(user_text) < 2:
                        await ws.send_json({"type": "status", "text": "Pret"})
                        continue

                    await ws.send_json({"type": "user_text", "text": user_text})

                    # --- 2. LLM streaming ---
                    await ws.send_json({"type": "status", "text": "Reflexion..."})
                    sentence_queue = await llm_stream(user_text, history)
                    t_llm_start = time.time()

                    full_response = ""
                    is_agent_speaking = True
                    first_audio = True

                    while True:
                        sentence, is_last = await sentence_queue.get()
                        if is_last:
                            break
                        if not is_agent_speaking:
                            # User interrupted
                            break

                        full_response += sentence + " "
                        await ws.send_json({
                            "type": "ai_text_chunk",
                            "text": sentence,
                        })

                        # --- 3. TTS streaming ---
                        try:
                            async for audio_chunk in orpheus.synthesize_streaming(
                                sentence, voice=TTS_VOICE
                            ):
                                if not is_agent_speaking:
                                    break

                                audio_b64 = base64.b64encode(audio_chunk).decode()
                                await ws.send_json({
                                    "type": "audio_chunk",
                                    "audio": audio_b64,
                                    "sample_rate": SAMPLE_RATE_OUT,
                                    "first": first_audio,
                                })

                                if first_audio:
                                    t_first_audio = time.time()
                                    latency = t_first_audio - t0
                                    print(f"  LATENCY first audio: {latency:.2f}s "
                                          f"(STT: {t_stt-t0:.2f}s)")
                                    first_audio = False
                        except Exception as e:
                            print(f"  TTS error for sentence '{sentence[:40]}': {e}")

                    is_agent_speaking = False

                    # Update history
                    history.append({"role": "user", "content": user_text})
                    history.append({"role": "assistant", "content": full_response.strip()})

                    # Keep history manageable
                    if len(history) > 10:
                        history = history[-10:]

                    await ws.send_json({
                        "type": "done",
                        "latency_stt": round(t_stt - t0, 2),
                    })

            elif "text" in data:
                # Handle text messages (ping/config)
                try:
                    msg = json.loads(data["text"])
                    if msg.get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                except (json.JSONDecodeError, TypeError):
                    pass

    except WebSocketDisconnect:
        print("  Client disconnected")
    except Exception as e:
        print(f"  WebSocket error: {e}")


# ============================================================
# HTTP fallback: text chat (no voice)
# ============================================================

from pydantic import BaseModel

class ChatReq(BaseModel):
    message: str
    history: list = []

@app.post("/chat")
async def chat_text(req: ChatReq):
    """Text-only chat endpoint (no audio)."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(req.history[-6:])
    messages.append({"role": "user", "content": req.message})

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            LLM_URL,
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "stream": False,
                "max_tokens": 100,
            },
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return {"response": content}


# ============================================================
# Web UI
# ============================================================

@app.get("/")
async def index():
    html_path = os.path.join(DIR, "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>V-Glass Auto v3</h1><p>static/index.html not found</p>")


# ============================================================
# Health check
# ============================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "whisper": whisper_model is not None,
        "vad": vad_model is not None,
        "orpheus": orpheus is not None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8880, log_level="info")
