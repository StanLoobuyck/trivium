#!/usr/bin/env bash
# Install Verbatim (the lecture transcriber) for the current user. Never uses sudo:
# missing system packages are printed as one pacman command to run yourself.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/lecture-transcriber"

missing=()
command -v ffmpeg >/dev/null || missing+=(ffmpeg)
command -v uv >/dev/null || missing+=(uv)
command -v notify-send >/dev/null || missing+=(libnotify)
if ((${#missing[@]})); then
    echo "Missing system packages. Run this, then rerun scripts/install.sh:"
    echo "    sudo pacman -S --needed ${missing[*]}"
    exit 1
fi

cd "$REPO"
uv python pin 3.12
uv sync --extra local
# Puts `lecture` in ~/.local/bin; --editable so code changes apply without reinstalling.
# Extra "local": faster-whisper + CUDA libraries (wheels) for transcription on the NVIDIA GPU.
uv tool install --editable '.[local]' --force --python 3.12

# Launcher (DMS / app menu) and the worker's systemd user unit. Enabling the service is left to you:
#   systemctl --user enable --now lecture-worker.service
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
mkdir -p "$APPS_DIR" "$UNIT_DIR" "$ICON_DIR"
install -m 644 packaging/verbatim.svg "$ICON_DIR/verbatim.svg"
sed "s|@LECTURE@|$HOME/.local/bin/lecture|" packaging/lecture.desktop > "$APPS_DIR/lecture.desktop"
install -m 644 packaging/lecture-worker.service "$UNIT_DIR/lecture-worker.service"

# The latex-notes skill lives in this repo; Claude Code finds it through a link.
SKILLS_DIR="$HOME/.claude/skills"
mkdir -p "$SKILLS_DIR"
if [[ -L "$SKILLS_DIR/latex-notes" || ! -e "$SKILLS_DIR/latex-notes" ]]; then
    ln -sfn "$REPO/skill/latex-notes" "$SKILLS_DIR/latex-notes"
else
    echo "Note: $SKILLS_DIR/latex-notes is a folder, not a link to the repo; left as it is."
fi

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
if [[ ! -f "$CONFIG_DIR/.env" ]]; then
    install -m 600 .env.example "$CONFIG_DIR/.env"
    echo "Created $CONFIG_DIR/.env — paste your API keys there."
else
    chmod 600 "$CONFIG_DIR/.env"
fi

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "Note: ~/.local/bin is not on your PATH; add it to ~/.bashrc." ;;
esac

echo "Done. Next: lecture doctor"
echo "Background worker (once): systemctl --user daemon-reload && systemctl --user enable --now lecture-worker.service"
