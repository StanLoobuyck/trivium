# lecture-models: the model server on the Mac at home

Design: `PLAN.md` section 4b. The laptop's app sends audio chunks here over Tailscale; this server runs
Whisper (mlx-whisper on the M1 Max GPU) and answers in Groq's `verbose_json` shape.

## Files
- `server.py`: FastAPI server, `GET /health`, `POST /v1/audio/transcriptions`, `POST /v1/llm/chat` (passes an
  Ollama /api/chat request to Ollama on this Mac; term fix suggestions) (bearer token).
- Ollama: `be.lecture.ollama.plist` LaunchDaemon (boot, no login; localhost:11434 only), see below. Models:
  qwen3.8:27b (used), gemma4:26b, gemma4:12b. The Homebrew build 0.40.6 has no structured output (`format` → 501).
- `.env` (on the Mac only, mode 600): `LECTURE_MAC_TOKEN`, `LECTURE_MAC_HOST` (Tailscale IP),
  `LECTURE_MAC_PORT` (7862), `LECTURE_MAC_MODEL` (large-v3), `LECTURE_MAC_WORKERS` (2: worker processes, each
  with its own model, ~4.2 GB; measured: 2 ≈ 1.5× throughput, 3–4 slower). The same token is in the laptop's
  `~/.config/lecture-transcriber/.env`.
- `be.lecture.models.plist`: LaunchDaemon (starts at boot without a login, runs as your own user; fill in __USER__ and __HOME__).
- `smoke.py`: speed test on one clip.

## Deploy (from the laptop, in the repo)
    rsync -a --exclude .venv --exclude .env --exclude logs mac/ mac:lecture-transcriber/
    ssh mac 'cd ~/lecture-transcriber && /opt/homebrew/bin/uv sync'
    ssh -t mac 'sudo launchctl kickstart -k system/be.lecture.models'      # restart

## Install the boot service (once, needs sudo on the Mac)
    ssh -t mac 'sudo cp ~/lecture-transcriber/be.lecture.models.plist /Library/LaunchDaemons/ &&
      sudo chown root:wheel /Library/LaunchDaemons/be.lecture.models.plist &&
      sudo launchctl bootstrap system /Library/LaunchDaemons/be.lecture.models.plist'

Status: `ssh mac 'launchctl print system/be.lecture.models | head -20'`; log: `~/lecture-transcriber/logs/server.log`.

## Ollama as a boot service (once, needs sudo; replaces brew's login-only agent)
    ssh -t mac '/opt/homebrew/bin/brew services stop ollama &&
      sudo cp ~/lecture-transcriber/be.lecture.ollama.plist /Library/LaunchDaemons/ &&
      sudo chown root:wheel /Library/LaunchDaemons/be.lecture.ollama.plist &&
      sudo launchctl bootstrap system /Library/LaunchDaemons/be.lecture.ollama.plist'

Status: `ssh mac 'launchctl print system/be.lecture.ollama | head -20'`; log: `~/lecture-transcriber/logs/ollama.log`.
