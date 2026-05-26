#!/usr/bin/env python3
"""
V-Glass Auto AI Agent — One-click setup
Run: python3 setup.py
"""
import subprocess, os, time, sys

DIR = "/workspace/parebrise-ai"
LOGS = f"{DIR}/logs"

def run(cmd, check=False):
    print(f"  → {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(f"  ⚠ {r.stderr.strip()[:200]}")
    return r.returncode == 0

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

print("""
╔══════════════════════════════════════════╗
║  🔧 V-GLASS AUTO — AI AGENT SETUP       ║
║  One-click install                       ║
╚══════════════════════════════════════════╝
""")

os.makedirs(LOGS, exist_ok=True)

# 1. GPU check
print("✅ 1/8 GPU")
run("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")

# 2. System deps
print("✅ 2/8 System deps")
run("apt-get update -qq")
run("apt-get install -y -qq curl wget redis-server postgresql postgresql-contrib ffmpeg supervisor jq zstd 2>/dev/null")

# 3. Ollama
print("✅ 3/8 Ollama")
if not run("which ollama"):
    run("curl -fsSL https://ollama.com/install.sh | sh")
run("pkill ollama 2>/dev/null; sleep 1")
subprocess.Popen("ollama serve", shell=True, stdout=open(f"{LOGS}/ollama.log","w"), stderr=open(f"{LOGS}/ollama.err","w"))
time.sleep(3)

# 4. n8n
print("✅ 4/8 n8n")
if not run("which n8n"):
    run("npm install -g n8n")

# 5. Python deps
print("✅ 5/8 Python packages")
run("pip install faster-whisper fastapi uvicorn python-multipart httpx kokoro soundfile scipy numpy aiofiles -q")

# 6. Qdrant
print("✅ 6/8 Qdrant")
if not run("which qdrant"):
    run("cd /tmp && wget -q https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-musl.tar.gz && tar -xzf qdrant-x86_64-unknown-linux-musl.tar.gz && mv qdrant /usr/local/bin/")

# 7. PostgreSQL + Redis
print("✅ 7/8 PostgreSQL + Redis")
run("service postgresql start")
run("service redis-server start")
run("""su - postgres -c "psql -c \\"CREATE USER agent WITH PASSWORD 'agent_pass';\\"" 2>/dev/null""")
run("""su - postgres -c "psql -c \\"CREATE DATABASE n8n OWNER agent;\\"" 2>/dev/null""")

# 8. Supervisor
print("✅ 8/8 Supervisor")

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
command=/usr/local/bin/qdrant --storage-path {DIR}/qdrant_data
autostart=true
autorestart=true
stdout_logfile={LOGS}/qdrant.log
stderr_logfile={LOGS}/qdrant.err
""")

run("supervisord -c /etc/supervisor/supervisord.conf 2>/dev/null || true")
run("supervisorctl reread")
run("supervisorctl update")
run("supervisorctl start all")

# 9. Pull model
print("\n⬇️  Pulling Qwen3 8B model (5GB, ~5 min)...")
time.sleep(5)
run("ollama pull qwen3:8b")

# 10. Status
print("\n⏳ Waiting for services...")
time.sleep(10)
run("supervisorctl status")

print("""
╔══════════════════════════════════════════════╗
║  ✅ V-GLASS AUTO AI — READY!                 ║
╠══════════════════════════════════════════════╣
║                                              ║
║  🎤 Voice Chat → port 8880                   ║
║  ⚙️  n8n        → port 5678                   ║
║  🧠 Ollama     → port 11434                  ║
║  📦 Qdrant     → port 6333                   ║
║                                              ║
║  Open port 8880 URL in your browser          ║
║  and start talking!                          ║
║                                              ║
╚══════════════════════════════════════════════╝
""")
