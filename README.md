# AI DJ System

## Architecture
This AI DJ System is designed with a three-layer architecture to separate AI reasoning from real-time execution.

1. **AI Reasoning Layer**: Recommends songs, handles dynamic requests, generates strategies (LLM-based)
2. **DJ Decision Engine**: Deterministic policy and scoring system that ranks candidates and manages the queue
3. **Music Playback**: Connects to the physical or simulated playback provider

## Installation
For Windows users, use PowerShell:
```powershell
git clone https://github.com/10Unknownboy/BazooAI
cd ai_dj_system
py -3.14 --version
py -3.14 -m venv .venv
.venv\Scripts\activate
pip install -e .[all]
```
Use Python 3.14.7 for the project-local `.venv`.

## Database Setup
- SQLite in WAL mode is used for development (automatically created at `data/ai_dj.db`).
- The repository layer uses SQLAlchemy and remains portable for a future PostgreSQL migration.

## Environment Variables
Copy `.env.example` to `.env` and fill in the values:
- `AI_MODEL_URL`
- `MUSICBRAINZ_USER_AGENT`

## Running the System
```powershell
# Streamlit UI (Dashboard, Debug, and API consoles)
streamlit run app/ui/streamlit_app.py

# Dashboard
python -m app --dashboard

# Debug Console
python -m app --debug

# API Console
python -m app --api

# Dashboard, Debug, and API views together in one shared runtime
python -m app --all

# Dry Run Simulation
python -m app --dry-run

# Simulation mode
python -m app --simulate
```

## Colab Model Server
1. Set the Colab runtime to a GPU and add `NGROK_AUTH_TOKEN` to Colab Secrets.
2. Run `notebooks/ai_dj_colab_server.ipynb`. It downloads the public
   `Qwen/Qwen2.5-1.5B-Instruct` model and requires a successful local inference smoke test;
   it does not fall back to OpenRouter or mock responses.
   The notebook clones the repository; ensure your latest project changes are pushed to the
   branch configured in its repository cell.
3. Set the printed ngrok URL as `AI_MODEL_URL` in the local `.env` and restart Streamlit.
   Keep the Colab runtime running while using the DJ.

## Manual Live AI Check
After the Colab server is running and `AI_MODEL_URL` points to its ngrok URL, send a real
structured decision request from the local project:
```powershell
python scripts/model_probe.py
```
The probe fails unless the remote server is using the local Hugging Face model, returns valid
candidate IDs, and responds to a real inference request.

The Streamlit **API Console** also has a **Run live AI decision check** button. Playback
candidates are restricted to existing local files, at least 30 seconds long by default, and
exclude configurable sound-effect terms in `config/scoring_weights.yaml`.

## Metadata and Live Diagnostics
- In the Streamlit sidebar, select **Fetch MusicBrainz metadata + LRCLIB lyrics** to enrich
  the indexed local library in the background. MusicBrainz requests use
  `MUSICBRAINZ_USER_AGENT` and are rate-limited; metadata and lyrics responses/analysis are
  cached in SQLite. The enrichment job does not block playback.
- The dashboard and five-song queue refresh automatically while the page is open.
- The Colab model server exposes `GET /log?limit=100` for a bounded, redacted tail of recent
  model-server logs (`limit` is restricted to 1–500).
- Manual vibe and energy settings stay in effect until the next event starts. Genre, artist,
  and language preferences contribute to deterministic candidate generation and scoring;
  only reconsiderable queue slots are replaced after a manual change.

## Commands
* `play` - Start playback
* `pause` - Pause playback
* `skip` - Skip current song
* `queue` - View queue
* `request <song>` - Request a song
* `vibe <preset>` - Change the active event vibe
* `energy <value>` - Set target energy from 0-100; use `+N` or `-N` for a relative change

## Creating Events
Use the config file to create events:
```powershell
python -m app --event config/event_example.yaml
```

## Handling Requests
Requests go through a lifecycle: Requested -> Evaluated -> Queued / Deferred / Rejected. The AI may generate a "Bridge Strategy" to transition from the current vibe to the requested song's vibe smoothly.

## Feedback
Submit feedback to train the contextual preference model:
- Simple: `feedback 9`
- Rich: `feedback 9 10 9 8 10`

## Why Command
Use `why <song_id>` to see the exact scoring components and policy evaluations that led to a decision.

## Adding Music
Set `LOCAL_MUSIC_DIR` in `.env` to the music folder (relative paths are resolved from the
project root; for example, `LOCAL_MUSIC_DIR=./music` or `LOCAL_MUSIC_DIR=C:/Users/You/Music`).
If unset, the app uses the project's `music/` directory. Put `.mp3`, `.wav`, `.flac`, or `.ogg`
files in that folder, start/restart Streamlit, then use **Refresh local music library**.
The refresh indexes file metadata in SQLite; audio analysis uses librosa when
installed and enabled, and falls back to metadata-only operation when unavailable. An event
cannot start without indexed tracks. Local playback requires a working
`pygame` audio mixer and an available output device; when the mixer cannot initialize, Streamlit
reports that audio output is unavailable.

## Streamlit Manual Check
1. Start the UI with `streamlit run app/ui/streamlit_app.py`.
2. Refresh the local library and confirm the expected track count.
3. Start an event, verify the five-song lookahead and debug/API activity tabs, then use play,
   pause, resume, skip, request, feedback, and stop controls.
4. Playback and event-state updates are reflected after a Streamlit rerun/page refresh.

Playback is rendered through `pygame` on the machine running Streamlit. That means a locally
running app plays through that computer's speakers/headphones, not the phone scanning the QR.
The guest page is a request-only view. To let guests connect, keep their phones on the same LAN,
allow inbound TCP on port `8003` in the host firewall, and use the LAN URL shown with the QR.
For guests outside the LAN, configure `GUEST_PUBLIC_URL` to a public HTTPS tunnel that forwards
to port `8003`. Never expose the request service on an untrusted network without appropriate
network protections.

The event bus and runtime state are in-process. Launching separate console/API processes does not
make them share live state; use the Streamlit UI as the integrated local console. A production
multi-process deployment needs a shared runtime transport and deployment-specific process
configuration.

## Audio Analysis
Uses `librosa` for BPM, energy, and key detection. Results are cached in the database.

## Running Tests
```powershell
pytest tests/ -v
```

## Project Structure
- `app/` - Core application code
  - `learning/` - Reinforcement learning and preferences
  - `simulation/` - Mock interfaces for testing
  - `decision/` - Scoring and policies
- `tests/` - Pytest test suites
- `config/` - YAML configuration files

## Configuration
See `config/policy.yaml` and `config/scoring_weights.yaml` to adjust the engine's behavior.
