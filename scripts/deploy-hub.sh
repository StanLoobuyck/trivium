#!/usr/bin/env bash
# Zet de hub en de Sequo-build op de Mac. Installeert niets in het systeem: de LaunchDaemon apart, met toestemming.
set -euo pipefail
cd "$(dirname "$0")/.."
npm run build
rsync -az --delete --exclude .venv --exclude .env --exclude '*.sqlite*' --exclude hub.log --exclude tests \
  --exclude web --exclude /share --exclude /share-web apps/hub/ mac:trivium-hub/
rsync -az --delete apps/sequo/dist/ mac:trivium-hub/web/
# Verbatim delen: de pagina om te bekijken (share.html) met de stijl en teksten van Verbatim
rsync -az --delete --exclude '__pycache__' apps/verbatim/src/lecture/web/ mac:trivium-hub/share-web/
ssh mac 'cd ~/trivium-hub && PATH=/opt/homebrew/bin:$PATH uv sync -q --no-dev'
