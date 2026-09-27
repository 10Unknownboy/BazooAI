# Preserve any existing checkout and user files.

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — edit these before running
# ═══════════════════════════════════════════════════════════════

# --- Backend selection ---
# "auto"     = try local HF model, fall back to external API if OOM
# "local"    = force local model (will fail if not enough VRAM)
# "external" = skip local model, use OpenRouter only
LLM_BACKEND = "auto"

# --- Local HuggingFace model ---
# Small models that fit on a free T4 (15 GB VRAM):
#   "TinyLlama/TinyLlama-1.1B-Chat-v1.0"     (~2 GB)  ← default
#   "microsoft/Phi-3.5-mini-instruct"          (~7 GB)
#   "Qwen/Qwen2.5-3B-Instruct"                (~6 GB)
#   "google/gemma-2-2b-it"                     (~5 GB)
# Larger models (need A100 or high-RAM T4):
#   "mistralai/Mistral-7B-Instruct-v0.3"      (~14 GB)
#   "meta-llama/Meta-Llama-3.1-8B-Instruct"   (~16 GB, gated)
HF_MODEL_NAME = "google/gemma-2-2b-it"
HF_DTYPE = "float16"  # "float16" or "bfloat16"

# --- External API (OpenRouter) ---
# Get a free key at https://openrouter.ai/keys
# Free models: "mistralai/mistral-7b-instruct:free",
#              "meta-llama/llama-3.1-8b-instruct:free"
OPENROUTER_API_KEY = ""  # Supply via Colab Secrets, never in source code
OPENROUTER_MODEL = "openrouter/free"

# --- ngrok (to expose the server to your local machine) ---
# Get a free token at https://dashboard.ngrok.com/get-started/your-authtoken
NGROK_AUTH_TOKEN = ""  # Supply via Colab Secrets, never in source code

# --- HuggingFace token (only needed for gated models like Llama) ---
HF_TOKEN = ""  # Supply via Colab Secrets, never in source code

# ═══════════════════════════════════════════════════════════════
# Load from Colab Secrets if available (overrides above)
# ═══════════════════════════════════════════════════════════════
try:
    from google.colab import userdata
    OPENROUTER_API_KEY = OPENROUTER_API_KEY or userdata.get("OPENROUTER_API_KEY", "")
    NGROK_AUTH_TOKEN = NGROK_AUTH_TOKEN or userdata.get("NGROK_AUTH_TOKEN", "")
    HF_TOKEN = HF_TOKEN or userdata.get("HF_TOKEN", "")
except Exception:
    pass

print(f"Backend:          {LLM_BACKEND}")
print(f"Local model:      {HF_MODEL_NAME}")
print(f"External model:   {OPENROUTER_MODEL}")
print(f"OpenRouter key:   {'✅ set' if OPENROUTER_API_KEY else '❌ not set'}")
print(f"ngrok token:      {'✅ set' if NGROK_AUTH_TOKEN else '❌ not set'}")
print(f"HF token:         {'✅ set' if HF_TOKEN else '⚪ not set (only needed for gated models)'}")

# --- Check GPU ---
import subprocess
gpu_info = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
                           "--format=csv,noheader"], capture_output=True, text=True)
if gpu_info.returncode == 0:
    print(f"🟢 GPU detected: {gpu_info.stdout.strip()}")
else:
    print("🔴 No GPU detected! Go to Runtime → Change runtime type → T4 GPU")
    print("   The server will still work with external API or mock mode.")

%%capture
# --- Install Python packages ---
!pip install -q \
    torch \
    transformers \
    accelerate \
    bitsandbytes \
    sentencepiece \
    protobuf \
    fastapi \
    uvicorn[standard] \
    httpx \
    pydantic \
    pyngrok \
    pyyaml \
    python-dotenv \
    nest_asyncio

import os

REPO_URL = "https://github.com/10Unknownboy/BazooAI.git"
REPO_DIR = "/content/BazooAI"
PROJECT_DIR = REPO_DIR # Corrected: 'ai_dj_system' subdirectory does not exist directly under BazooAI

if os.path.exists(PROJECT_DIR):
    print(f"📁 Project already cloned at {PROJECT_DIR}")
    # Pull latest changes
    !cd {REPO_DIR} && git pull --ff-only 2>/dev/null || echo "Already up to date"
else:
    print(f"📥 Cloning {REPO_URL} ...")
    !git clone {REPO_URL} {REPO_DIR}

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

# External API
if OPENROUTER_API_KEY:
    os.environ["OPENROUTER_API_KEY"] = OPENROUTER_API_KEY
    os.environ["OPENROUTER_MODEL"] = OPENROUTER_MODEL

# HuggingFace token
if HF_TOKEN:
    os.environ["HF_TOKEN"] = HF_TOKEN
    os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN

# Server
os.environ["API_HOST"] = "0.0.0.0"
os.environ["API_PORT"] = "8000"

print("✅ Environment variables set")

import time

# Import the model server module
from app.api.model_server import router, LLMBackend

print(f"🔧 Initializing backend (mode={LLM_BACKEND}) ...")
print(f"   Local model:    {HF_MODEL_NAME}")
print(f"   External API:   {'configured' if OPENROUTER_API_KEY else 'not configured'}")
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
elif active == LLMBackend.EXTERNAL:
    print(f"✅ EXTERNAL backend active: {router.external.model_name}")
    if router.local.load_error:
        print(f"   (Local model failed: {router.local.load_error})")
else:
    print("⚠️  MOCK backend active (no real LLM)")
    if router.local.load_error:
        print(f"   Local error: {router.local.load_error}")
    if not router.external.available:
        print("   External: no API key configured")
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
raw_text, backend = await router.generate(prompt)

print(f"\n📡 Backend used: {backend}")
print(f"\n📄 RAW OUTPUT:")
print(raw_text[:500] if raw_text else "(empty — mock mode)")

# Parse
if raw_text:
    parsed = parse_llm_json(raw_text)
    print(f"\n✅ PARSED JSON:")
    print(json.dumps(parsed, indent=2, default=str)[:500])
else:
    print("\n⚠️ No output from model — mock responses will be used")


# --- Setup ngrok ---
from pyngrok import ngrok, conf

if NGROK_AUTH_TOKEN:
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)
    tunnel = ngrok.connect("127.0.0.1:8000", "http")
    public_url = tunnel.public_url
    print("=" * 60)
    print(f"🌐 ngrok tunnel active!")
    print(f"")
    print(f"   PUBLIC URL:  {public_url}")
    print(f"")
    print(f"   Set this in your local .env file:")
    print(f"   AI_MODEL_URL={public_url}")
    print(f"")
    print(f"   Health check: {public_url}/health")
    print(f"   API docs:     {public_url}/docs")
    print("=" * 60)
else:
    print("⚠️  No NGROK_AUTH_TOKEN set — server will only be accessible within Colab")
    print("   Get a free token at: https://dashboard.ngrok.com/get-started/your-authtoken")
    public_url = "http://localhost:8000"

# --- Start FastAPI server ---
# This cell blocks and runs the server. The server will keep running
# until you stop this cell or the Colab runtime disconnects.

import uvicorn
from app.api.model_server import app

print(f"🚀 Starting AI DJ Model Server...")
print(f"   Backend: {router.active_backend.value}")
print(f"   Listening on: 0.0.0.0:8000")
if NGROK_AUTH_TOKEN:
    print(f"   Public URL: {public_url}")
print()
print("Press the ⏹️ button to stop the server.")
print("-" * 60)

# Using uvicorn.Server directly to avoid nest_asyncio loop_factory errors in Colab
config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
server = uvicorn.Server(config)
await server.serve()

import httpx, json

resp = httpx.get("http://localhost:8000/health")
print(json.dumps(resp.json(), indent=2))

import httpx, json

# Switch to external API
resp = httpx.post("http://localhost:8000/v1/backend/switch", json={
    "backend": "external",  # "local", "external", or "auto"
    # "model_name": "Qwen/Qwen2.5-3B-Instruct",  # optional: change model
})
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