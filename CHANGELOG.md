# Changelog

## ▶ Start here (volgende sessie)
1. Oriëntatie: `CLAUDE.md` (laadt vanzelf). Daarna `npm test`; `npm run build && npm run test:e2e` voor schermen.
2. **Nu:** fase 1 gebouwd en lokaal getest, wacht op de test van de eigenaar op iPhone en laptop. Fase 0 is af.
   Repo `studie-ecosysteem`, MIT, noreply-adres in deze repo, geen Claude-vermelding in commits. `PLAN.md` blijft
   lokaal (geen back-up via GitHub).
3. **Volgende:** na goedkeuring fase 2 (hub op de Mac). Daarvoor nodig: domein voor de tunnel.
4. **Open:** `UID`-stabiliteit over exports nog niet bewezen: over enkele dagen de roosterlink opnieuw downloaden en
   vergelijken (eerste getal = TimeEdit-id, goed teken). Lighthouse nog niet gedraaid. Overkoepelende naam (fase 6).

## 2026-11-01 — fase 1: feedback van de eerste iPhone-test
- Laptop: twee kolommen op overzicht, vakdetail en instellingen vanaf 1100 px. Ruimte onder de keuzeknop.
  `#stage` gebruikt `overflow: clip`, omdat `hidden` de app uit beeld kon schuiven.
- Tweede test: `#stage` vult het scherm met `screen.height` (op het beginscherm was het venster korter, wat de balk
  ongeveer de hoogte van de statusbalk omhoog duwde). Bounce weer aan met `overscroll-behavior: contain`. Kleine titel
  bij scrollen weg. Weergave Systeem/Licht/Donker in instellingen.
- Sheets sluiten door naar beneden te vegen (vanaf de bovenkant van de sheet, niet vanuit tekstvelden).
- De app scrolt nu binnen `.view`, met `overscroll-behavior: none`, tegen het meetrekken op het beginscherm.
- Afgevinkte rijen blijven staan tot 2,5 s na de laatste tik of aanraking; undo geldt voor de hele reeks.
- Zwevende tabbalk en zijbalk, effen zonder blur. Op de laptop vervangt een knop Toevoegen in de zijbalk de +.
  Op een breed scherm staan het getal en Volgende naast elkaar.

## 2026-11-01 — fase 1: Inhaal-MVP
- Rooster uploaden (.ics, meerdere bestanden tegelijk), controle van vakken, overzicht, vakdetail, instellingen,
  sessie-opties, manueel toevoegen, Selecteer, swipe en lang drukken, undo, Notes plakken, JSON- en Notes-export,
  back-upherinnering, installatie-uitleg, NL + EN met keuze in instellingen, updatebanner.
- `domain/` is puur en getest: parser, semesters splitsen (gat > 21 dagen), vakken, nummering, samenvoegen, Notes.
- Echt rooster + aanvulling (33 sessies uit schermafbeeldingen, week 21/9 tot 11/10; 13 sessies van de week van 12/10
  vergeleken met de export: identiek): **63 open**, los van de app nageteld. Zonder aanvulling 35.
- Tests: 78 unit, 88 schermtests lokaal (2 overgeslagen: offline in Firefox). `axe` zonder meldingen op alle schermen.
- Keuzes zonder overleg, klein en omkeerbaar: alleen het huidige semester wordt geïmporteerd; een bestand uit een
  later semester start een nieuw semester. Vervolgvakken worden voorgesteld op dezelfde docent en niet-overlappende
  lessen. Korte namen zijn initialen (EB, DS) en aanpasbaar. De examendatum is een schatting, aanpasbaar.
- Niet in deze fase: sneltoetsen en commandopalet (fase 2).
- Niet gemeten: Lighthouse (`npx lighthouse@latest` werd geweigerd omdat het niet-vastgepinde code uitvoert).

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
