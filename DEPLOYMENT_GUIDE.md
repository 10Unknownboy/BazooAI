# 🎧 AI DJ System — Full Deployment & Setup Guide

This guide walks you through setting up the AI DJ system for a "real-world" deployment. The architecture is split into two parts to maximize performance and minimize cost:
1. **The Remote AI Brain (Google Colab):** Runs the heavy language models (LLMs) on free GPUs.
2. **The Local DJ Orchestrator:** Runs locally on your machine to manage state, scoring, audio playback, and policies with zero latency.

---

## Phase 1: Set up the Remote AI Brain (Google Colab)

To avoid frying your local computer, we offload the heavy AI thinking to Google Colab.

1. **Prepare your accounts:**
   * Get a free [ngrok auth token](https://dashboard.ngrok.com/get-started/your-authtoken) (exposes the Colab server to your local machine).
   * Get a free [OpenRouter API key](https://openrouter.ai/keys) (serves as a fallback if the Colab GPU runs out of memory).

2. **Launch the Notebook:**
   * Upload `notebooks/ai_dj_colab_server.ipynb` to Google Colab.
   * Go to **Runtime → Change runtime type** and select **T4 GPU**.

3. **Configure Secrets:**
   * Click the 🔑 **Secrets** icon on the left sidebar in Colab.
   * Add the following secrets:
     * `NGROK_AUTH_TOKEN` : Your ngrok token
     * `OPENROUTER_API_KEY` : Your OpenRouter key
     * `LLM_BACKEND` : `auto` (Tries local GPU first, falls back to OpenRouter)
     * `HF_MODEL_NAME` : `google/gemma-2-2b-it` (Or `TinyLlama/TinyLlama-1.1B-Chat-v1.0` for speed)

4. **Run the Server:**
   * Press **Runtime → Run all** (Ctrl+F9).
   * Scroll down to the "Start the FastAPI Server" cell.
   * You will see a green success message with a **PUBLIC URL** (e.g., `https://abc-123.ngrok-free.app`). **Copy this URL.**
   * *Leave this browser tab open while your DJ event runs.*

---

## Phase 2: Set up the Local DJ Orchestrator

This runs on your laptop/PC at the actual event venue.

1. **Clone & Install:**
   Open your terminal (Command Prompt/PowerShell on Windows, Terminal on Mac/Linux):
   ```bash
   git clone https://github.com/10Unknownboy/BazooAI.git
   cd BazooAI/ai_dj_system
   
   # Create and activate virtual environment
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Mac/Linux:
   source .venv/bin/activate
   
   # Install the project and dependencies
   pip install -e .
   ```

2. **Configure your Local Environment:**
   Copy the example config file:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and configure the essential settings:
   ```env
   # Paste the ngrok URL you copied from Colab:
   AI_MODEL_URL=https://abc-123.ngrok-free.app
   
   # Set to 'false' for production, 'true' for testing
   DRY_RUN=false
   
   # Set to your email for MusicBrainz rate-limiting
   MUSICBRAINZ_USER_AGENT=AIDJSystem/1.0 (your-email@example.com)
   ```

3. **Configure Event Policies & Scoring:**
   * Edit `config/policy.yaml` to set hard rules (e.g., block explicit content, restrict genres).
   * Edit `config/scoring_weights.yaml` to adjust how the deterministic engine scores songs (e.g., prioritize energy vs. crowd feedback).
   * Edit `config/event_example.yaml` to define your specific event (e.g., College Party, Wedding).

---

## Phase 3: Run the Event (Deployment)

The system features three distinct consoles. You can run them in separate terminal windows for a professional setup.

**1. The Main Dashboard (The UI)**
This is what you monitor during the event. It shows the Now Playing track, the 5-song lookahead queue, energy levels, and agent statuses.
```bash
python -m app --dashboard --dry-run
```
*(Remove `--dry-run` when you have real audio files integrated).*

**2. The Debug Console (Under the hood)**
Open a second terminal, activate the venv, and run the debug view to see exact AI reasoning, policy rejections, and exact score calculations in real-time.
```bash
python -m app --debug
```

**3. Interactive Commands**
At the bottom of the Main Dashboard, you can type live commands during the event to steer the AI without interrupting playback:
* `vibe hype` — Tells the AI to smoothly transition to high-energy tracks.
* `request "Brown Munde"` — Simulates a crowd request. The AI decides whether to accept, queue, defer, or reject based on the current vibe.
* `energy +10` — Bumps the target energy up.
* `why` — Asks the system to explain *exactly* why it chose the next song in the queue (shows score breakdown and AI reasoning).

---

## Phase 4: Making it "Production Ready" (Next Steps)

The current architecture is production-ready for decision-making, but requires a few final integrations for a real-world physical event:

1. **Audio Playback Integration:**
   Currently, the system uses `MockMusicProvider` to simulate playback. To play real audio:
   * Populate a folder with `.mp3`/`.wav` files.
   * Update `app/providers/local_file_provider.py` to use a Python audio library (like `pygame` or `pydub`) to physically output sound to your speakers.

2. **Resilience & Fallbacks (Already Implemented!):**
   * **Colab Disconnects?** If the internet drops or Colab times out, the `FallbackManager` automatically takes over. The system seamlessly switches to a 100% deterministic local mode. The music *never* stops.
   * **Database:** The local `ai_dj.db` uses SQLite with WAL (Write-Ahead Logging) mode, which is highly robust for local deployments and prevents corruption during crashes.

3. **Persistent Learning:**
   Every event generates a summary in your `data/` folder. The system learns which transitions worked and which didn't, permanently updating its weights for future events.
