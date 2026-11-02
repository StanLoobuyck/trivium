# Trivium — notities voor Claude Code

Monorepo met drie apps, elk apart te downloaden en te gebruiken: **Sequo** (technisch `inhaal`, nieuw: welke lessen moet ik
nog inhalen), **Velox** (technisch `swiftskip`, bestaat: Toledo-opnames kijkbaar en downloadbaar) en **Verbatim** (bestaat:
transcripts en notities). De eigenaar schrijft zelf geen code: Claude Code bouwt, draait en test alles; de
eigenaar test de app en beslist. Dit is een **publieke repo**: geen persoonlijke gegevens, adressen of
rooster in gecommitte bestanden. Persoonlijke setup hoort in `CLAUDE.local.md`. `PLAN.md` bevat persoonlijke
details en blijft lokaal; beide staan in `.gitignore`.

## Begin van een sessie
1. Lees `CHANGELOG.md` → "▶ Start here" en de nieuwste entry. Lees `PLAN.md` alleen voor de sectie die je
   nodig hebt.
2. `npm test` (offline). Vraag wat er moet gebeuren als dat niet al duidelijk is.

## Werkregels
- **Vraag eerst** vóór `sudo`, `pacman`, `yay`, `systemctl` en **alles op de Mac** (`ssh mac`, `brew`,
  `launchctl`, `pmset`). Python alleen via venv/uv.
- **Standaard commits en pushes naar `main` mogen zonder vragen** zodra de tests slagen (toestemming van de
  eigenaar, 2026-11-01). Vraag wel eerst bij force push, het herschrijven van geschiedenis, wijzigingen aan
  repo-instellingen en alles waarbij privégegevens online kunnen komen. Conventional commits.
- **Updates op de Mac mogen zonder vragen** met `scripts/deploy-hub.sh`, zodra de tests slagen (toestemming van de
  eigenaar, 2026-11-01). Voor `sudo`, `launchctl`, `brew`, `pmset`, Tailscale en al de rest op de Mac: wel vragen.
- **Geen Claude-vermelding in commits of PR's**: geen `Co-Authored-By`, `Claude-Session` of "Generated with".
  Dit gaat vóór de standaardinstelling van Claude Code.
- Bouw alleen de fase die aan de beurt is.
- Stop na elke fase met een korte checklist van wat de eigenaar op iPhone en laptop moet testen.
- Keuzes van de eigenaar (UI, features, namen): vraag ze één voor één, met opties en een aanbeveling.
- Na twee koerscorrecties op hetzelfde probleem: stop en vat samen wat je leerde.
- Houd `CHANGELOG.md` bij: nieuwste eerst, gemeten getallen, bovenaan "▶ Start here".
- Test elk scherm op iPhone-formaat (375 px) en 1440 px, licht en donker. Vertel wat je niet kon testen.
- Antwoord in de taal van de eigenaar (Nederlands of Engels).

Namen: Trivium is het geheel, Sequo en Velox zijn wat je ziet. Mappen, id's, opslag, repo- en update-adressen blijven `inhaal` en `swiftskip`, zodat installaties en koppelingen werken.

## Mapstructuur
```
apps/
  inhaal/     PWA: src/{domain,db,ui,screens,sync,i18n}, Vite-config
  hub/        (fase 2) Python FastAPI op de Mac: /sync, /rooster, /events; serveert ook de eigen Inhaal
  swiftskip/  (fase 3) verhuisd uit de SwiftSkip-repo, met geschiedenis
  verbatim/   (fase 4) verhuisd uit lecture-transcriber, met geschiedenis, incl. mac/ modelserver
packages/
  design/     tokens.css, components.css, icons.js — stijl A, zonder framework en zonder build
  contract/   CONTRACT.md + JSON Schema: vakcodes, sessie-id's, events
site/         GitHub Pages: landingspagina, downloads, SwiftSkip updates.json, Inhaal-build
.github/      CI per app; releases met prefix (inhaal-v1.0.0, swiftskip-v4.1.0, verbatim-v0.2.0)
fixtures/     private/ = echt rooster, nooit committen; tests gebruiken een geanonimiseerde kopie
```
Elke app blijft los te bouwen, testen en releasen; het enige wat ze delen is `packages/`.

## Stack
| Onderdeel | Keuze |
| --- | --- |
| Inhaal UI | Vanilla JS (ES-modules) + `packages/design`, kleine eigen componenten. Geen framework, geen Tailwind |
| Inhaal build | Vite, alleen voor bundelen en PWA (vite-plugin-pwa) |
| Opslag | Dexie.js op IndexedDB; local-first, UUID + `createdAt`/`updatedAt`/`deletedAt` op elk record |
| Datums | date-fns met `nl-BE` en `en-GB`; tijden in Europe/Brussels |
| Rooster | `ical.js` in `domain/rooster.js` |
| Talen | Eén JSON per taal (nl, en); elke tekst in beide talen |
| Tests | Vitest (domain, design) + Playwright (iPhone-viewport, WebKit) |
| Hosting | GitHub Pages (statisch); geen server voor anderen |
| Hub (fase 2) | Python 3.12 + FastAPI + SQLite met uv, als LaunchDaemon op de Mac, deploy met rsync |
| Toegang (fase 2) | Tailscale Funnel (gratis `*.ts.net`) met koppelcode per toestel; geen eigen domein, niets extra op de iPhone |

**Regel:** alle rekenlogica van Inhaal zit in `domain/` als pure, geteste functies zonder UI (herbruikbaar
voor een latere iOS-app). Afgeleide waarden (aantallen, `number`, tempo) worden altijd berekend, nooit
opgeslagen. De vakcode is de gedeelde sleutel tussen de drie apps; zie `packages/contract/CONTRACT.md`.

## Productprincipes
1. **Eén tik om af te vinken**, met undo-toast van 5 s, nooit een bevestigingsvenster.
2. **Niet typen, kiezen.** Datums komen uit het rooster of uit chips.
3. **Het getal is de held.** Bovenaan één groot getal: wat nog openstaat.
4. **Kalm, geen schuldgevoel.** Geen rode alarmen, streaks, punten of badges.
5. **Kleur betekent iets.** Grijs en wit voor de interface, één kleur per vak, geen decoratieve gradiënten.
6. **Direct, ook offline.** Elke actie lokaal en zichtbaar binnen 100 ms; sync op de achtergrond.
7. **Gsm eerst, laptop volwaardig.** Eén duim op de gsm; op de laptop rijkere lay-out met sneltoetsen.

Kwaliteitslat voor elke fase: geen layoutsprongen, elke tikactie voelt direct, werkt op 375 px én 1440 px,
en donker ziet er even goed uit als licht.

## Design (stijl A: native iOS)
Grijze achtergrond, witte gegroepeerde lijsten, één blauw accent, vakkleur alleen als stip of tint.
Componenten gebruiken **nooit losse waarden**, alleen tokens uit `packages/design/tokens.css`.

- **Type:** `-apple-system, "SF Pro Text"`, Inter als fallback. Altijd `tabular-nums`. Schaal 34 · 22 · 17 ·
  15 · 13 · 11 px, in rem (1 rem = 17 px) zodat de systeemtekstgrootte werkt. Gewicht 400/500/600; 700 alleen
  voor het hero-getal.
- **Kleur:** achtergrond `#F2F2F7` / `#000000`, kaarten `#FFFFFF` / `#1C1C1E`, scheidingslijn 0,5 px op 12%.
  Vakpalet van 8 (blauw, indigo, paars, roze, rood, oranje, geel, groen), telkens met `-tint`.
- **Ruimte:** 4, 8, 12, 16, 20, 24, 32, 48. **Radius:** 10 rij, 16 kaart, 22 sheet, rond voor chips.
  Rijhoogte ≥ 44 px. `env(safe-area-inset-*)` voor notch en home-indicator.
- **Beweging:** spring (stijfheid 400, demping 30), 200–300 ms; FLIP bij lijsten. Bij
  `prefers-reduced-motion` alleen fades.
- **Materiaal:** tab- en kopbalk `backdrop-filter: blur(20px)` op 80%. Licht: hoogstens `0 1px 2px` op 4%.
  Donker: geen schaduw.
- **Toegankelijkheid:** tekstcontrast ≥ 4,5:1, vakkleur nooit als enige drager, volledige
  toetsenbordbediening, zichtbare focusring.

## Fasen (details en acceptatiecriteria in `PLAN.md`)
0. Monorepo en stijl A
1. Inhaal-MVP (vervangt de Notes-lijst)
2. Hub op de Mac
3. SwiftSkip erbij
4. Verbatim erbij
5. Eén look
6. Publiek

## Valkuilen
- Proefrun van een SwiftSkip-release: `npm run release -- <versie> --dry-run`. Zonder `--` slikt npm de vlag en publiceert
  het echt.
- De hub herstart niet met `scripts/deploy-hub.sh`: nieuwe hubcode vraagt een herstart (proces stoppen volstaat, KeepAlive start het opnieuw).
- Verbatim draait op de laptop als geïnstalleerde tool: Python-wijzigingen vragen `apps/verbatim/scripts/install.sh` en een herstart van de
  worker (vraag eerst). Statische webbestanden gelden na herladen. Persoonlijke instellingen staan in `~/.config/lecture-transcriber/`.
- Vóór code in deze publieke repo komt: scannen op Mac-naam, IP, thuispaden, plaatsen, privémail en Claude-vermeldingen.
- Eén look: `packages/design` is de enige bron. Na een wijziging daar: `node scripts/sync-design.mjs` (kopie voor Verbatim; een test faalt anders).
  SwiftSkip kopieert bij het bouwen. De speler-overlay heeft de donkere waarden letterlijk in `style.css`; ook die bewaakt een test. Geen eigen tokens of knoppen in een app.
- Popup testen in echte Zen kan zonder venster: `--headless --marionette -remote-allow-system-access` met een eigen profiel, `Addon:Install` en `browserActionFor(ext).openPopup`.
- De repo en de map heten `trivium`. Updates van Velox lopen via `site/swiftskip/updates.json`; de oude repo's `studie-ecosysteem` en `SwiftSkip` zijn weg (2026-11-02).
- Map of repo hernoemd: venvs wijzen nog naar het oude pad. Herstel met `uv sync --reinstall` in `apps/hub` en `apps/verbatim`.
- Zen verbergt het Extensies-paneel: zet `extensions.unifiedExtensions.button.always_visible` op true om een add-on vast te maken.
- Node-werkruimtes: `npm` (workspaces) vanuit de root; er is geen pnpm op deze machine.
- SwiftSkip is geen werkruimte: `npm ci`, `npm test` en releases vanuit `apps/swiftskip`. `.env` met de AMO-sleutels staat
  daar lokaal.
- WebKit draait niet op Arch: lokaal Chromium en Firefox, WebKit alleen in de CI.
- Eigen rooster testen: upload `fixtures/private/rooster.ics` en `rooster-aanvulling.ics` samen. De aanvulling komt
  uit schermafbeeldingen, omdat TimeEdit niets vóór 12 oktober exporteert. Verwacht op 2026-11-01: 63 open.
- `fixtures/rooster-anon.ics` hermaken: `node scripts/anonymize-rooster.mjs`.
