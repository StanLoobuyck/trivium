"""Het rooster elk uur ophalen. Lezen doet de app zelf: er is maar één parser, in domain/rooster.js."""
import asyncio
import hashlib
import logging
from datetime import UTC, datetime

import httpx

from .store import Store

log = logging.getLogger("hub.rooster")
INTERVAL_S = 3600


def save_rooster(store: Store, text: str) -> bool:
    """Bewaart alleen een geldig rooster; een foutpagina mag het vorige niet overschrijven."""
    if not text.lstrip().startswith("BEGIN:VCALENDAR"):
        return False
    # DTSTAMP verandert bij elke export en zegt niets over de lessen.
    lines = [line for line in text.splitlines() if not line.startswith(("DTSTAMP", "LAST-MODIFIED"))]
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
    if digest != store.get_meta("rooster_hash"):
        store.set_meta("rooster_text", text)
        store.set_meta("rooster_hash", digest)
    store.set_meta("rooster_fetched_at", datetime.now(UTC).isoformat())
    return True


async def fetch_once(store: Store, url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        return save_rooster(store, response.text)
    except httpx.HTTPError as error:
        log.warning("rooster niet opgehaald: %s", type(error).__name__)
        return False


async def fetch_loop(store: Store, url: str) -> None:
    while True:
        await fetch_once(store, url)
        await asyncio.sleep(INTERVAL_S)
