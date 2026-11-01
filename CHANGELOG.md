# Changelog

## ▶ Start here (volgende sessie)
1. Oriëntatie: `CLAUDE.md` (laadt vanzelf). Daarna `npm test`; `npm run build && npm run test:e2e` voor schermen.
2. **Nu:** fase 0 af: getest op iPhone en laptop, stijl A goedgekeurd (kleine aanpassingen later mogelijk). Publieke
   repo `studie-ecosysteem`, MIT, commits met het noreply-adres (alleen in deze repo ingesteld). `PLAN.md` blijft
   lokaal (geen back-up via GitHub).
3. **Volgende:** fase 1 (Inhaal-MVP). Daarvoor is een nieuwe rooster-export vanaf de
   semesterstart nodig: daarmee controleren we ook of de `UID`s stabiel blijven (zie CONTRACT.md).
4. **Open:** domein voor de tunnel (fase 2), overkoepelende naam en definitief adres (fase 6).

## 2026-11-01 — fase 0: monorepo en stijl A
- Monorepo met npm-werkruimtes, `CLAUDE.md`, Inhaal-schil, landingspagina, CI met Pages-deploy.
- `packages/design`: tokens, componenten, iconen en voorbeeldpagina (`packages/design/index.html`, live op
  `/design/`). Tests rekenen het contrast na in licht en donker.
- `packages/contract`: vakcodes, sessie-id's, events + JSON Schema met tests.
- Afwijkingen van het plan, door de contrasteis van 4,5:1: accent `#0066D6` i.p.v. `#007AFF` (dat haalt 4,0:1),
  accenttekst `#0058BA` / `#409CFF`, secundaire tekst `#5E5E63` / `#A5A5AC`. Vakkleuren zijn donkerder in licht en
  lichter in donker, en halen 3:1 als grafisch element. Het hero-getal is 56 px: het plan gaf geen maat.
- `CONTRACT.md` maakt vakcodes hoofdletterongevoelig: het rooster schrijft `H01L1a`, Toledo `[H01L1A]`.
- De spring is uitgerekend (stijfheid 400, demping 30, ζ = 0,75, overshoot 2,8%) en geschaald naar 300 ms.
- De WebKit-binary van Playwright draait niet op Arch (Ubuntu-bibliotheken ontbreken). Lokaal: Chromium op
  iPhone-formaat en Chromium + Firefox op 1440 px. WebKit draait alleen in CI.
- `npm audit`: 10 meldingen (low/moderate), allemaal in build-afhankelijkheden van vite-plugin-pwa; niets daarvan
  komt in de app.
