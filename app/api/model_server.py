"""
AI DJ Model Server — Dual-backend LLM inference.

Runs as a FastAPI app (intended for Google Colab behind ngrok).

Backends:
  1. LOCAL — HuggingFace Transformers model loaded on the Colab GPU.
  2. EXTERNAL — OpenRouter (or any OpenAI-compatible API) in auto/external mode.

Set LLM_BACKEND=local to fail closed without using an external provider.
In auto mode, the server may fall back to the external API if local inference fails.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import re
import time
import traceback
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# ---------------------------------------------------------------------------
# Pydantic request / response schemas (self-contained so the server can
# run stand-alone in Colab without the full project installed).
# When the project IS installed, we re-export from app.models.agent.
# ---------------------------------------------------------------------------
try:
    from app.models.agent import AIRequest, AIResponse
    _PROJECT_INSTALLED = True
except ImportError:
    _PROJECT_INSTALLED = False

    class AIRequest(BaseModel):  # type: ignore[no-redef]
        request_id: str = ""
        message_type: str = "DJ_DECISION"
        event_type: str | None = None
        event_progress: float | None = None
        current_vibe: dict | None = None
        target_energy: float | None = None
        current_energy: float | None = None
        current_song_id: str | None = None
        recent_song_ids: list[str] = Field(default_factory=list)
        recent_genres: list[str] = Field(default_factory=list)
        recent_artists: list[str] = Field(default_factory=list)
        candidate_songs: list[dict] = Field(default_factory=list)
        request_data: dict = Field(default_factory=dict)
        queue_data: list[dict] = Field(default_factory=list)
        lyrics_data: dict = Field(default_factory=dict)
        custom_instructions: str = ""
        audience_age_range: list[int] = Field(default_factory=list)
        allowed_languages: list[str] = Field(default_factory=list)
        timestamp: str | None = None

    class AIResponse(BaseModel):  # type: ignore[no-redef]
        request_id: str = ""
        message_type: str = "DJ_DECISION"
        success: bool = True
        error: str | None = None
        decision: str | None = None
        reason: str = ""
        confidence: float = 0.0
        recommended_vibe: dict | None = None
        recommended_energy: float | None = None
        preferred_genres: list[str] = Field(default_factory=list)
        preferred_languages: list[str] = Field(default_factory=list)
        preferred_artists: list[str] = Field(default_factory=list)
        avoid_genres: list[str] = Field(default_factory=list)
        avoid_artists: list[str] = Field(default_factory=list)
        recommended_song_ids: list[str] = Field(default_factory=list)
        rejected_song_ids: list[str] = Field(default_factory=list)
        request_decision: str | None = None
        bridge_strategy: list[str] | None = None
        recommended_position: int | None = None
        lyrics_analysis: dict = Field(default_factory=dict)
        queue_approved: bool = True
        queue_changes: list[dict] = Field(default_factory=list)
        event_summary: dict = Field(default_factory=dict)
        model_name: str | None = None
        latency_ms: float | None = None
        timestamp: str | None = None


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
logger = logging.getLogger("ai_dj.model_server")


# ═══════════════════════════════════════════════════════════════════════════
# Backend enum
# ═══════════════════════════════════════════════════════════════════════════
class LLMBackend(str, Enum):
    LOCAL = "local"
    EXTERNAL = "external"
    MOCK = "mock"


# ═══════════════════════════════════════════════════════════════════════════
# System prompt
# ═══════════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """\
You are an autonomous professional DJ AI. You reason about music selection
for live events. Your goals (in priority order):
1. Event suitability and crowd satisfaction
2. Vibe consistency and smooth transitions
3. Appropriate energy progression
4. Request satisfaction when compatible with the vibe
5. Musical variety within the event context
6. Policy compliance (never override hard policies)
7. Incorporate learned contextual preferences

RESPONSE RULES — you MUST:
• Reply ONLY with valid JSON (no markdown fences, no commentary).
• Use ONLY song IDs from the provided candidates — NEVER invent songs.
• Never override hard policy decisions.
• Always include "decision", "reason", and "confidence" (0-1) keys.
"""


# ═══════════════════════════════════════════════════════════════════════════
# 1. LOCAL BACKEND — HuggingFace Transformers
# ═══════════════════════════════════════════════════════════════════════════
class LocalModelBackend:
    """Wraps a HuggingFace causal-LM loaded on the Colab GPU."""

    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.model_name: str = ""
        self.device: str = "cpu"
        self.loaded: bool = False
        self.load_error: str | None = None

    # ------------------------------------------------------------------
    def load(
        self,
        model_name: str = "",
        dtype: str = "float16",
        max_memory_mb: int | None = None,
    ) -> bool:
        """
        Attempt to load a HuggingFace model. Returns True on success.
        On OOM or any failure, sets self.load_error and returns False.
        """
        model_name = model_name or os.getenv(
            "HF_MODEL_NAME", "Qwen/Qwen2.5-1.5B-Instruct"
        )
        self.model_name = model_name
        logger.info(f"[LOCAL] Loading model: {model_name}  (dtype={dtype})")

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"[LOCAL] Device: {self.device}")

            if self.device == "cuda":
                free_mem = torch.cuda.mem_get_info()[0] / (1024 ** 2)
                logger.info(f"[LOCAL] Free GPU memory: {free_mem:.0f} MB")
                if max_memory_mb and free_mem < max_memory_mb:
                    raise MemoryError(
                        f"Only {free_mem:.0f} MB free, need ~{max_memory_mb} MB"
                    )

            torch_dtype = getattr(torch, dtype, torch.float16)

            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name, trust_remote_code=True
            )
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            load_kwargs: dict[str, Any] = {
                "torch_dtype": torch_dtype,
                "trust_remote_code": True,
                "low_cpu_mem_usage": True,
            }
            if self.device == "cuda":
                load_kwargs["device_map"] = "auto"

            self.model = AutoModelForCausalLM.from_pretrained(
                model_name, **load_kwargs
            )
            self.model.eval()
            self.loaded = True
            logger.info(f"[LOCAL] Model loaded successfully on {self.device}")
            return True

        except Exception as e:
            self.load_error = f"{type(e).__name__}: {e}"
            logger.error(f"[LOCAL] Failed to load model: {self.load_error}")
            # Clean up partial loads
            self.model = None
            self.tokenizer = None
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    def generate(self, prompt: str, max_new_tokens: int = 1024) -> str:
        """Run inference on the loaded model."""
        if not self.loaded or self.model is None or self.tokenizer is None:
            raise RuntimeError("Local model not loaded")

        import torch

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        # Try chat template first; fall back to raw concatenation
        try:
            text = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            text = f"{SYSTEM_PROMPT}\n\nUser: {prompt}\n\nAssistant:"

        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=4096)
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
                pad_token_id=self.tokenizer.pad_token_id,
            )

        generated = outputs[0][inputs["input_ids"].shape[1]:]
        return self.tokenizer.decode(generated, skip_special_tokens=True).strip()


# ═══════════════════════════════════════════════════════════════════════════
# 2. EXTERNAL BACKEND — OpenRouter / OpenAI-compatible API
# ═══════════════════════════════════════════════════════════════════════════
class ExternalAPIBackend:
    """Calls an OpenAI-compatible chat-completions endpoint (OpenRouter, etc.)."""

    def __init__(self):
        self.api_key: str = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("LLM_API_KEY", "")
        self.base_url: str = os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        )
        self.model_name: str = os.getenv(
            "OPENROUTER_MODEL", "openrouter/free"
        )
        self.available: bool = bool(self.api_key)
        if not self.available:
            logger.warning("[EXTERNAL] No API key found (OPENROUTER_API_KEY / LLM_API_KEY)")

    # ------------------------------------------------------------------
    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        if not self.available:
            raise RuntimeError("External API key not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/10Unknownboy/BazooAI",
            "X-Title": "AI DJ System",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"].get("content")
            if not content:
                raise RuntimeError("External AI provider returned an empty response")
            return content.strip()


def _backend_error_message(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        try:
            body = error.response.json()
            details = body.get("error", {})
            metadata = details.get("metadata", {}) if isinstance(details, dict) else {}
            description = (
                metadata.get("raw")
                or (details.get("message") if isinstance(details, dict) else None)
                or error.response.reason_phrase
            )
            return f"HTTP {error.response.status_code}: {str(description)[:300]}"
        except (ValueError, TypeError):
            return f"HTTP {error.response.status_code}: {error.response.reason_phrase}"
    return str(error)


# ═══════════════════════════════════════════════════════════════════════════
# 3. INFERENCE ROUTER — ties the two backends together
# ═══════════════════════════════════════════════════════════════════════════
class InferenceRouter:
    """
    Routes inference to the selected backend and enforces local-only mode when requested.
    """

    def __init__(self):
        self.local = LocalModelBackend()
        self.external = ExternalAPIBackend()
        self.active_backend: LLMBackend = LLMBackend.MOCK
        self.local_only = False
        self.request_count: int = 0
        self.local_count: int = 0
        self.external_count: int = 0
        self.error_count: int = 0

    # ------------------------------------------------------------------
    def initialize(self, force_backend: str = "auto", **local_kwargs) -> LLMBackend:
        """
        Initialize the inference backend.

        force_backend: "auto" | "local" | "external"
        """
        force = force_backend.lower()
        self.local_only = force == "local"

        if force == "external":
            if self.external.available:
                self.active_backend = LLMBackend.EXTERNAL
                logger.info("[ROUTER] Forced external backend")
            else:
                logger.error("[ROUTER] External forced but no API key!")
                self.active_backend = LLMBackend.MOCK
            return self.active_backend

        # Try local first (unless forced external)
        if force in ("auto", "local"):
            requested_model = local_kwargs.get("model_name") or os.getenv(
                "HF_MODEL_NAME", "Qwen/Qwen2.5-1.5B-Instruct"
            )
            if self.local.loaded and self.local.model_name == requested_model:
                self.active_backend = LLMBackend.LOCAL
                return self.active_backend
            if self.local.load(**local_kwargs):
                self.active_backend = LLMBackend.LOCAL
                logger.info("[ROUTER] Using LOCAL backend")
                return self.active_backend
            else:
                logger.warning(f"[ROUTER] Local load failed: {self.local.load_error}")

        # Fallback to external
        if force != "local" and self.external.available:
            self.active_backend = LLMBackend.EXTERNAL
            logger.info("[ROUTER] Falling back to EXTERNAL backend")
            return self.active_backend

        # Neither worked
        if force == "local":
            logger.error("[ROUTER] Local model forced but failed to load!")
        else:
            logger.warning("[ROUTER] No backend available — running in MOCK mode")

        self.active_backend = LLMBackend.MOCK
        return self.active_backend

    # ------------------------------------------------------------------
    async def generate(self, prompt: str, max_tokens: int = 1024) -> tuple[str, str, str | None]:
        """
        Generate a response as (text, backend_used, error).
        Auto mode falls back from local to external; forced-local mode never does.
        """
        self.request_count += 1

        errors = []

        # 1. Try local
        if self.active_backend == LLMBackend.LOCAL and self.local.loaded:
            try:
                text = self.local.generate(prompt, max_new_tokens=max_tokens)
                if not text:
                    raise RuntimeError("Local model returned an empty response")
                self.local_count += 1
                return text, f"local:{self.local.model_name}", None
            except Exception as e:
                logger.error(f"[ROUTER] Local inference failed: {e}")
                errors.append(f"Local model failed: {_backend_error_message(e)}")
                # Auto mode may try the external backend for this request.

        if self.local_only:
            self.error_count += 1
            error = "; ".join(errors) or self.local.load_error or "Local model is not loaded"
            return "", "mock", error

        # 2. Try external
        if self.external.available:
            try:
                text = await self.external.generate(prompt, max_tokens=max_tokens)
                self.external_count += 1
                return text, f"external:{self.external.model_name}", None
            except Exception as e:
                details = _backend_error_message(e)
                logger.error(f"[ROUTER] External API failed: {details}")
                errors.append(f"External API failed: {details}")
        else:
            errors.append("External API key is not configured")

        # 3. Mock fallback
        self.error_count += 1
        return "", "mock", "; ".join(errors) or "No AI backend is available"


# ═══════════════════════════════════════════════════════════════════════════
# Prompt builder
# ═══════════════════════════════════════════════════════════════════════════
def build_task_prompt(request: AIRequest) -> str:
    """Build a structured prompt from the AIRequest fields."""
    msg_type = str(request.message_type)
    # Strip enum class prefix: "AIMessageType.DJ_DECISION" → "DJ_DECISION"
    if hasattr(request.message_type, "value"):
        msg_type = request.message_type.value
    elif "." in msg_type:
        msg_type = msg_type.rsplit(".", 1)[-1]

    sections = [f"## Task: {msg_type}"]

    # Event context
    ctx_parts = []
    if request.event_type:
        ctx_parts.append(f"Event type: {request.event_type}")
    if request.event_progress is not None:
        ctx_parts.append(f"Progress: {request.event_progress:.0%}")
    if request.current_energy is not None:
        ctx_parts.append(f"Current energy: {request.current_energy:.2f}")
    if request.target_energy is not None:
        ctx_parts.append(f"Target energy: {request.target_energy:.2f}")
    if request.current_vibe:
        ctx_parts.append(f"Current vibe: {request.current_vibe}")
    if request.recent_genres:
        ctx_parts.append(f"Recent genres: {', '.join(request.recent_genres[:8])}")
    if request.recent_artists:
        ctx_parts.append(f"Recent artists: {', '.join(request.recent_artists[:5])}")
    if request.allowed_languages:
        ctx_parts.append(f"Allowed languages: {', '.join(request.allowed_languages)}")
    if request.audience_age_range:
        ctx_parts.append(f"Audience age: {request.audience_age_range}")
    if ctx_parts:
        sections.append("### Event Context\n" + "\n".join(ctx_parts))

    # Candidates
    if request.candidate_songs:
        cand_lines = []
        for c in request.candidate_songs[:20]:
            cand_lines.append(
                f"  - ID: {c.get('song_id', c.get('id', '?'))} | "
                f"{c.get('title', '?')} — {c.get('artist', '?')} | "
                f"genre={c.get('genre', '?')} energy={c.get('energy', '?')} "
                f"bpm={c.get('bpm', '?')}"
            )
        sections.append("### Candidate Songs\n" + "\n".join(cand_lines))

    # Request data
    if request.request_data:
        sections.append(f"### Song Request Data\n{json.dumps(request.request_data, default=str)}")

    # Queue
    if request.queue_data:
        q_lines = [
            f"  [{q.get('position', i)}] {q.get('song_title', q.get('song_id', '?'))} "
            f"({q.get('lock_status', '?')}) score={q.get('final_score', '?')}"
            for i, q in enumerate(request.queue_data)
        ]
        sections.append("### Current Queue\n" + "\n".join(q_lines))

    # Lyrics
    if request.lyrics_data:
        sections.append(f"### Lyrics / Content Data\n{json.dumps(request.lyrics_data, default=str)}")

    # Custom instructions
    if request.custom_instructions:
        sections.append(f"### DJ Custom Instructions\n{request.custom_instructions}")

    # Task-specific instructions
    task_instr = _task_instructions(msg_type)
    if task_instr:
        sections.append(f"### Expected Response Format\n{task_instr}")

    return "\n\n".join(sections)


def _task_instructions(msg_type: str) -> str:
    instructions = {
        "DJ_DECISION": (
            'Return JSON: {"recommended_song_ids": [...], "reason": "...", '
            '"confidence": 0.0-1.0, "decision": "SELECT"}'
        ),
        "VIBE_UPDATE": (
            'Return JSON: {"recommended_vibe": {"energy": 0-1, "danceability": 0-1, '
            '"happiness": 0-1, "intensity": 0-1, "romance": 0-1}, '
            '"preferred_genres": [...], "preferred_languages": [...], '
            '"reason": "...", "confidence": 0-1}'
        ),
        "REQUEST_DECISION": (
            'Return JSON: {"request_decision": "ACCEPT_NOW|QUEUE|DEFER|BRIDGE|REJECT", '
            '"reason": "...", "confidence": 0-1, '
            '"bridge_strategy": [...] (if BRIDGE), "recommended_position": int (if QUEUE)}'
        ),
        "QUEUE_REVIEW": (
            'Return JSON: {"queue_approved": true/false, '
            '"queue_changes": [{"action": "swap|remove|insert", '
            '"position": int, "song_id": "..."}], "reason": "..."}'
        ),
        "LYRIC_ANALYSIS": (
            'Return JSON: {"lyrics_analysis": {"language": "...", '
            '"themes": [...], "sentiment": 0-1, "mood": "...", '
            '"celebration": 0-1, "romance": 0-1, "sadness": 0-1, '
            '"family_friendly": true/false, "explicit_content": true/false}}'
        ),
        "EVENT_SUMMARY": (
            'Return JSON: {"event_summary": {"overall_quality": 0-10, '
            '"highlights": [...], "improvements": [...], '
            '"crowd_favorites_pattern": "..."}}'
        ),
        "TRANSITION_REVIEW": (
            'Return JSON: {"queue_approved": true/false, '
            '"queue_changes": [...], "reason": "..."}'
        ),
    }
    return instructions.get(msg_type, instructions["DJ_DECISION"])


# ═══════════════════════════════════════════════════════════════════════════
# Response parser — extract JSON from LLM output
# ═══════════════════════════════════════════════════════════════════════════
def parse_llm_json(raw: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from LLM output."""
    if not raw:
        return {}

    # 1. Try direct parse
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"raw_output": raw[:500]}
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = cleaned.strip().rstrip("`")
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {"raw_output": raw[:500]}
    except json.JSONDecodeError:
        pass

    # 3. Find first { ... } block
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            parsed = json.loads(match.group())
            return parsed if isinstance(parsed, dict) else {"raw_output": raw[:500]}
        except json.JSONDecodeError:
            pass

    logger.warning(f"[PARSER] Could not parse JSON from LLM output (len={len(raw)})")
    return {"raw_output": raw[:500]}


# ═══════════════════════════════════════════════════════════════════════════
# Mock response generator (when neither backend is available)
# ═══════════════════════════════════════════════════════════════════════════
def mock_response(msg_type: str, request: AIRequest) -> dict[str, Any]:
    """Deterministic fallback responses."""
    if msg_type in ("VIBE_UPDATE",):
        return {
            "recommended_vibe": {"energy": 0.8, "danceability": 0.85, "happiness": 0.7,
                                 "intensity": 0.6, "romance": 0.2},
            "preferred_genres": ["Bollywood", "Punjabi Pop"],
            "reason": "Mock: maintaining party energy",
            "confidence": 0.5,
        }
    if msg_type in ("REQUEST_DECISION",):
        return {
            "request_decision": "QUEUE",
            "reason": "Mock: queuing request for review",
            "confidence": 0.5,
        }
    if msg_type in ("LYRIC_ANALYSIS",):
        return {
            "lyrics_analysis": {
                "language": "unknown", "themes": [], "sentiment": 0.5,
                "mood": "neutral", "family_friendly": True,
            }
        }
    if msg_type in ("QUEUE_REVIEW", "TRANSITION_REVIEW"):
        return {"queue_approved": True, "queue_changes": [], "reason": "Mock: approved"}

    # DJ_DECISION / generic
    candidate_ids = [c.get("song_id", c.get("id", "")) for c in request.candidate_songs[:5]]
    return {
        "recommended_song_ids": candidate_ids,
        "decision": "SELECT",
        "reason": "Mock: returning candidates in order",
        "confidence": 0.5,
    }


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI application
# ═══════════════════════════════════════════════════════════════════════════
START_TIME = time.time()
router = InferenceRouter()


app = FastAPI(
    title="AI DJ Model Server",
    description="Dual-backend LLM server (Local HF + OpenRouter fallback)",
    version="2.0.0",
)

@app.on_event("startup")
async def initialize_backend() -> None:
    """Initialize the configured backend when the API process starts."""
    configured_backend = os.getenv("LLM_BACKEND", "auto").lower()
    active_backend = router.initialize(
        force_backend=configured_backend,
        model_name=os.getenv("HF_MODEL_NAME", "Qwen/Qwen2.5-1.5B-Instruct"),
        dtype=os.getenv("HF_DTYPE", "float16"),
    )
    if configured_backend == "local" and active_backend != LLMBackend.LOCAL:
        raise RuntimeError(
            "LLM_BACKEND=local was required, but the local model failed to initialize: "
            f"{router.local.load_error or 'unknown loading error'}"
        )


class HealthResponse(BaseModel):
    status: str
    active_backend: str
    model_name: str
    uptime: float
    stats: dict[str, int]


class BackendSwitchRequest(BaseModel):
    backend: str = "auto"
    model_name: str = ""
    dtype: str = "float16"


class BackendSwitchResponse(BaseModel):
    success: bool
    active_backend: str
    message: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health_check():
    model_name = ""
    if router.active_backend == LLMBackend.LOCAL:
        model_name = router.local.model_name
    elif router.active_backend == LLMBackend.EXTERNAL:
        model_name = router.external.model_name

    return HealthResponse(
        status="ok" if router.active_backend != LLMBackend.MOCK else "degraded",
        active_backend=router.active_backend.value,
        model_name=model_name,
        uptime=time.time() - START_TIME,
        stats={
            "total_requests": router.request_count,
            "local_requests": router.local_count,
            "external_requests": router.external_count,
            "errors": router.error_count,
        },
    )


@app.post("/v1/backend/switch", response_model=BackendSwitchResponse)
async def switch_backend(req: BackendSwitchRequest):
    """Hot-switch between local/external backends."""
    kwargs = {}
    if req.model_name:
        kwargs["model_name"] = req.model_name
    if req.dtype:
        kwargs["dtype"] = req.dtype

    result = router.initialize(force_backend=req.backend, **kwargs)
    return BackendSwitchResponse(
        success=result != LLMBackend.MOCK,
        active_backend=result.value,
        message="Backend initialized" if result != LLMBackend.MOCK else "No AI backend is available",
    )


@app.post("/v1/ai/decide", response_model=AIResponse)
async def ai_decide(request: AIRequest):
    """Main AI decision endpoint — routes to the active backend."""
    start = time.time()

    msg_type = (
        request.message_type.value
        if hasattr(request.message_type, "value")
        else str(request.message_type)
    )

    # Build prompt
    prompt = build_task_prompt(request)

    # Generate
    raw_text, backend_used, inference_error = await router.generate(prompt)
    latency_ms = (time.time() - start) * 1000

    # Parse
    response_error = inference_error
    if raw_text:
        parsed = parse_llm_json(raw_text)
        if "raw_output" in parsed:
            parsed = mock_response(msg_type, request)
            backend_used = "mock"
            response_error = "AI model returned invalid JSON"
    else:
        parsed = mock_response(msg_type, request)

    candidate_ids = {
        str(candidate.get("song_id", candidate.get("id")))
        for candidate in request.candidate_songs
        if candidate.get("song_id", candidate.get("id")) is not None
    }
    recommended_song_ids = [
        str(song_id)
        for song_id in parsed.get("recommended_song_ids", [])
        if str(song_id) in candidate_ids
    ]
    logger.info(
        f"[{backend_used}] {msg_type} -> {list(parsed.keys())[:5]}  ({latency_ms:.0f}ms)"
    )

    # Map parsed fields → AIResponse
    return AIResponse(
        request_id=request.request_id or "",
        message_type=msg_type,
        success=backend_used != "mock",
        error=response_error,
        decision=parsed.get("decision"),
        reason=parsed.get("reason", ""),
        confidence=float(parsed.get("confidence", 0.0)),
        recommended_vibe=parsed.get("recommended_vibe"),
        recommended_energy=parsed.get("recommended_energy"),
        preferred_genres=parsed.get("preferred_genres", []),
        preferred_languages=parsed.get("preferred_languages", []),
        preferred_artists=parsed.get("preferred_artists", []),
        avoid_genres=parsed.get("avoid_genres", []),
        avoid_artists=parsed.get("avoid_artists", []),
        recommended_song_ids=recommended_song_ids,
        rejected_song_ids=parsed.get("rejected_song_ids", []),
        request_decision=parsed.get("request_decision"),
        bridge_strategy=parsed.get("bridge_strategy"),
        recommended_position=parsed.get("recommended_position"),
        lyrics_analysis=parsed.get("lyrics_analysis", {}),
        queue_approved=parsed.get("queue_approved", True),
        queue_changes=parsed.get("queue_changes", []),
        event_summary=parsed.get("event_summary", {}),
        model_name=backend_used,
        latency_ms=latency_ms,
    )


# Convenience aliases — delegate to the main endpoint
@app.post("/v1/ai/request")
async def ai_request(request: AIRequest):
    if hasattr(request, "message_type"):
        request.message_type = "REQUEST_DECISION"
    return await ai_decide(request)


@app.post("/v1/ai/vibe")
async def ai_vibe(request: AIRequest):
    if hasattr(request, "message_type"):
        request.message_type = "VIBE_UPDATE"
    return await ai_decide(request)


@app.post("/v1/ai/lyrics")
async def ai_lyrics(request: AIRequest):
    if hasattr(request, "message_type"):
        request.message_type = "LYRIC_ANALYSIS"
    return await ai_decide(request)


@app.post("/v1/ai/review-queue")
async def ai_review_queue(request: AIRequest):
    if hasattr(request, "message_type"):
        request.message_type = "QUEUE_REVIEW"
    return await ai_decide(request)


@app.post("/v1/ai/event-summary")
async def ai_event_summary(request: AIRequest):
    if hasattr(request, "message_type"):
        request.message_type = "EVENT_SUMMARY"
    return await ai_decide(request)


# ═══════════════════════════════════════════════════════════════════════════
# Standalone runner (for Colab: `!python app/api/model_server.py`)
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")
