#!/usr/bin/env python3
"""
V-Glass Auto — Voice Agent v3 Setup
RunPod A40 48GB / Ubuntu 22.04 / CUDA 12.4 / PyTorch 2.4

Installs: vLLM, Whisper turbo, Orpheus FR, SNAC, Silero VAD
Then launches everything via start.sh

Usage: python3 setup_v3.py
"""
import subprocess, os, sys, time, shutil

DIR = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(DIR, "logs")

def run(cmd, desc="", check=True, timeout=600):
    """Run a shell command with error handling."""
    if desc:
        print(f"  {desc}")
    r = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )
    if r.returncode != 0 and check:
        err = r.stderr.strip()[:300] if r.stderr else "unknown error"
        print(f"  WARNING: {err}")
    return r.returncode == 0

def step(n, total, msg):
    print(f"\n[{n}/{total}] {msg}")

TOTAL = 8

print("""
==========================================
  V-GLASS AUTO — VOICE AGENT v3 SETUP
  A40 48GB / RunPod
==========================================
""")

os.makedirs(LOGS, exist_ok=True)

# ---- 1. GPU ----
step(1, TOTAL, "Checking GPU...")
run("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", check=False)

# ---- 2. System deps ----
step(2, TOTAL, "System dependencies...")
run("apt-get update -qq")
run("apt-get install -y -qq curl wget ffmpeg jq zstd git 2>/dev/null")

# ---- 3. Node.js 20 (for n8n later) ----
step(3, TOTAL, "Node.js 20...")
rc = subprocess.run("node -v 2>/dev/null", shell=True, capture_output=True, text=True)
if rc.returncode != 0 or "v20" not in rc.stdout:
    run("apt-get remove -y libnode-dev libnode72 2>/dev/null", check=False)
    run("curl -fsSL https://deb.nodesource.com/setup_20.x | bash -", check=False)
    run("apt-get install -y nodejs 2>/dev/null", check=False)
run("node --version", check=False)

# ---- 4. Python packages (order matters) ----
step(4, TOTAL, "Python packages...")

# Install vLLM first (needs specific version for Orpheus compat)
print("  Installing vLLM...")
run("pip install vllm -q", desc="vLLM")

# Install transformers (pin version for PyTorch 2.4 compat)
print("  Installing transformers...")
run("pip install transformers==4.44.0 -q", desc="transformers 4.44")

# Install SNAC decoder
print("  Installing SNAC...")
run("pip install snac -q", desc="SNAC")

# Install Whisper
print("  Installing faster-whisper...")
run("pip install faster-whisper -q", desc="faster-whisper")

# Install FastAPI + deps
print("  Installing server deps...")
run("pip install fastapi uvicorn httpx websockets python-multipart -q")

# Install Silero VAD deps
print("  Installing Silero VAD deps...")
run("pip install onnxruntime -q")

print("  All Python packages installed")

# ---- 5. Download models (in background) ----
step(5, TOTAL, "Pre-downloading models...")

print("  This downloads ~15GB of models. Be patient.")
print("  Qwen3 8B + Orpheus 3B FR + Whisper turbo + SNAC decoder")

# Download Whisper model now (it downloads on first use anyway)
print("  Pre-loading Whisper turbo...")
run(
    'python3 -c "'
    "from faster_whisper import WhisperModel; "
    "WhisperModel('deepdml/faster-whisper-large-v3-turbo-ct2', device='cpu', compute_type='int8')"
    '"',
    desc="Whisper model download",
    timeout=600,
)

# Download SNAC model
print("  Pre-loading SNAC decoder...")
run(
    'python3 -c "'
    "from snac import SNAC; "
    "SNAC.from_pretrained('hubertsiuzdak/snac_24khz')"
    '"',
    desc="SNAC model download",
    timeout=300,
)

# Download Silero VAD
print("  Pre-loading Silero VAD...")
run(
    'python3 -c "'
    "import torch; "
    "torch.hub.load('snakers4/silero-vad', 'silero_vad', trust_repo=True)"
    '"',
    desc="Silero VAD download",
    timeout=120,
)

print("  Core models downloaded")
print("  (Qwen3 8B and Orpheus FR will download when vLLM starts)")

# ---- 6. Make scripts executable ----
step(6, TOTAL, "Setting permissions...")
run(f"chmod +x {DIR}/start.sh {DIR}/stop.sh")

# ---- 7. Verify installation ----
step(7, TOTAL, "Verifying installation...")

checks = [
    ("vLLM", "python3 -c 'import vllm; print(vllm.__version__)'"),
    ("faster-whisper", "python3 -c 'import faster_whisper; print(\"ok\")'"),
    ("SNAC", "python3 -c 'import snac; print(\"ok\")'"),
    ("FastAPI", "python3 -c 'import fastapi; print(fastapi.__version__)'"),
    ("httpx", "python3 -c 'import httpx; print(\"ok\")'"),
]

all_ok = True
for name, cmd in checks:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode == 0:
        ver = r.stdout.strip()
        print(f"  OK  {name} ({ver})")
    else:
        print(f"  FAIL {name}: {r.stderr.strip()[:100]}")
        all_ok = False

if not all_ok:
    print("\n  Some packages failed. Check errors above.")
    print("  You can try running setup_v3.py again.")
    sys.exit(1)

# ---- 8. Launch ----
step(8, TOTAL, "Launching services...")
print("  Running start.sh...")
print("  This will download Qwen3 8B + Orpheus FR on first run (~10 min)")
print()

os.chdir(DIR)
os.execvp("bash", ["bash", f"{DIR}/start.sh"])
