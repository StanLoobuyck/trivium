# Hub

Sync tussen toestellen en het rooster ophalen. Draait op de eigen Mac; anderen gebruiken Inhaal zonder hub.

```bash
uv run pytest
HUB_CODE=<minstens 32 tekens> HUB_WEB=../inhaal/dist uv run uvicorn --factory hub.app:from_env --port 8788
```

Instellingen staan in `.env`, dat niet gecommit wordt: `HUB_CODE`, `HUB_DB`, `HUB_WEB`, `ROOSTER_URL`.
Bereikbaar via Tailscale Funnel. De pagina's zijn openbaar, de gegevens alleen met de koppelcode.
