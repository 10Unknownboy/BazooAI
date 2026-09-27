# Preserve any existing checkout and user files.

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — edit these before running
# ═══════════════════════════════════════════════════════════════

# Force the ungated local model; do not send inference to an external API.
LLM_BACKEND = "local"
HF_MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"
HF_DTYPE = "float16"  # "float16" or "bfloat16"
REPO_REF = "main"  # Set to the branch containing the latest local-only model-server code.

# --- ngrok (to expose the server to your local machine) ---
# Get a free token at https://dashboard.ngrok.com/get-started/your-authtoken
NGROK_AUTH_TOKEN = ""  # Supply via Colab Secrets, never in source code

# ═══════════════════════════════════════════════════════════════
# Load from Colab Secrets if available (overrides above)
# ═══════════════════════════════════════════════════════════════
try:
    from google.colab import userdata
    NGROK_AUTH_TOKEN = NGROK_AUTH_TOKEN or userdata.get("NGROK_AUTH_TOKEN", "")
except Exception:
    pass

print(f"Backend:          {LLM_BACKEND}")
print(f"Local model:      {HF_MODEL_NAME}")
if not NGROK_AUTH_TOKEN:
    raise RuntimeError("Set NGROK_AUTH_TOKEN in Colab Secrets before starting the server.")

# --- Check GPU ---
import subprocess
gpu_info = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
                           "--format=csv,noheader"], capture_output=True, text=True)
if gpu_info.returncode == 0:
    print(f"🟢 GPU detected: {gpu_info.stdout.strip()}")
else:
    raise RuntimeError("GPU unavailable; select Runtime → Change runtime type → GPU.")

%%capture
# --- Install Python packages ---
!pip install -q \
    "transformers>=4.45,<5" \
    accelerate \
    sentencepiece \
    protobuf \
    fastapi \
    uvicorn[standard] \
    httpx \
    pydantic \
    pyngrok \
    pyyaml \
    python-dotenv

import os, subprocess

REPO_URL = "https://github.com/10Unknownboy/BazooAI.git"
REPO_DIR = "/content/BazooAI"
PROJECT_DIR = REPO_DIR

if os.path.exists(PROJECT_DIR):
    print(f"📁 Project already cloned at {PROJECT_DIR}")
    subprocess.run(["git", "-C", REPO_DIR, "fetch", "origin", REPO_REF], check=True)
    subprocess.run(["git", "-C", REPO_DIR, "checkout", REPO_REF], check=True)
    subprocess.run(["git", "-C", REPO_DIR, "pull", "--ff-only", "origin", REPO_REF], check=True)
else:
    print(f"📥 Cloning {REPO_URL} ...")
    subprocess.run(
        ["git", "clone", "--branch", REPO_REF, "--single-branch", REPO_URL, REPO_DIR],
        check=True,
    )

# Verify project structure
assert os.path.exists(f"{PROJECT_DIR}/app"), f"❌ {PROJECT_DIR}/app not found!"
assert os.path.exists(f"{PROJECT_DIR}/app/api/model_server.py"), "❌ model_server.py not found!"
print(f"✅ Project structure verified at {PROJECT_DIR}")

# Add project to Python path so imports work
import sys
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
    print(f"✅ Added {PROJECT_DIR} to sys.path")

import os

# Backend
os.environ["LLM_BACKEND"] = LLM_BACKEND
os.environ["HF_MODEL_NAME"] = HF_MODEL_NAME
os.environ["HF_DTYPE"] = HF_DTYPE

# Server
os.environ["API_HOST"] = "0.0.0.0"
os.environ["API_PORT"] = "8000"

print("✅ Environment variables set")

import time

# Import the model server module
from app.api.model_server import router, LLMBackend

print(f"🔧 Initializing backend (mode={LLM_BACKEND}) ...")
print(f"   Local model:    {HF_MODEL_NAME}")
print()

start = time.time()
active = router.initialize(
    force_backend=LLM_BACKEND,
    model_name=HF_MODEL_NAME,
    dtype=HF_DTYPE,
)
elapsed = time.time() - start

print()
print("=" * 60)
if active == LLMBackend.LOCAL:
    print(f"✅ LOCAL backend active: {router.local.model_name}")
    print(f"   Device: {router.local.device}")
    import torch
    if torch.cuda.is_available():
        alloc = torch.cuda.memory_allocated() / 1024**3
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3 # Changed total_mem to total_memory
        print(f"   GPU memory: {alloc:.1f} / {total:.1f} GB")
else:
    raise RuntimeError(
        "Local model failed to load; refusing mock/external fallback: "
        f"{router.local.load_error or 'unknown loading error'}"
    )
print(f"   Init time: {elapsed:.1f}s")
print("=" * 60)

import asyncio
import json
from app.api.model_server import router, build_task_prompt, parse_llm_json, AIRequest

# Build a test request
test_request = AIRequest(
    request_id="TEST_001",
    message_type="DJ_DECISION",
    event_type="college_party",
    event_progress=0.5,
    current_energy=0.8,
    target_energy=0.85,
    recent_genres=["Punjabi Pop", "Bollywood"],
    allowed_languages=["Hindi", "Punjabi", "English"],
    candidate_songs=[
        {"song_id": "S1", "title": "Tauba Tauba", "artist": "Karan Aujla",
         "genre": "Punjabi Pop", "energy": 0.91, "bpm": 104},
        {"song_id": "S2", "title": "Brown Munde", "artist": "AP Dhillon",
         "genre": "Punjabi Pop", "energy": 0.88, "bpm": 100},
        {"song_id": "S3", "title": "Kala Chashma", "artist": "Amar Arshi",
         "genre": "Bollywood", "energy": 0.85, "bpm": 110},
    ],
)

# Build prompt
prompt = build_task_prompt(test_request)
print("📝 PROMPT:")
print("-" * 60)
print(prompt[:800])
print("-" * 60)

# Generate
print("\n🤖 Generating response...")
raw_text, backend, inference_error = await router.generate(prompt)

print(f"\n📡 Backend used: {backend}")
print(f"\n📄 RAW OUTPUT:")
print(raw_text[:500] if raw_text else "(empty)")

# Parse
if raw_text:
    parsed = parse_llm_json(raw_text)
    print(f"\n✅ PARSED JSON:")
    print(json.dumps(parsed, indent=2, default=str)[:500])
else:
    raise RuntimeError(f"Local model inference failed: {inference_error or 'empty response'}")
if not backend.startswith("local:") or "raw_output" in parsed:
    raise RuntimeError(f"Local-model smoke test failed: backend={backend}; parsed={parsed}")


# Start FastAPI before opening the ngrok tunnel. The tunnel must never point
# at port 8000 until the upstream health check succeeds.
import asyncio

import httpx
import uvicorn
from app.api.model_server import app

config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
server = uvicorn.Server(config)
server_task = asyncio.create_task(server.serve())
async with httpx.AsyncClient(timeout=10) as client:
    for _ in range(180):
        if server_task.done():
            await server_task
        try:
            response = await client.get("http://127.0.0.1:8000/health")
            response.raise_for_status()
            health = response.json()
            if health.get("active_backend") != "local":
                server.should_exit = True
                await server_task
                raise RuntimeError(f"Local model server started unhealthy: {health}")
            break
        except httpx.HTTPError:
            await asyncio.sleep(1)
    else:
        server.should_exit = True
        await server_task
        raise RuntimeError("FastAPI did not become healthy on port 8000")

raw_text, backend, inference_error = await router.generate(
    'Return ONLY a JSON object with keys "ready" (boolean) and "model" (string). Set ready to true.',
    max_tokens=80,
)
parsed = parse_llm_json(raw_text)
if not backend.startswith("local:") or not parsed.get("ready"):
    server.should_exit = True
    await server_task
    raise RuntimeError(
        f"Local inference smoke test failed: backend={backend}, error={inference_error}"
    )

from pyngrok import ngrok

ngrok.set_auth_token(NGROK_AUTH_TOKEN)
tunnel = ngrok.connect(addr="127.0.0.1:8000", proto="http")
public_url = tunnel.public_url
print(f"ngrok tunnel active: {public_url}")
print(f"Set AI_MODEL_URL={public_url} in your local .env")
print(f"Health check: {public_url}/health")
print("FastAPI is healthy with the local model; press stop to end the server.")
await server_task

import httpx, json

resp = httpx.get("http://localhost:8000/health")
print(json.dumps(resp.json(), indent=2))

!nvidia-smi

import httpx, json

test_payload = {
    "request_id": "MANUAL_TEST",
    "message_type": "VIBE_UPDATE",
    "event_type": "college_party",
    "current_energy": 0.7,
    "target_energy": 0.9,
    "recent_genres": ["Bollywood", "Punjabi Pop"],
    "allowed_languages": ["Hindi", "Punjabi", "English"],
}

resp = httpx.post("http://localhost:8000/v1/ai/decide", json=test_payload, timeout=60.0)
result = resp.json()
print(f"Status: {resp.status_code}")
print(f"Backend: {result.get('model_name')}")
print(f"Latency: {result.get('latency_ms', 0):.0f}ms")
print(json.dumps(result, indent=2, default=str)[:600])

import gc, torch
from app.api.model_server import router

if router.local.model is not None:
    del router.local.model
    del router.local.tokenizer
    router.local.model = None
    router.local.tokenizer = None
    router.local.loaded = False
    gc.collect()
    torch.cuda.empty_cache()
    print("✅ GPU memory freed")
    !nvidia-smi
else:
    print("No local model loaded")