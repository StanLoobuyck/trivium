# Changelog

## ▶ Start here (volgende sessie)
1. Oriëntatie: `CLAUDE.md`. Daarna `npm test`; SwiftSkip en Verbatim testen in hun eigen map (`npm test`, `uv run pytest -q`).
2. **Klaar:** fase 0 t/m 5 gebouwd. Fase 5 is herdaan: Verbatim en SwiftSkip laden nu echt `packages/design`. Verbatim is live na herladen.
3. **Wacht op de eigenaar:** SwiftSkip-popup in Zen beoordelen (tijdelijk laden via `about:debugging`: `apps/swiftskip/dist/firefox/manifest.json`), daarna akkoord
   voor release 4.4.0. Oordeel over de look, notitiemodel in Verbatim (nu Gemini), namen voor fase 6, LaTeX-skill verfijnen.
4. **Niet getest:** ronde hoeken van het echte Zen-venster (headless heeft die niet), look op de echte Kaltura-speler, badges in de Inhaal-app zelf, Safari.
5. **Volgende:** na het oordeel release 4.4.0, dan de slides-stroom (aanbevolen) of fase 6.
6. **Open:** vakkleuren in Verbatim volgen de lijstvolgorde, niet de kleur uit Inhaal; Lighthouse niet gemeten; `~/Documents/lecture-transcriber` opruimen als Verbatim stabiel blijft.

## 2026-11-01 — één look, echt: Verbatim en SwiftSkip op packages/design
- Eigenaarstest: het leek op Inhaal, maar was het niet. Oorzaak: beide apps hadden eigen kopieën van de waarden en eigen componenten.
- Verbatim: `tokens.css`, `app.css` en `css/` weg (ruim 640 regels), nu `design/` (exacte kopie) plus `verbatim.css` met alleen eigen schermen. Zelfde zijbalk,
  tabbalk, rijen, toast en scrollgedrag als Inhaal. Taal en thema staan in Instellingen. De tabel werd een gegroepeerde lijst, het lesscherm volgt de mock-up.
- SwiftSkip: popup, instellingen en welkomstpagina laden dezelfde CSS met Inter. Overlay: Inhaals kaart, sheet en toast, Download nu rechtsboven.
- Hoeken in Zen: Zen tekent het venster in `#1F1F1F` achter onze pikzwarte pagina. In donker staat de popup nu op `--card` (`#1C1C1E`), zoals Inhaals sheets.
- Gemeten op 1440 px: 140 van 142 stijlwaarden van de zijbalk gelijk tussen Inhaal en Verbatim; de 2 verschillen zijn meetruis (tweecijferige teller, `auto`/`0px`).
- Inhaal-instellingen: losse teksten staan nu in een kaart. Grotere layoutwijzigingen niet gedaan.
- Tests: 128 unit, 134 schermtests (13 overgeslagen), 88 + 27 SwiftSkip, 232 Verbatim, webextensie-lint 0 fouten. Nieuw: test die drift tussen de apps tegenhoudt.

## 2026-11-01 — fase 5: één look
- Keuze: richting A (blauw zoals Inhaal), met het modellenblok uit C en het app-icoon uit B. Canvas: privé, in de sessie gelinkt.
- Verbatim: tokens en lettertype volgen stijl A (Inter i.p.v. Geist), zwevende zijbalk, vakkenlijst scrolt, modellen blijven zichtbaar.
- Inhaal: icoon linksboven in de zijbalk. Op de gsm is er geen zijbalk, dus daar staat het niet.
- SwiftSkip 4.3.0: stijl A in menu, instellingen en overlay. Instellingen via een knop bovenaan het menu en in het `?`-venster op
  de speler. Instellingenpagina gegroepeerd, met sectielijst vanaf 900 px en Koppelingen als eigen groep.
- Bekeken op schermafbeeldingen in licht en donker; niet in Safari.

## 2026-11-01 — Verbatim meldt alle lessen, dubbel semester weg
- Eigenaarstest: geen enkele badge in Inhaal. De worker bewaarde de instellingen van bij het opstarten, dus de koppeling
  bleef voor hem onbekend, en oude lessen werden nooit gemeld. Nu leest hij elke ronde de instellingen en vergelijkt hij alle
  lessen met `hub_sent.json`. Dat vervangt de wachtrij. Gemeten op echte data: 9 berichten, 8 lessen, 0 zonder les.
- Een datum die Verbatim alleen uit de bestandsleeftijd haalt, gaat niet mee: die zei niets over de les.
- Hub: tweede actief semester zacht gewist met 7 vakken, 1 les verplaatst. Gecontroleerd: `/api/courses` geeft nu 6 vakken.

## 2026-11-01 — Verbatim: klikbare transcriptregels
- Een klik op een transcriptregel springt naar dat moment; tekst selecteren blijft werken. Op een echte les gemeten: doel
  174,9 s, speler 175,6 s; na slepen over tekst bleef de speler staan.
- De stap `stage_suggestions` heeft nu een leesbare naam in beide talen.
- Gevonden: de hub heeft twee actieve semesters met dezelfde naam, elk met 7 vakken. Daarom gaf `/api/courses` dubbels.

## 2026-11-01 — fase 4: Verbatim gekoppeld
- Verbatim: `codes` per vak, knop Vakken ophalen (koppelt op code of naam, wijzigt verder niets), inbox ook in
  `~/Downloads/Verbatim/<vakcode>/`, `notes.ready` naar de hub met een wachtrij voor als de hub onbereikbaar is.
- SwiftSkip 4.2.0: schakelaar Downloads naar Verbatim, standaard uit. Keuzes van de eigenaar.
- Hub: `POST`/`GET /api/events`, `GET /api/courses`. Inhaal zoekt de les eerst op bestandsnaam: die is gelijk aan de
  download van SwiftSkip. Geen les gevonden: geen badge, geen vraag.
- De badge is een regel "Notities klaar" op de rij; op de laptop opent een knop de les in Verbatim.
- Tests: 88 + 27 SwiftSkip, 227 Verbatim, 16 hub, 120 unit, 134 schermtests. Zonder echte download of Whisper-run.

## 2026-11-01 — fase 4: Verbatim verhuisd
- De repo had één commit. In de monorepo zijn weggehaald: Mac-naam en -IP, thuispaden, plaatsen en weekritme, privémail,
  echte docentennamen, Claude-vermeldingen. De voorbeeldvakken blijven; de eigenaar gaf akkoord om te pushen.
- `CLAUDE.local.md`, `PLAN.md` en `CHANGELOG.private.md` staan alleen lokaal in `apps/verbatim`.
- Het Mac-adres staat niet meer in de standaardinstellingen: bij overschakelen hoort `stt.mac.url` in de eigen config.
- Updatemelding van Inhaal staat nu in de pagina en schuift de inhoud op, in plaats van eroverheen te liggen.

## 2026-11-01 — halverwege toont de resterende tijd
- Eigenaarstest: de rij toonde de bekeken tijd in plaats van wat overblijft ("0u 10" bij een les van 2 uur). De rij en de
  sheet tonen nu "Halverwege · 0u 10 bekeken", rechts de resterende tijd. Het getal bovenaan rekende al juist.

## 2026-11-01 — delen van een les
- Een les in delen (`deel`/`part` in de titel, of meerdere opnames bij één les) wordt afgevinkt als de bekeken tijd samen 80%
  van de lesduur haalt; tot dan staat ze op halverwege, met de juiste resterende tijd. Keuze van de eigenaar.
- Een opname uit één stuk vinkt af bij 90% van de opname, ook als ze korter is dan de les.

## 2026-11-01 — Claude-vermelding uit de geschiedenis
- 19 regels `Co-Authored-By` verwijderd met een force push, op verzoek van de eigenaar. Alle 56 commits hebben dezelfde datums
  en dezelfde bestandsbomen; alleen de commit-id's en de tags `swiftskip-v4.1.0` en `-v4.1.1` zijn verplaatst.
- De oude repo StanLoobuyck/SwiftSkip is niet aangepast.

## 2026-11-01 — fix: opnames zonder Toledo-titel
- Eigenaarstest: bekijken en downloaden kwamen niet aan. `Semiconductor Physics - Lecture - Recording2.mp4` toont waarom
  dat kon: zonder `toolTitle` in het Toledo-adres stuurde SwiftSkip stil niets. De naam van de Kaltura-opname is nu de terugval.
- Delen van dezelfde les ("Les 6, part 3") komen nu bij die les. Elk deel dat tot 90% bekeken is, vinkt de les af.
- De echte Firefox-test kon niet: geckodriver downloaden en starten werd geweigerd. Blijft een test van de eigenaar.

## 2026-11-01 — fase 3: Koppel met Inhaal
- SwiftSkip geeft bekeken (vanaf 90% van de positie), positie en downloads door. Zonder koppeling wordt niets bewaard.
- Koppelen start in Inhaal. Een webpagina kan geen extensiepagina openen, dus de link gaat naar `www.kuleuven.be`, waar
  SwiftSkip al draait en zijn instellingen opent. De gebruiker bevestigt daar, en daarna vraagt de browser toestemming.
- Op het Inhaal-adres draait alleen een klein script, niet het spelerscript. De wachtrij blijft tot Inhaal bevestigt.
- Keuzes van de eigenaar: koppelen vanuit Inhaal, één melding met undo, rustige rij voor opnames zonder les.
- Opnames zonder les blijven lokaal op de laptop; de gekozen koppeling staat bij de les en synct wel mee.
- Bekeken telt de positie: doorspoelen tot 90% vinkt dus ook af. Undo vangt dat op.
- Gevonden: een manuele link opslaan had de opnamegegevens van een les gewist. Opgelost.
- Tests: 109 unit (root), 85 unit SwiftSkip, 130 schermtests Inhaal (11 overgeslagen), 24 browsertests SwiftSkip.

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
