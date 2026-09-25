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
python -m venv .venv
.venv\Scripts\activate
pip install -e .[all]
```

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

## Commands
* `play` - Start playback
* `pause` - Pause playback
* `skip` - Skip current song
* `queue` - View queue
* `request <song>` - Request a song

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
