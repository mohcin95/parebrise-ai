#!/usr/bin/env python3
"""
V-Glass Auto AI Agent — One-click setup
Tested on RunPod PyTorch 2.4.0 / Ubuntu 22.04 / CUDA 12.4
Run: python3 setup.py
"""
import subprocess, os, time, sys

DIR = os.path.dirname(os.path.abspath(__file__))
LOGS = f"{DIR}/logs"

def run(cmd, check=False):
    print(f"  > {cmd[:80]}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(f"  ! {r.stderr.strip()[:200]}")
    return r.returncode == 0

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

print("""
==================================
  V-GLASS AUTO — AI AGENT SETUP
  One-click install
==================================
""")
os.makedirs(LOGS, exist_ok=True)

# 1
print("1/9 GPU")
run("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")

# 2
print("2/9 System deps")
run("apt-get update -qq")
run("apt-get install -y -qq curl wget redis-server postgresql postgresql-contrib ffmpeg supervisor jq zstd 2>/dev/null")

# 3 Node 20 (avoid conflict with old node)
print("3/9 Node.js 20")
if not run("node -v 2>/dev/null | grep -q 'v2'"):
    run("apt-get remove -y libnode-dev libnode72 2>/dev/null")
    run("curl -fsSL https://deb.nodesource.com/setup_20.x | bash -")
    run("apt-get install -y nodejs")
run("node --version")

# 4 n8n
print("4/9 n8n")
if not run("which n8n"):
    run("npm install -g n8n")

# 5 Ollama
print("5/9 Ollama")
if not run("which ollama"):
    run("curl -fsSL https://ollama.com/install.sh | sh")
run("pkill ollama 2>/dev/null; sleep 1")
subprocess.Popen("ollama serve", shell=True,
    stdout=open(f"{LOGS}/ollama.log","w"),
    stderr=open(f"{LOGS}/ollama.err","w"))
time.sleep(3)

# 6 Python deps (order matters: transformers 4.40 before kokoro)
print("6/9 Python packages")
run("pip install transformers==4.40.0 -q")
run("pip install faster-whisper fastapi uvicorn python-multipart httpx kokoro soundfile scipy numpy aiofiles websockets -q")

# 7 Qdrant
print("7/9 Qdrant")
if not run("which qdrant"):
    run("cd /tmp && wget -q https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-musl.tar.gz && tar -xzf qdrant-x86_64-unknown-linux-musl.tar.gz && mv qdrant /usr/local/bin/")

# 8 PostgreSQL + Redis
print("8/9 PostgreSQL + Redis")
run("service postgresql start")
run("service redis-server start")
run("""su - postgres -c "psql -c \\"CREATE USER agent WITH PASSWORD 'agent_pass';\\"" 2>/dev/null""")
run("""su - postgres -c "psql -c \\"CREATE DATABASE n8n OWNER agent;\\"" 2>/dev/null""")

# 9 Supervisor
print("9/9 Supervisor")
write("/etc/supervisor/conf.d/parebrise.conf", f"""[program:ollama]
command=ollama serve
autostart=true
autorestart=true
stdout_logfile={LOGS}/ollama.log
stderr_logfile={LOGS}/ollama.err

[program:n8n]
command=n8n start
environment=N8N_HOST="0.0.0.0",N8N_PORT="5678",N8N_PROTOCOL="http",GENERIC_TIMEZONE="Europe/Paris",N8N_AI_ENABLED="true",DB_TYPE="postgresdb",DB_POSTGRESDB_HOST="localhost",DB_POSTGRESDB_PORT="5432",DB_POSTGRESDB_DATABASE="n8n",DB_POSTGRESDB_USER="agent",DB_POSTGRESDB_PASSWORD="agent_pass"
autostart=true
autorestart=true
stdout_logfile={LOGS}/n8n.log
stderr_logfile={LOGS}/n8n.err

[program:voice]
command=python3 {DIR}/voice_server.py
directory={DIR}
autostart=true
autorestart=true
stdout_logfile={LOGS}/voice.log
stderr_logfile={LOGS}/voice.err

[program:qdrant]
command=/usr/local/bin/qdrant
environment=QDRANT__STORAGE__STORAGE_PATH="{DIR}/qdrant_data"
autostart=true
autorestart=true
stdout_logfile={LOGS}/qdrant.log
stderr_logfile={LOGS}/qdrant.err
""")

run("supervisord -c /etc/supervisor/supervisord.conf 2>/dev/null || true")
run("supervisorctl reread")
run("supervisorctl update")
run("supervisorctl start all")

# Pull model
print("")
print("Pulling Qwen3 8B (~5GB, 5 min)...")
time.sleep(5)
run("ollama pull qwen3:8b")

# Wait for voice server to load models
print("Waiting for Whisper + Kokoro to load (~90s)...")
time.sleep(90)

# Status
run("supervisorctl status")
run("curl -s -o /dev/null -w '%{http_code}' http://localhost:8880/")

print("""
==================================
  V-GLASS AUTO AI — READY!
==================================

  Voice Chat -> port 8880
  n8n        -> port 5678
  Ollama     -> port 11434
  Qdrant     -> port 6333

  Open port 8880 URL in browser
  and start talking!
==================================
""")
