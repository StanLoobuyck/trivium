#!/usr/bin/env bash
# Zet de hub en de Inhaal-build op de Mac. Installeert niets in het systeem: de LaunchDaemon apart, met toestemming.
set -euo pipefail
cd "$(dirname "$0")/.."
npm run build
rsync -az --delete --exclude .venv --exclude .env --exclude '*.sqlite*' --exclude hub.log --exclude tests \
  --exclude web apps/hub/ mac:inhaal-hub/
rsync -az --delete apps/inhaal/dist/ mac:inhaal-hub/web/
ssh mac 'cd ~/inhaal-hub && PATH=/opt/homebrew/bin:$PATH uv sync -q --no-dev'
