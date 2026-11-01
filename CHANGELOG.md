# Changelog

## ▶ Start here (volgende sessie)
1. Oriëntatie: `CLAUDE.md` (laadt vanzelf). Daarna `npm test`; `npm run build && npm run test:e2e` voor schermen.
2. **Nu:** fase 2 is af: de reboot-test slaagt met automatisch aanmelden op de Mac. SwiftSkip staat met geschiedenis in
   `apps/swiftskip`; 4.0.1 naar 4.0.2 is door de eigenaar bevestigd. Update naar een volgende versie via het nieuwe adres
   is nog niet bewezen.
3. **Volgende:** "Koppel met Inhaal" (opt-in, zie `PLAN.md`, sectie Ecosysteem). Daarmee komt ook de eerste release vanuit
   de monorepo (`swiftskip-v`), die de laatste test van fase 3 is.
4. **Wacht op de eigenaar:** niets.
5. **Open:** Lighthouse niet gemeten, overkoepelende naam (fase 6).

## 2026-11-01 — SwiftSkip verhuisd naar de monorepo
- 30 commits met geschiedenis naar `apps/swiftskip`, vanuit een gefilterde kopie: auteur op het noreply-adres, zodat privé-
  mailadressen niet in deze repo komen. De commit-id's verschillen dus van de oude repo. Daarom geen tags meegenomen.
- SwiftSkip is geen npm-werkruimte: eigen `node_modules` en lockfile, en `npm test` vanuit `apps/swiftskip`. Zo blijft de
  app los te bouwen en verandert de root-lockfile niet. De CI-job heet `swiftskip` en blokkeert de Pages-deploy niet.
- `release.js` schrijft nu `site/swiftskip/updates.json`, met tags `swiftskip-v`, en respecteert `--dry-run` ook zonder `--`.
- De oude repo moet blijven bestaan: installaties tot 4.0.1 lezen daar hun update, en de downloadlinks in de README's en de
  instellingenpagina wijzen er nog naar. Die links aanpassen hoort bij fase 6.
- Reboot-test geslaagd na automatisch aanmelden; 4.0.1 kreeg 4.0.2 in Firefox.

## 2026-11-01 — SwiftSkip 4.0.2 gepubliceerd, reboot-test mislukt
- 4.0.2 is de brugversie: update-adres `stanloobuyck.github.io/studie-ecosysteem/swiftskip/updates.json`. Gecontroleerd:
  ondertekend, id en adres kloppen, sha256 van de download gelijk aan de waarde in beide manifesten.
- Bedoeld was eerst een proefrun, maar `npm run release 4.0.2 --dry-run` publiceerde echt: npm slikt de vlag. De eigenaar
  had de release wel toegestaan. De fout staat ook in `DEVELOPMENT.md` en `release.js`; aanpassen bij de verhuizing.
- Reboot-test mislukt. Gemeten op de Mac: FileVault uit, `SleepDisabled 1`, hub draait sinds het opstarten (`runs = 1`),
  Tailscale pas sinds de aanmelding, geen automatisch aanmelden. Het wachtwoord was dus het aanmeldscherm, niet FileVault.
- Hernoem je de repo in fase 6, dan moet er eerst nog een
  brugversie uit, want dan valt dit update-adres weg.

## 2026-11-01 — fase 3: updatebestand van SwiftSkip op Pages
- `site/swiftskip/updates.json` is een kopie van het bestand in de oude repo (4.0.0 en 4.0.1). Nog geen enkele installatie
  leest het. Drie tests bewaken de vorm, want een fout hier stopt stil de updates.
- Installaties tot 4.0.1 blijven het oude adres lezen. Dat bestand moet dus 4.0.2 krijgen en blijven bestaan.
- De eigenaar testte het tikken op balkjes op de iPhone en vulde de examendata in.

## 2026-11-01 — sessie-id's zijn stabiel
- Nieuwe download vergeleken met de vorige: 154 gedeelde sessies, 0 gewijzigd, 0 lessen met een nieuwe id. Wel een
  schuivend venster: 39 oude sessies vielen eraf, 40 uit april 2027 kwamen erbij. De hub heeft 0 dubbele lessen.
- Een dag verschil, dus sterk bewijs maar geen garantie op lange termijn.

## 2026-11-01 — plan telt komende lessen mee
- Het tempo per week rekent nu met open lessen plus lessen die nog komen tot de examens.
- Staafjes tonen de week bij hover, tik en slepen met de vinger.

## 2026-11-01 — inhaalplan, grafiek, sneltoetsen
- Inhaalplan met afspeelsnelheid (1×, 1,5×, 2×; bewaard op het semester), staafjes met open sessies per lesweek.
- Sneltoetsen J/K, X/spatie, N, 1-9, Z. `/` en ⌘K nog niet: er is nog geen zoekfunctie of commandopalet.

## 2026-11-01 — afvinken is direct
- Scherm en geheugen veranderen meteen, opslaan gebeurt erachter; geen wachttijd en geen animatie meer bij afvinken.
- Bug: door de wachttijd raakte een snelle tik dezelfde rij opnieuw (aan, uit, aan) terwijl de teller doorliep ("13"
  bij 7 lessen). De teller telt nu unieke lessen.

## 2026-11-01 — fase 2: hub en sync (laptop)
- `apps/hub`: FastAPI + SQLite, `/api/sync` (recentste `updatedAt` wint), rooster elk uur ophalen, koppelcode van
  minstens 32 tekens. 13 pytest-tests.
- Sync in de app: scant op `updatedAt` na de laatste push in plaats van een outbox-tabel (minder bewegende delen).
  Elke 4 s zolang de app openstaat, niet 30 s, om de eis van 5 s te halen. Twee toestellen en offline getest.
- Wissen en herstellen zijn nu zachte wijzigingen, zodat ze ook andere toestellen bereiken.
- Afwijking van het plan: Tailscale Funnel met koppelcode i.p.v. Cloudflare Tunnel + Access.

## 2026-11-01 — niet vindbaar in zoekmachines
- `noindex` op Inhaal, landingspagina en voorbeeldpagina: bereikbaar met de link, niet bedoeld voor Google. De repo
  zelf blijft publiek op GitHub. Delen gebeurt met de link; het hub-adres blijft alleen voor de eigenaar.

## 2026-11-01 — fase 1: feedback van de eerste iPhone-test
- Derde test: gsm scrolt weer als gewone pagina. iOS knipte de app af op een venster dat korter is dan het scherm:
  een eigen scrollvak gaf een gat onderaan, `screen.height` sneed de menubalk af. Rijen schuiven nu na 180 ms door in
  plaats van 2,5 s; Afgewerkt staat altijd open. Menubalk wordt breder zonder +. Kleine animaties toegevoegd.
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
