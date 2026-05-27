"""
Orpheus TTS Streaming Helper
Connects to a vLLM server serving the Orpheus French model.
Parses SNAC audio tokens from the streaming response and
decodes them to PCM audio in real-time.

Architecture:
  text → vLLM Orpheus (streaming) → <custom_token_XXXX> → SNAC decoder → PCM 24kHz

Token structure (per frame = 7 tokens):
  Position 0: Layer 1 (coarsest)
  Position 1: Layer 2
  Position 2: Layer 3 (finest)
  Position 3: Layer 3
  Position 4: Layer 2
  Position 5: Layer 3
  Position 6: Layer 3

SNAC decoder reconstructs audio at 24kHz from the 3-layer codes.
"""

import re
import struct
import asyncio
import numpy as np
import torch
import httpx
from typing import AsyncGenerator, Optional

# Orpheus special token IDs (text repr numbers, not vocab IDs)
TOKEN_OFFSET = 10          # Audio codes start at custom_token_10
LAYER_1_SIZE = 4096        # Codes per layer
LAYER_2_OFFSET = 4096
LAYER_3_OFFSET = 8192

# Regex to extract custom token numbers from vLLM text output
CUSTOM_TOKEN_RE = re.compile(r"<custom_token_(\d+)>")

# Stop tokens (text repr numbers)
STOP_TOKENS = {3, 4, 5, 1, 2}  # custom_token_3..5 are control tokens


class OrpheusTTS:
    """Streaming TTS using Orpheus model via vLLM server + SNAC decoder."""

    def __init__(
        self,
        vllm_url: str = "http://localhost:8001/v1/completions",
        model_name: str = "canopylabs/3b-fr-ft-research_release",
        device: str = "cuda",
        frames_per_chunk: int = 7,
    ):
        self.vllm_url = vllm_url
        self.model_name = model_name
        self.device = device
        self.frames_per_chunk = frames_per_chunk
        self.snac = None

    def load_snac(self):
        """Load SNAC decoder model on GPU."""
        if self.snac is not None:
            return
        print("  Loading SNAC decoder...")
        from snac import SNAC
        self.snac = SNAC.from_pretrained("hubertsiuzdak/snac_24khz")
        self.snac = self.snac.to(self.device).eval()
        print("  SNAC decoder ready")

    def format_prompt(self, text: str, voice: str = "tara") -> str:
        """Format text into Orpheus prompt with voice and control tokens."""
        return (
            f"<custom_token_3>"
            f"<|begin_of_text|>"
            f"{voice}: {text}"
            f"<|eot_id|>"
            f"<custom_token_4>"
            f"<custom_token_5>"
            f"<custom_token_1>"
        )

    def _parse_tokens(self, text: str) -> list[int]:
        """Extract custom token numbers from vLLM text output."""
        tokens = []
        for match in CUSTOM_TOKEN_RE.finditer(text):
            num = int(match.group(1))
            if num not in STOP_TOKENS and num >= TOKEN_OFFSET:
                tokens.append(num)
        return tokens

    def _decode_snac_frame(self, token_numbers: list[int]) -> Optional[np.ndarray]:
        """
        Decode a group of SNAC tokens to PCM audio.
        
        Args:
            token_numbers: List of custom token numbers (must be multiple of 7)
        
        Returns:
            PCM audio as numpy float32 array at 24kHz, or None if invalid
        """
        if len(token_numbers) < 7:
            return None

        # Trim to complete frames only
        n_frames = len(token_numbers) // 7
        token_numbers = token_numbers[: n_frames * 7]

        layer_1, layer_2, layer_3 = [], [], []

        for i, tok in enumerate(token_numbers):
            pos = i % 7
            val = tok - TOKEN_OFFSET  # Remove base offset

            if pos == 0:
                # Layer 1 (coarsest): no additional offset
                code = val % LAYER_1_SIZE
                layer_1.append(code)
            elif pos in (1, 4):
                # Layer 2 (middle): subtract layer 2 offset
                code = (val - LAYER_2_OFFSET) % LAYER_1_SIZE
                layer_2.append(code)
            elif pos in (2, 3, 5, 6):
                # Layer 3 (finest): subtract layer 3 offset
                code = (val - LAYER_3_OFFSET) % LAYER_1_SIZE
                layer_3.append(code)

        # Validate layer sizes
        if not layer_1 or not layer_2 or not layer_3:
            return None
        if len(layer_2) != 2 * len(layer_1):
            return None
        if len(layer_3) != 4 * len(layer_1):
            return None

        try:
            codes = [
                torch.tensor([layer_1], dtype=torch.long).to(self.device),
                torch.tensor([layer_2], dtype=torch.long).to(self.device),
                torch.tensor([layer_3], dtype=torch.long).to(self.device),
            ]
            with torch.no_grad():
                audio = self.snac.decode(codes)
            return audio.squeeze().cpu().numpy()
        except Exception as e:
            print(f"  SNAC decode error: {e}")
            return None

    async def synthesize_streaming(
        self,
        text: str,
        voice: str = "tara",
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream TTS audio from text.
        
        Yields PCM audio chunks (int16, 24kHz, mono) as bytes.
        Each chunk is decoded as soon as enough SNAC tokens arrive.
        
        Args:
            text: Text to speak
            voice: Voice name (tara, leah, etc. or speaker_0 for French)
        """
        self.load_snac()
        prompt = self.format_prompt(text, voice)

        token_buffer: list[int] = []
        tokens_sent = 0

        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream(
                "POST",
                self.vllm_url,
                json={
                    "prompt": prompt,
                    "model": self.model_name,
                    "max_tokens": 2000,
                    "temperature": 0.4,
                    "top_p": 0.9,
                    "repetition_penalty": 1.1,
                    "stream": True,
                    "stop": ["<custom_token_2>"],
                },
            ) as resp:
                buffer_text = ""
                async for chunk in resp.aiter_text():
                    # vLLM SSE format: data: {...}\n\n
                    buffer_text += chunk
                    while "\n" in buffer_text:
                        line, buffer_text = buffer_text.split("\n", 1)
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            import json
                            data = json.loads(data_str)
                            text_chunk = (
                                data.get("choices", [{}])[0]
                                .get("text", "")
                            )
                        except (ValueError, IndexError, KeyError):
                            continue

                        # Parse any new tokens from this chunk
                        new_tokens = self._parse_tokens(text_chunk)
                        token_buffer.extend(new_tokens)

                        # Decode when we have enough complete frames
                        available_frames = (len(token_buffer) - tokens_sent) // 7
                        if available_frames >= self.frames_per_chunk:
                            decode_count = (available_frames // self.frames_per_chunk) * self.frames_per_chunk * 7
                            chunk_tokens = token_buffer[tokens_sent: tokens_sent + decode_count]
                            audio = self._decode_snac_frame(chunk_tokens)
                            if audio is not None:
                                # Convert float32 to int16 PCM
                                audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
                                yield audio_int16.tobytes()
                            tokens_sent += decode_count

        # Decode remaining tokens
        remaining = token_buffer[tokens_sent:]
        if len(remaining) >= 7:
            remaining = remaining[: (len(remaining) // 7) * 7]
            audio = self._decode_snac_frame(remaining)
            if audio is not None:
                audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
                yield audio_int16.tobytes()

    async def synthesize_full(self, text: str, voice: str = "tara") -> bytes:
        """Non-streaming: generate full audio from text."""
        chunks = []
        async for chunk in self.synthesize_streaming(text, voice):
            chunks.append(chunk)
        return b"".join(chunks)
