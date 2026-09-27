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
- SQLite is used for development (automatically created in `.data/db.sqlite`).
- PostgreSQL support is planned for production.

## Environment Variables
Copy `.env.example` to `.env` and fill in the values:
- `AI_MODEL_URL`
- `MUSICBRAINZ_USER_AGENT`

## Running the System
```powershell
# Dashboard
python -m app --dashboard

# Debug Console
python -m app --debug

# API Server
python -m app --api

# Dry Run Simulation
python -m app --dry-run

# High-speed simulation
python -m app --simulate --speed 10
```

## Colab Model Server
1. Upload `model_server.py` to Colab
2. Run it and expose via ngrok or localtunnel
3. Update `.env` with the URL

## Manual Live AI Check
Configure `OPENROUTER_API_KEY` in `.env` and set `OPENROUTER_MODEL` to a model available to your account (the default is OpenRouter's free-model router, `openrouter/free`). Start the real model API in one terminal:
```powershell
python -m app --model-server
```

Then send one live decision request from another terminal:
```powershell
python scripts/model_probe.py --url http://127.0.0.1:8000
```
The probe fails if the server is using the deterministic mock backend, returns invalid candidate IDs, or cannot reach a real model. Free-provider capacity can be rate-limited; the model server reports that failure instead of presenting mock output as a successful AI decision.

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
Drop `.mp3` files in the `music/` directory. Metadata and audio features will be automatically analyzed.

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
