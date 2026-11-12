# Changelog

## ▶ Start here (volgende sessie)
1. **G14-test van 0.2.2 (2026-11-12):** de fix voor os error 448 werkt (eigen Python, geen 448 in de 0.2.2-run). Nieuwe fout: "Access is denied (os error 5)" bij het vervangen van `.venv\Scripts`, omdat Verbatim 0.2.1 nog draaide; de melding zei ten onrechte 448 (oude regels in hetzelfde `install.log`). **0.2.3** (nog niet uitgebracht) stopt een draaiende Verbatim vóór het installeren en leest alleen de eigen run.
2. **Volgende stap:** CI groen? Dan tag `verbatim-v0.2.3` (vraag de eigenaar). Op de G14 nu al: Verbatim afsluiten (systeemvak → Quit, of Taakbeheer → `pythonw.exe`) en 0.2.2 opnieuw draaien; daarna de checklist (Groq-sleutel, Velox, testles, Startmenu, herstart).
3. **Niet getest / onaf:** de 0.2.3-installer is niet lokaal gecompileerd (geen Inno op Linux; alleen CI). Installeren als gewone gebruiker in CI (stap blokkeert niet); tray en meldingen op echte Windows; een volledige les via Velox op Windows. Velox 5.5.0 nog niet in de Edge-winkel.
4. **Wacht op eigenaar:** G14-test; daarna de minder technische vriend; Mac-scherm terug (`~/velox-safari/resolution restore`), `latex-notes.zip` uploaden, Velox in de Mac App Store (wacht op de vader).
5. **Later (W8, optioneel):** Sequo zonder hub. Open: notitiemodel (nu Gemini), ondertitels (grootte/positie), afspeelkopie EBS Les 6.

## 2026-11-12 — Verbatim 0.2.3: installeren terwijl Verbatim draait
- G14 (gewone dubbelklik, 0.2.1 stond er al en draaide): 0.2.2 maakte de omgeving opnieuw met de eigen Python (andere interpreter dan uv's Python van 0.2.1), en het verwijderen van `.venv\Scripts` faalde: `pythonw.exe` was in gebruik. Inno's `CloseApplications` ziet alleen bestanden die het zelf kopieert, niet `.venv`. CI zag het nooit: daar draaide de oude versie niet tijdens de update.
- Installer: stopt bij `ssInstall` elk proces uit de installatiemap (PowerShell, wacht tot 20 s, schrijft het in `install.log`); `install.log` krijgt per run een kop, en de foutmelding kijkt alleen naar die run; nieuwe melding bij os error 5/32 ("Sluit Verbatim … Quit").
- CI: de update-test start eerst de oude Verbatim; nieuwe stap "0.2.1 draait, dubbelklik op de nieuwe installer" (`test-upgrade.ps1 -From verbatim-v0.2.1 -Manual`).
- CI op Windows was twee keer rood op `test_tick_queues_velox_download_with_notes_when_gemini_is_set`: de aanmaaktijd van een bestand kan op Windows enkele ms ná `time.time()` liggen, dan werd de wachttijd negatief. Nu nooit onder 0.
- Getest lokaal: root 144 + 1 overgeslagen; Verbatim 331 (3 archieftests falen ook zonder deze wijziging: geen ssh/rsync in deze cloudcontainer). Installer alleen via CI.

## 2026-11-12 — Verbatim 0.2.1 en 0.2.2: de installer op echte laptops
- Echte test (vriend, Discord + eigen G14): 0.2.0/0.2.1 faalden bij "Python downloaden". `install.log` (nieuw in 0.2.1: uv en setup-simple loggen en worden gecontroleerd, CUDA → CPU-terugval, duidelijke melding) toonde **os error 448** ("niet-vertrouwd koppelpunt"): uv's eigen Python maakt een junction `cpython-3.12-…`, en Inno Setup zet RedirectionGuard aan, wat uv erft; een junction van een gewone gebruiker wordt dan geweigerd. Vanuit PowerShell (als beheerder) lukte hetzelfde wel; CI draait als beheerder en zag het dus nooit.
- Daarna bij de vriend: "SRE module mismatch" door een eigen Python 3.10 met globale `PYTHONPATH`. De vriend draait Verbatim nu (handmatig: variabelen leeg, `uv sync`, `python -I … setup-simple`, app met `-I`).
- 0.2.2: Python 3.12.16 (python-build-standalone 20261026) zit in de installer (113,7 MB), uv met `--no-managed-python --no-python-downloads --python {app}\python\python.exe`; `RedirectionGuard=no`; `python -I` in snelkoppelingen, `PYTHONPATH`/`PYTHONHOME` leeg tijdens het installeren (CI test met een kapotte `re.py` op `PYTHONPATH`); heropenen na Bijwerken pas na uv (een `[Run]`-regel liep vóór `ssPostInstall`, CI ving het: app op de oude omgeving); aparte melding bij os error 448; tab Suggesties weg in eenvoudige modus.
- Testen als gewone gebruiker in CI (`test-standard-user.ps1`, nieuwe lokale gebruiker + `Start-Process -Credential`): Setup start niet (geen setup.log, exit 1 na ~20 s), ook niet met 0.2.1, dus het bewijst niets; niet-blokkerend gelaten na twee pogingen.
- Velox **5.4.0 live in de Edge-winkel** (`oojejooncahlokgpffoomionmgnlaibk`); knop op de Trivium-pagina, Chrome krijgt de raad Edge/Firefox; READMEs bijgewerkt. Velox **5.5.0** uitgebracht door de eigenaar (de release werd voor Claude door de toestemmingscontrole tegengehouden).
- Werkwijze: de eigenaar wisselt voortaan naar Claude Code op Windows voor test-en-fix-rondes (logs direct lezen); een Windows-VM (quickemu) is een optie voor schone "nieuwe laptop"-tests.
- Getest: CI groen voor elke stap (zie hierboven); root 145; Verbatim 334 lokaal. Release-workflow `verbatim-v0.2.2` liep nog bij het afsluiten.

## 2026-11-11 — updates getest, Velox ziet Verbatim, README's, opruimen
- CI test nu ook **bijwerken**: de gepubliceerde 0.2.0 installeren, instellen als een gebruiker (Groq-sleutel, Whisper "snel", achtergebleven codebestand), dan de nieuwe installer met precies de argumenten van de knop Bijwerken. Gemeten: 13 s; sleutel, keuze, map en welkomststatus blijven, oud bestand weg, Verbatim gaat vanzelf weer open met de juiste versie (`/api/setup` geeft nu `version`). Valkuil: `Start-Process -Wait` wacht ook op de heropende Verbatim; `WaitForExit` niet.
- Velox (5.5.0, nog niet uitgebracht): draait Verbatim op deze computer (`127.0.0.1:7861` met titel "Verbatim"), dan gaat "Downloads naar Verbatim" vanzelf aan, bij het starten van de browser en bij elke download, tot de gebruiker de instelling zelf verandert (`downloadsToVerbatimChosen`). Keuze eigenaar: vanzelf aan. Een race (instelling veranderd tijdens het kijken) gevonden met de e2e-tests: de instellingen worden na de controle opnieuw gelezen. E2e-tests starten nu overal van "zelf uitgezet", ook als er lokaal een echte Verbatim draait. Getest: 111 unit, 34 e2e (1 nieuw met een nep-Verbatim op 7861 of de echte), lint schoon, dry run OK.
- README's van Verbatim: Windows-sectie (gebruikers → handleiding; ontwikkelaars → bouwen, CI, release met tag).
- Opgeruimd (akkoord eigenaar): `~/inhaal-hub` op de Mac (24 MB, niet meer in gebruik; hub antwoordt nog). `.paar-fout-2026-11-02/` bestond niet meer.
- Sequo-job één keer rood op een WebKit-time-out (back-up exporteren); niets aan Sequo veranderd, opnieuw gestart.

## 2026-11-11 — Verbatim W6: updates, handleiding, eerste Windows-release
- CI groen na de spiegelwissel (`/etc/apt/apt-mirrors.txt`). Installer-test op een schone Windows: 99 MB, installatie 34–38 s (Python + bibliotheken), omgeving 562 MB, instellingen en eigen ffmpeg in orde, lokaal Whisper (small) op de CPU, app zonder console antwoordt, verwijderen laat de lessen staan.
- Fout gevonden met die test: via de snelkoppeling (`pythonw.exe`) heeft Python geen stdout/stderr en startte uvicorn niet. Nu gaat de uitvoer dan naar `<cache>/app.log` (ook handig om bij de vriend op te vragen). Nagebootst op Linux: zonder de fix geen antwoord, met wel.
- Updates (keuze eigenaar: banner + één klik): `updates.py` kijkt hoogstens een keer per dag naar de GitHub-releases `verbatim-v…` (alleen in de Windows-app), banner "Verbatim x staat klaar · Bijwerken" bovenaan de bibliotheek, niet tijdens het omzetten (melding). De installer wordt gecontroleerd tegen de SHA-256 van GitHub, stil gestart met dezelfde map en Whisper-keuze, verwijdert de oude code en opent Verbatim opnieuw (`/RELAUNCH=1`). Eén melding per versie in de tray.
- Release: tag `verbatim-v<versie>` (gelijk aan `pyproject.toml`) → workflow `verbatim-release.yml` bouwt, installeert, test en publiceert (niet als "Latest"; dat blijft Velox). Release-notities = boodschap van de tag.
- Site: handleiding `site/verbatim/` (NL/EN; downloadknop zoekt de nieuwste installer via de GitHub-API, anders de releasepagina; SmartScreen "Meer info → Toch uitvoeren"; Velox-instelling "Downloads naar Verbatim" aanzetten; app.log), Verbatim-kaart met knop Windows. Privacybeleid: Windows-versie (Groq standaard, vakcode naar de KU Leuven, updatecheck bij GitHub, model van Hugging Face).
- Valkuil (in CLAUDE.md): een test-app draaide met de echte Velox-map en maakte in een tijdelijke config vakken en twee jobs uit de eigen downloads. Nagekeken: niets in `~/Downloads/Verbatim` gewijzigd, geen audio verstuurd (geen sleutel).
- Getest: 334 Verbatim lokaal (6 nieuw voor updates, 2 voor app.log, 4 voor lokaal Whisper), root 145; banner in Chromium op 375/1440 px (NL/EN, "bezig"-melding); handleiding op 375/1440, licht/donker, NL/EN: 0 px overloop.

## 2026-11-11 — Verbatim W4 en W5: Velox naar Edge, installer voor Windows
- Velox: winkelpagina voor **Edge Add-ons** ingediend (eigenaar, gratis Partner Center-account als individu). `apps/velox/store/edge/`: teksten NL/EN, privacyantwoorden, opmerkingen voor de reviewers (testen zonder KU Leuven-account), logo 300×300 en 8 schermafbeeldingen 1280×800 uit de testpagina's met een neutrale demoslide (`STORE_SHOTS=1 npx playwright test store-shots`). Keuze eigenaar: niets betalen, dus geen Chrome Web Store. Overblijfselen van de hernoeming weg uit README's en privacybeleid.
- Trivium-pagina: Velox-knop volgens de browser (Edge-winkel in Edge zodra `EDGE_URL` ingevuld is; Chrome krijgt dan de raad Edge of Firefox). Nagekeken met nagebootste Firefox/Edge/Chrome op 375 px, zonder en met Edge-link: 0 px overloop.
- Verbatim: een Velox-map met een onbekende vakcode wordt in eenvoudige modus een vak, met de officiële naam uit de publieke ECTS-fiches van de KU Leuven (anders de code); alleen de vakcode gaat naar de KU Leuven. Schakelaar "Maak automatisch notities" (aan; alleen met een Gemini-sleutel). Uitgeschakelde schakelaar in `packages/design` gedimd.
- Lokaal Whisper ook op de processor: `device: auto` (GPU als die werkt, anders CPU; mislukt de GPU toch, dan verder op de CPU), int8, beam 1. Gemeten op 5 min Nederlandse les (RZL), CPU int8, tegen het GPU-transcript (large-v3): **small** 13× realtime, 15,7 % andere woorden ("Mijn manager" voor "Dus men"); **large-v3-turbo** 6,6×, 4,5 %. 4 of 16 threads maakt weinig uit. Keuze eigenaar: in de installer "Nauwkeurig" (turbo, standaard) of "Snel" (small). Extra `whisper-cpu` (zonder 1,5 GB CUDA); met NVIDIA de gewone `local`, DLL's van de nvidia-wheels via `add_dll_directory`.
- Installer (`apps/verbatim/packaging/windows/`): klein, per gebruiker zonder beheerdersrechten; uv 0.13.7, ffmpeg 8.1 (BtbN, GPL, licentie mee), Verbatim-bron. Twee vragen (map, Whisper), Startmenu, optioneel starten met Windows; op het einde `uv sync` (Python 3.12 + bibliotheken, eenmalig) en `lecture setup-simple`. Snelkoppelingen starten `pythonw -m lecture.cli app` (geen console); `prepare_windows_app` zet de eigen ffmpeg vooraan op PATH en opent hulpprocessen zonder consolevenster. Verwijderen laat lessen, sleutels en instellingen staan. CI-job installeert stil en controleert instellingen, ffmpeg, lokaal Whisper (small op CPU), de app en het verwijderen; het `.exe` is een artefact.
- CI hing: `ubuntu-latest` werd 26.04, maar de echte oorzaak was de spiegel `azure.archive.ubuntu.com` (elke package 20 s time-out, ook op 24.04). Twee pogingen misten (vastpinnen op 24.04; `sed` op `ubuntu.sources`): de runner leest zijn spiegel uit `/etc/apt/apt-mirrors.txt`.
- Getest: 326 Verbatim lokaal (+ Windows-CI), 107 Velox + 33 e2e, lint schoon, root 145. Niet getest: de installer op een echte laptop, het tray-icoon, een echte Groq/Gemini-sleutel.

## 2026-11-11 — Verbatim W3: welkomstscherm
- Keuzes eigenaar: stappen, één per scherm; Groq overslaan mag met waarschuwing; geen vakkenstap (vakken komen van Velox of uit het uploadformulier).
- `#/welcome` (`screens/welcome.js`), alleen in eenvoudige modus tot `app.welcomed`: ① taal ② Groq (knop naar de site, plakken, Test; overslaan → kalme uitleg "kan traag zijn" + "Toch overslaan") ③ Gemini optioneel ("Nu geen notities") ④ klaar: Velox (Trivium-pagina) of zelf een opname toevoegen. Geen zijbalk of tabbalk; op de gsm staan Terug/Volgende onderaan, op de laptop een kolom in het midden. Alle teksten NL + EN.
- `POST /api/setup/key/test`: vraagt de modellenlijst (gratis, geen quota), bewaart de sleutel alleen als hij werkt; redenen: formaat (niet verstuurd), geweigerd, regio (Gemini), offline, fout. `POST /api/setup/welcome-done` → `settings.yaml`.
- Nieuwe gebruiker in eenvoudige modus: geen vakken (was: de vakken uit de repo). `lecture setup-simple <map>` (voor de installer): eenvoudige modus, lessen in `<map>/jobs`, keten `[groq, local]`, lokaal ook op batterij, geen termcontrole; opnieuw draaien bewaart sleutels, vakken en welkomststatus.
- Nagekeken in Chromium (375 en 1440 px, licht en donker, met minder beweging): doorverwijzing bij de eerste start, alle vier stappen, foute sleutel, overslaan, 0 px overloop, geen verticale scroll, geen consolefouten; afgewerkt → bibliotheek, en blijft bewaard. Twee fouten onderweg hersteld: stap knipperde bij elke hertekening (animatie nu alleen bij een nieuwe stap), rijen in stap 4 afgekapt op 375 px.
- Getest: 315 Verbatim (10 nieuw), root 145. Niet getest: echte sleutels (alleen nep-antwoorden; een geldige Groq/Gemini-sleutel volgt bij W7).

## 2026-11-11 — Verbatim W2: één programma, eenvoudige modus
- `lecture app`: webinterface (uvicorn in een thread) en worker in hetzelfde proces, tray-icoon met "Open Verbatim" en "Quit" (pystray + Pillow, alleen op Windows/macOS geïnstalleerd), meldingen via de tray (`notify.set_backend`). Draait er al een worker (systemd op Linux), dan alleen de UI. Zonder pystray loopt het tot Ctrl+C.
- Eenvoudige modus (`app: {simple: true}` in de gebruikersconfig): geen Mac- en hubinstellingen (sleutels blijven), geen tab Delen, geen LaTeX-knop of -keuze per vak, geen Mac-presets bij modellen, archief zonder "video naar de Mac", geen termcontrole op de Mac (ook niet in de worker). Nieuw veld met standaardwaarde, dus lopende processen van de eigenaar blijven werken.
- Bug gevonden: `already_running` zocht "Lecture Transcriber" op de pagina, maar die heet al een tijd "Verbatim"; een tweede start probeerde dezelfde poort. Hersteld en getest.
- Nagekeken: `lecture app` in eenvoudige modus met een lege config op poort 7871, Chromium op 375 en 1440 px, licht en donker: tabs Modellen/Vakken/Verbindingen/Algemeen, onder Verbindingen alleen de sleutels, 0 px overloop, geen consolefouten.
- Getest: 305 Verbatim (4 nieuw: app met nep-tray, tweede start, herkenning, eenvoudige modus), Windows-CI 299 + 6 overgeslagen, root 145. Niet getest: tray-icoon en meldingen op echte Windows.

## 2026-11-11 — Verbatim W1: draait op Windows
- Aanleiding: een vriend (rechten, Windows) wil Verbatim; delen helpt niet (andere vakken). Verbatim draaide alleen op Linux.
- `oscompat.py`: bestandssloten (`fcntl` op Linux/macOS, `msvcrt` op Windows, blokkerend = opnieuw proberen), "leeft dit proces" (op Windows `OpenProcess`; `os.kill(pid, 0)` stuurt daar Ctrl+C), map/URL openen (`os.startfile`, `open`, `xdg-open`), losgekoppeld starten zonder consolevenster. Gebruikt in wachtrij, job, delen, quota, UI en API.
- Tekst van subprocessen (ffmpeg, ffprobe, claude) altijd UTF-8 (Windows gebruikt anders cp1252); LaTeX-pad in de prompt met `/`, voortgang herkent `lessen` ook met `\`; `.env`-rechtencontrole niet op Windows.
- CI: nieuwe job `verbatim-windows` (windows-latest, ffmpeg via choco). Eerste run 291/301, daarna 295 geslaagd + 6 overgeslagen (archiveren naar de Mac via ssh, VA-API, Linux-sysfs, Unix-rechten). Linux: 301 (4 nieuw voor sloten en processen), root 145.
- Niet getest: op een echte Windows-laptop (alleen CI, geen GPU, geen UI). Worker en `lecture ui` op de laptop draaien nog de oude code; gedrag op Linux is ongewijzigd, herstart mag bij gelegenheid.

## 2026-11-09 — Velox in Safari, gewone mp4
- Keuzes eigenaar: alleen macOS, via de Mac App Store onder het dev-account van zijn vader; downloaden eerst via de eenvoudige weg (Safari slaat op als gewone download).
- Op afstand getest (eigenaar 80 km weg): VNC via Tailscale naar de Mac (rechtstreeks, 97 ms). Retina-scherm te traag: met een klein Swift-script (`~/velox-safari/resolution`, alleen voor de sessie) op 1920×1200 gezet, 3,3× minder pixels. 8-bit kleur in Remmina gaf een time-out; GVNC vraagt `gtk-vnc` (niet geïnstalleerd).
- Xcode stond op de Mac; first launch met `sudo …/Xcode.app/…/xcodebuild -runFirstLaunch` (gewone `sudo xcodebuild` valt terug op de Command Line Tools). De converter schrijft de app-id met hoofdletter (`…Velox`) en de extensie-id niet: Xcode weigert dat, het script herstelt het.
- Safari-valkuilen: `tabs.sendMessage` van achtergrond naar tab/frame komt niet aan (antwoord `undefined`, ook met frame-id). Twee pogingen faalden; nu vraagt de speler en antwoordt de achtergrond (`safariNextDownload`, voortgang met de staat in het antwoord, `safariDownloadDone`). De download loopt in het spelerframe en wordt bewaard met een `download`-link op een blob. Popup-knop in Safari: "Gebruik de downloadknop in de speler". Geen Verbatim-mappen en geen slideknoppen in Safari.
- mp4 van Velox in QuickTime: zwart beeld, 27 u. Oorzaak: mux.js schrijft gefragmenteerde mp4 met duur 0xFFFFFFFF (27,05 u = 0xFFFFFFFF/44 100 Hz; de "13 u 15" van 2026-11-02 is hetzelfde bij 90 kHz). Alleen de duur herstellen hielp niet: AVFoundation opent geen enkele gefragmenteerde mp4 van schijf (ook die van ffmpeg niet). Nu schrijft Velox een gewone mp4 (`shared/mp4.js`: ftyp · moov met tabellen · mdat, co64, edit list voor de latere audiostart). Gemeten op de testsegmenten: AVFoundation 120,0 s en beeld op 30 s (was 97 401 s en "Cannot Open"); ffmpeg decodeert zonder fouten, alle videoframes gelijk aan ffmpegs eigen mp4. Verklaart waarschijnlijk ook de afspeelkopie van EBS Les 6.
- Eigenaar in Safari: download loopt, voortgang in de speler, mp4 speelt in QuickTime. Chrome/Firefox blijven 83 kB `content.js` (downloader alleen in de Safari-build, 275 kB).
- Uitgebracht: Velox 5.4.0 (ondertekend door Mozilla, GitHub-release, feed). Minimale macOS 12.0: oudste die een Safari krijgt met alles wat Velox gebruikt (16.4+); buildnummer = a·10000+b·100+c (5.4.0 → 50400), want de App Store wil per upload een hoger nummer.
- App Store-route gekozen (bronnen: Apple-hulp over rollen en API-sleutels): bij een individueel account zijn toegevoegde gebruikers alleen App Store Connect-gebruikers, geen teamleden voor ondertekening; een team-API-sleutel (Admin) kan wel provisioning, een individuele niet. Zo hoeft de vader alleen één uitnodiging te sturen. Zijn naam staat als verkoper in de store.
- CI faalde na de push: de mp4-test las testmedia die niet in git staan. De test maakt ze nu zelf aan (ffmpeg staat in de CI); lokaal geverifieerd vanaf een lege map.
- Getest: 107 Velox (3 nieuw voor mp4, 1 voor bestandsnamen), 33 e2e, lint schoon. Niet getest: echte download in Firefox/Chrome met de nieuwe mp4 (alleen e2e), geluid over VNC, een les met webcam in Safari.

## 2026-11-07 — Velox 5.3.0 op gedeelde lessen
- Eigenaar: Velox moet werken op de share-pagina's die hij naar mensen stuurt. Velox draait nu vast op `https://*.ts.net/share/*` (elke Funnel-hub, alleen `/share/`; geen hubnaam in de code). Sequo op dezelfde hub blijft zonder Velox.
- Valkuilen onderweg: Chrome weigert de hele extensie als `web_accessible_resources` een pad bevat (`/share/*`): daar alleen oorsprongen (test bewaakt het). Chrome geeft de hostrechten zonder pad terug (`https://*.ts.net/*`), waardoor de achtergrond ze als zelf aangezette site zag en een extra script registreerde (e2e-test ving het): ingebouwde patronen tellen nu in beide vormen.
- Nagekeken met de release-build in Chromium op de echte share-pagina (tijdelijke link, daarna ingetrokken): `]` → 1,25× met overlay "1.25×" zichtbaar, → spoelt 10 s, `r`, `?` sneltoetsenblad; op Sequo (zelfde hub) niets. Share-pagina toonde de sleutel `subs_on` i.p.v. tekst: hersteld (`subtitles_on`).
- Uitgebracht: Velox 5.3.0 (ondertekend, GitHub-release, feed). Getest: 103 unit, 33 e2e, lint schoon.
- CI faalde op de nieuwe examendatumtest in WebKit: Safari vuurt bij toetsenbordbewerking geen `change` op een datumveld. Sequo bewaart nu ook op `input` (zonder hertekenen). CI daarna groen (ook WebKit), 145 unit, 89 schermtests lokaal.
- Gevonden, niet opgelost: de afspeelkopie van EBS Les 6 (13/10) is nog een gefragmenteerde mp4 (`moof`), terwijl `player.json` klaar zegt; laadt niet via de share-pagina. De andere drie EBS-lessen zijn in orde.

## 2026-11-07 — deellink uit de adresbalk werkte niet
- Eigenaar stuurde het adres uit zijn eigen adresbalk (`…/share/#/`); de vriend kreeg "Open the link you were sent". Oorzaak: de pagina haalde de code na het inloggen uit het adres; bij de eigenaar werkte het nog dankzij de cookie.
- Nu blijft de code vooraan in elk adres (`#<code>`, `#<code>/vak/…`, `#<code>/les/…`); `/share/api/me` geeft de eigen code terug, zodat een oud `#/`-adres met cookie de code terugkrijgt. Nagekeken met een lokale hub: gekopieerd lesadres opent bij iemand zonder cookie meteen de les; `#/` zonder cookie en een foute code geven de juiste melding. Hub herstart, publiek nagekeken.
- De vriend had nooit een cookie: die heeft een nieuwe link nodig (Kopieer link in Instellingen → Delen).

## 2026-11-07 — examendatum, deelformulier, volgorde van versturen
- Eigenaar: examendatum in Sequo "reset" na herladen. Oorzaak: een datumveld vuurt `change` per afgewerkt deel (dag, maand, jaar); Sequo hertekende dan de pagina, het veld verloor de focus en de volgende cijfers werden sneltoetsen ("1" = overzicht). Op de hub stond zo een half getypte 10/12/2026. Nu: opslaan zonder hertekenen. Schermtest met pijltjestoetsen (vuurt `change` per druk): faalt zonder fix, slaagt met (Chromium, Firefox). Valkuil: de schermtests draaien op `_site/` → `npm run build` in de root, niet alleen `apps/sequo`.
- Eigenaar: naam en vakken van een nieuwe deellink verdwijnen. Oorzaak: tijdens een sync herlaadt het tabblad elke 3 s en hertekende het de hele sectie. Nu alleen de lijst met links (als die veranderde) en de statusregel; formulier na "Maak link" wel leeg. Nagekeken: "Lies" en een vinkje blijven staan tijdens een sync.
- Eigenaar: eerst maar één les gedeeld. Oorzaak: per les tekst + video (~15 s per video), dus lessen verschenen één voor één. Nu eerst alle teksten en ondertitels, dan de video's; status telt af per video.
- Share-pagina werkt zichzelf bij: lijst en vakken van de link elke minuut en bij terugkeren naar het tabblad, een les zonder video elke 30 s. Nagekeken: vak toegevoegd aan een link → 6 → 16 lessen zonder herladen.
- Getest: 297 Verbatim, 145 unit, 28 hub, 92 schermtests. `lecture ui` en worker herstart; share-pagina en Sequo op de hub bijgewerkt (statisch, geen hubherstart).
- Eigenaar bevestigt: alles werkt (ordenen, delen, examendatum). Volgorde wensen afgewerkt: ordenen → delen; Safari volgt over enkele dagen.

## 2026-11-06 — Verbatim delen
- Keuzes eigenaar: link via de Mac (Funnel draait al), per code een keuze van vakken (nieuwe lessen komen er vanzelf bij), per les video + transcript, notities en downloads.
- Hub `share.py`: deelcodes (naam, vakken, kleur) en lessen in SQLite, video en `.vtt` in `share/<les>/` naast de database. Beheer onder `/api/share…` met de koppelcode; bekijken onder `/share/api/…` met de deelcode als HttpOnly-cookie (`Path=/share`, SameSite strict, Secure achter Funnel). Een deelcode opent niets onder `/api/` (getest voor sync, courses, events, rooster), en de koppelcode is geen deelcode. Video met Range (spoelen) en als download; transcript als `.txt`.
- Verbatim `share.py`: houdt de hub gelijk met de jobs (nieuw of gewijzigd erop, vak niet meer gedeeld of les weg eraf). Stuurt geen paden, modellen, wachtrij of correctielijst mee. Worker: hoogstens om de 5 min en 1 video per ronde (meteen opnieuw als er nog video's wachten); "Nu bijwerken" stuurt alles. Bestandsslot tegen dubbel uploaden.
- Instellingen → Delen: link maken (kopieert meteen), vakken wijzigen, intrekken met 5 s ongedaan maken, status "x lessen gedeeld · nog y video's". Vijf tabbladen passen niet op 375 px: de balk scrolt opzij.
- Share-pagina (`web/share.html`, `js/share/viewer.js`, stijl en teksten van Verbatim; `deploy-hub.sh` zet ze in `~/trivium-hub/share-web/`): code na `#` wordt cookie en verdwijnt uit de adresbalk; bibliotheek per vak met groepen; les met video, ondertitels (`c`), hoofdstukken, notities, transcript met zoeken, drie downloadknoppen.
- Valkuil gevonden: de rsync van `apps/hub/` met `--delete` had `share/` (alle video's) bij elke deploy gewist; nu `--exclude /share --exclude /share-web`.
- Gemeten lokaal: 16 echte lessen (4,1 GB) naar een testhub in 6,3 s, tweede ronde 1,3 s en niets verstuurd. Publiek: `/share/` 200, `/share/api/me` zonder code 401, inloggen met tijdelijke code → `Secure`-cookie, na intrekken 401.
- Getest: 28 hub (10 nieuw), 296 Verbatim (11 nieuw), 145 unit. Chromium op 375 en 1440 px, licht en donker, voor de share-pagina en Instellingen → Delen: 0 px overloop, geen consolefouten; video speelt, tik op tijd spoelt. Niet in Safari, iPhone of Zen.

## 2026-11-06 — Verbatim-bibliotheek ordenen
- Keuzes eigenaar: lessen in delen als uitklapbare groep (bestanden blijven per deel); volgorde op lesnummer; lelijke titels opkuisen met het nummer uit Sequo; bibliotheek per vak.
- `library.py` (afgeleid, niets in een manifest): les en deel uit de titel, rang binnen het vak (semester, lesnummer, deel; een les zonder nummer na de genummerde op of vóór haar datum), groepssleutel vak + semester + les. Titel gelijk aan de gok uit de bestandsnaam en zonder nummer → "Les n" als het rooster die dag één hoorcollege heeft, anders "Les van 13 okt". Zelf hernoemd blijft staan; dubbele spaties weg.
- Hub: `/api/courses` geeft per vak `lectures: [{date, number}]`, zelfde telling als `computeNumbers` in Sequo (per vak en type, geschrapt telt niet, datum in Brussel). Verbatim bewaart dat in `~/Lectures/jobs/hub_lessons.json` en vraagt het na 10 min opnieuw op de achtergrond; zonder hub de datum.
- Lijst: blok per vak (vak met de nieuwste les eerst), groep "Les 11 · 4 delen" met totale duur en notitiestatus, open/dicht onthouden in de browser, met Enter/spatie te bedienen, een groep naar een map slepen verplaatst alle delen. Datum zonder jaartal in het huidige jaar; titels lopen door op 375 px. Valkuil: `.part` bestond al op de lespagina (24 px marge) → `.lecture-part`.
- Gemeten op echte data: Les 11 en Les 13 elk 4 delen in één rij; RZL 1–6 op volgorde (was 3 boven 1); EBS 13/10 → Les 6, 9/10 → Les 5, 29/9 → Les 2 (klopt met rooster + aanvulling).
- Getest: 285 Verbatim (8 nieuw), 18 hub (1 nieuw), 145 unit. Chromium op 375 en 1440 px, licht en donker: 0 px overloop, geen consolefouten. Niet in Zen en niet in Firefox bekeken.

## 2026-11-04 — ondertitels in de speler van Verbatim
- Lessen met een transcript (`outputs/subtitles.vtt`) krijgen ondertitels in de speler: toets `c` of de CC-knop van de speler. Keuze blijft onthouden (`lt-subs`), standaard uit; melding "Ondertitels aan/uit (c)". Typen in een veld schakelt niet. Na een woordcorrectie of een aanvaarde suggestie laadt de speler de nieuwe ondertitels.
- Eigen route `/api/lectures/{id}/subtitles.vtt` (als `text/vtt`, geen bijlage). `c` is vrij in Velox.
- Nagekeken op een echte les (482 cues) in Chromium en Firefox, 1440 px licht en 375 px donker: `c` aan/uit, tekst op de video, niet tijdens typen in de zoekbalk. Niet getest: in Zen zelf, op volledig scherm.
- Getest: 277 Verbatim (nieuw: ondertitels als WebVTT). Na herstart van `lecture ui` (7861) en de worker bevestigd door de eigenaar in Zen. Geen `install.sh` nodig: Verbatim is editable geïnstalleerd.

## 2026-11-02 — Velox-overlay op een video op volledig scherm
- Eigenaar: overlay werkt in de kleine speler van Verbatim, niet op volledig scherm. Oorzaak: daar is de `<video>` zelf het fullscreen-element; het overlay kan er niet in en hing in `<html>`, onder de bovenste laag.
- Velox 5.2.2: is de video zelf fullscreen, dan wordt het overlay een popover (`popover="manual"`, `showPopover()`), boven de video in de bovenste laag; na het verdwijnen weer gewoon. Op Toledo (fullscreen op een omhullend vak) verandert niets.
- Nagekeken in Chromium met minder beweging: 5.2.1 overlay in `<html>`, niet bovenaan; 5.2.2 popover open, midden op het scherm. Headless Zen weigert volledig scherm (ook na een klik): niet in Zen getest.
- Getest: 101 Velox, 33 e2e, lint schoon.

## 2026-11-02 — Velox-overlay onzichtbaar in Verbatim
- Eigenaar: in Verbatim werken de sneltoetsen, maar het overlay (1,25× enz.) is onzichtbaar. Oorzaak: het systeem heeft animaties uit (`gtk-enable-animations=false`), dus Zen vraagt "minder beweging"; `packages/design` zet dan `* { animation: none !important }`, en het overlay werd alleen via zijn animatie zichtbaar (basis opacity 0). Op Toledo bestaat die regel niet.
- Velox 5.2.1: de eindtoestanden staan nu ook in de gewone stijl; de animatie is alleen in- en uitgang. Nagekeken in headless Zen met `ui.prefersReducedMotion`: 5.2.0 opacity 0, 5.2.1 opacity 1, midden op de video.
- Onderweg twee verkeerde sporen: versie/toestemming (in orde: 5.2.0 met localhost) en "headless toont het niet" (in headless Zen lopen animaties helemaal niet; enkel met minder beweging aan is het een eerlijke test). Headless-schermafbeeldingen van Zen tonen soms een oude positie: vertrouw `getBoundingClientRect`.
- Getest: 101 Velox, 33 e2e, lint schoon.

## 2026-11-02 — delen van een les in Sequo
- Keuze eigenaar: in het venster van een les een lijst "Delen": per deel hoe ver je bent (bekeken / x van y / nog niet), knop naar de opname en (laptop) naar de Verbatim-les van dat deel. Bij delen geen los linkveld meer; opslaan raakt de opnames dan niet aan.
- `domain/recordings.js`: `partNumber`, `lectureParts`, `partState` (afgeleid, niet opgeslagen); `reconcileNotes` zet de Verbatim-les per deel op bestandsnaam. Delen komen samen via het lesnummer (op datum koppelt Sequo maar één opname per les).
- Design: geen dubbele ruimte tussen een groepstitel en een lijst in een venster.
- Getest: 145 unit, 137 schermtests (nieuw: les in delen, iPhone + laptop, Chromium + Firefox), licht en donker bekeken. Niet getest: de Verbatim-knop per deel met echte hubdata.

## 2026-11-02 — Velox in Verbatim
- Velox 5.2.0 draait ook op Verbatim (`127.0.0.1` en `localhost`, poort 7861). Match-patronen kennen geen poort: het manifest dekt alle lokale pagina's en `content.js` stopt meteen buiten poort 7861 (`isVerbatim` in `shared/sites.js`). Dev-builds blijven overal lokaal draaien voor de tests.
- Nagekeken met de release-build: in Verbatim zet een sneltoets de snelheid op 1,25× en verschijnt de overlay; op een andere lokale pagina (poort 7999) doet Velox niets. Geen Sequo-meldingen vanuit Verbatim (geen vakcode in de pagina), geen downloadknop (geen HLS).
- De update vraagt een nieuwe toestemming in Zen.
- Getest: 101 Velox + 33 e2e.

## 2026-11-02 — samenvoegen op de Mac, lus hersteld, stopknop in Verbatim
- Fout: na het samenvoegen stonden `X.mp4` en `X.webcam.mp4` nog naast elkaar, dus de inbox voegde Les 11 deel 3 drie keer samen (2560 → 3200 → 3840 px) en overschreef de originele slides. Nu: een opname met `X.slides.*` ernaast wordt nooit opnieuw samengevoegd (regressietest). Bestanden van die run in `Downloads/Verbatim/H01L1A/.paar-fout-2026-11-02/`; slides opnieuw downloaden.
- Samenvoegen eerst op de Mac (`/v1/video/side-by-side`), dan AMD-chip, CPU als laatste. Gemeten op de Mac (19 min les): VideoToolbox 5,6× realtime en 193 MB, libx264 veryfast 11× en ~4× kleiner → libx264. Versturen 311 MB in 15 s, terug 193 MB in 14 s. Laptop → Mac op 60 s: 12 s. Mislukte pogingen loggen nu de reden van ffmpeg. Op de laptop viel VA-API eenmaal terug naar de CPU; niet na te bootsen.
- Velox-downloads hebben "duur onbekend" in de mp4-kop (mux.js): mpv toont 19 min, andere spelers 13 u 15. Niet aangepast (eigenaar: laat maar).
- Keuze eigenaar: Stop op een lopende les = stoppen en vergeten. Transcriberen: map gewist, opname op `inbox_ignored.json` tot je hem met de hand toevoegt. Notities: alleen de delen van deze run weg. LaTeX: uit de wachtrij. Samenvoegen: stopt binnen 1 s op de laptop; op de Mac loopt ffmpeg uit en het resultaat wordt weggegooid. `Stopped` is een BaseException, zodat providers het niet opvangen. Knop in Bezig met 5 s Ongedaan maken. Bekeken op 375 en 1440 px, licht en donker.
- Getest: 276 Verbatim, 141 unit.

## 2026-11-02 — slides en webcam naast elkaar; kopbalk Verbatim
- Eigenaar: Kaltura-opnames met slides en webcam als twee beelden gaven vaak alleen de webcam. Oorzaak: Velox hield de laatst geladen stream bij en zag de tweede entry als een andere les.
- Velox 5.1.0: `shared/streams.js` houdt hoofdbeeld (de entry uit de URL van de speler, standaard groot = slides) en tweede beeld bij. Zonder Verbatim alleen de slides; met Verbatim-downloads eerst `<titel>.webcam.mp4`, dan `<titel>.mp4`, één voortgangsbalk (0–50 %, 50–100 %).
- Verbatim `pair.py`: wacht tot beide klaar zijn, zet ze naast elkaar (slides 1080 px hoog, webcam 640 px breed, gecentreerd op zwart), geluid van de slides of anders van de webcam. AMD-chip via VA-API, anders libx264. Gemeten: 11× realtime (60 s in 5,5 s), dus ~11 min voor 2 u. Resultaat krijgt de naam van de slides; originelen blijven als `.slides`/`.webcam`. Lukt het niet, dan de slides alleen.
- Niet getest op een echte Toledo-opname met twee beelden: de regel "entry uit de speler-URL = slides" is een aanname.
- Verbatim-kopbalk: doorzichtig in rust (geen grijze band in donker), materiaal in paginakleur + haarlijn als er inhoud onder schuift; zijbalk boven de balk zodat zijn schaduw niet wordt afgesneden (`packages/design`).
- Getest: 141 unit, 100 Velox + 33 e2e, 270 Verbatim, 134 schermtests.

## 2026-11-02 — twee actieve semesters, DNS op de laptop
- Eigenaar laadde het rooster op twee toestellen voor ze gesynct waren: twee actieve semesters (één met 7 vakken en 0 lessen), de hub gaf 14 vakken aan Verbatim. Nu wint overal de nieuwste upload (`domain/semesters.js`, zelfde regel in `hub/store.py`); Sequo zet de oudere uit en synct dat. Hub geeft nu 6 vakken (1 verborgen). 141 unit, 17 hub, 134 schermtests.
- Verbatim: `~/Lectures/jobs/hub_sent.json` opzij (`.oud`), alle 10 lessen opnieuw gemeld aan de nieuwe hub.
- Laptop: NetworkManager overschreef `/etc/resolv.conf`, `macbook-pro-stan` onbereikbaar. Nu `systemd-resolved` met `dns=systemd-resolved`; naam en modelserver weer bereikbaar.

## 2026-11-02 — oude namen weg: alles heet Sequo en Velox
- Keuze eigenaar: ook technisch geen `inhaal` of `swiftskip` meer, verse start (nog niemand gebruikte de apps echt). Mappen `apps/sequo` en `apps/velox`, Dexie-database `sequo`, opslagsleutels, berichtkanaal `velox-sequo`, event-bron `velox`, Pages-pad `/trivium/sequo/`, feed `site/velox/updates.json`, add-on-id `velox@stanloobuyck.github.io`. Hub heet `trivium-hub` (map, LaunchDaemon `be.trivium.hub`, `/api`-antwoord).
- "Inhaalplan" en "inhalen" blijven: gewoon Nederlands. Historische regels in de changelogs en de git-geschiedenis houden de oude namen.
- Getest: 137 unit, 94 Velox + lint schoon, 31 Velox-e2e, 16 hub, 265 Verbatim, 134 schermtests. Signed xpi nagekeken: id `velox@…`, update-adres `/trivium/velox/`. Live: site, `/sequo/`, feed en xpi geven 200, geen oude namen op de pagina.
- Releases: Velox 5.0.0 (nieuw add-on-id, dus nieuwe installatie), Sequo 1.0.0 als `sequo-v1.0.0`; `inhaal-v1.0.0` en `swiftskip-v4.1.0`–`4.5.0` verwijderd.
- Mac: hub verhuisd naar `~/trivium-hub` met LaunchDaemon `be.trivium.hub`, lege database, zelfde poort 8788; `/api/health` antwoordt `trivium-hub`. `~/inhaal-hub` blijft als back-up.
- Fouten onderweg: rename-commit gepusht vóór de Velox-release, dus twee CI-runs faalden op de lege feed en de oude site wees even naar verwijderde downloads; daarna faalde de Pages-deploy op een netwerkfout (opnieuw gestart, nu groen). Sudo via `!` werkt niet: geen terminal, eigenaar draait sudo-commando's voor de Mac in een eigen venster.

## 2026-11-02 — fase 6: landingspagina, privacy en READMEs
- Eigenaar: pagina's, Velox-download en Les 11 in de nieuwe stijl in orde. Sequo 1.0.0 uitgebracht als `inhaal-v1.0.0` (zonder "Latest": dat blijft bij Velox). Fase 6 afgevinkt in `PLAN.md`.
- CI: één publicatie faalde omdat de vorige nog bezig was; die commit raakte alleen `CHANGELOG.md`, de site was al juist.
- Keuzes eigenaar: geschreven voor KU Leuven-studenten, link zelf delen (`noindex` blijft); één pagina met drie kaarten.
- Landingspagina in NL en EN (browsertaal, NL/EN-knop, keuze bewaard). Velox-versie en downloads komen bij de build uit `updates.json` (`scripts/build-site.mjs`), dus elke release werkt de pagina bij. Op brede schermen drie kolommen.
- Privacypagina `/privacy/` met een stuk per app, ankers vanaf elke kaart. Feiten nagekeken in de code: Sequo heeft geen netwerkverkeer buiten een eigen hub; Velox alleen bij downloads (nu ook slides) en de updatecheck van de browser; Verbatim stuurt alleen naar diensten die je zelf instelt.
- READMEs: Sequo nieuw (NL + EN); Velox heet Velox, downloads via de Trivium-pagina (de links wezen nog naar 4.4.1), dode link naar `ROADMAP.md` weg; Verbatim met experimentele intro en Nederlandse handleiding.
- Getest: 137 unit (5 nieuw voor de site), 94 Velox, 265 Verbatim; beide pagina's op 375 en 1440 px, licht en donker, NL en EN: 0 px overloop, geen fouten of 404's.

## 2026-11-02 — LaTeX-notities naast de slides
- Eigenaarsoordeel Les 11: oké, niet wauw; te woordig, meer structuur. Studeert met de slides ernaast. Sequo-badges werken.
- Oorzaken in Les 11: 4 volledige codeblokken en elke FSM twee keer (TikZ en uitsnede van dezelfde slide), bullets als kleine alinea's, elk onderwerp een andere vorm.
- Keuze eigenaar: alleen aanvullen. Geen code of figuren van de slide meer, wel verwijzing en wat de lector toevoegt; hoogstens 4 regels code waar de uitleg over gaat. Elk onderwerp: `\kernpunt`, korte bullets, `\valkuil`. Slides die de lector niet besprak: één regel "Niet besproken". Budget 3 pagina's per uur, minimum 2.
- `check.py` meldt gekopieerde code, slidefiguren en onderwerpen zonder kernregel: 11 problemen op de oude Les 11.
- Keuze eigenaar: per vak instelbaar ("LaTeX-notities: Naast slides / Zonder slides" in Instellingen → Vakken), voor vakken zoals religie. Zonder slides = zelfstandig leesbaar, code en figuren mogen, 5 pagina's per uur.
- Getest: 265 Verbatim-tests, sjabloon compileert met de nieuwe macro's, vakformulier op 375 en 1440 px licht en donker (0 px overloop, geen JS-fouten). Niet getest: een echte run in de nieuwe stijl.

## 2026-11-02 — LaTeX-skill getest op een echte les, Opus als standaard
- Eerste echte run (Sonnet, Les 11 deel 3): tijdstempels overgenomen uit een foute slidekoppeling; de koppeling zelf in Verbatim is niet aangepast, 4 pagina's tegen budget 1,5, lege regels door `\slide`.
- Nieuw: `scripts/check.py` (tijden, slides, eigen macro's, budget), transcript bepaalt volgorde, slide-only samen op het einde, `\slide{p}{}` zonder tijd, `\tijd` in het sjabloon, sjabloon altijd bijgewerkt, rapport in `.work/<les>/report.md`, Claude bekijkt twee pagina's.
- Vergelijking zelfde les: Sonnet 3 pagina's, 1 checkprobleem, geen `% CHECK`; Opus 2 pagina's, 0 problemen, omgekeerde Mealy-regel in het transcript gevonden, `typedef wire` gemarkeerd, maar schrapte figuren om binnen 2 pagina's te blijven. Daarom minimum 3 pagina's. Duur Opus: 408-435 s.
- Standaard nu Opus 5.5. Les 11 deel 3 opnieuw gemaakt: 3 pagina's, 0 problemen. Eén les nagekeken: de keuze rust op deze ene vergelijking.

## 2026-11-02 — één notatie voor duur
- Keuze: `1u 55` (en: `1h 55`) in Sequo en Verbatim. Verbatim had `1:55` en `1 h 55 min`. Posities in een opname blijven `m:ss`.

## 2026-11-02 — LaTeX-notities in Verbatim
- Correctie: de eerste aanpassing vertrok van de oudere lokale kopie (18 okt). De gesyncte versie (25 okt) had al dichtheidsregels; die zijn nu overgenomen. De gesyncte kopie heeft geen scripts en blijft los van de repo.
- Uit een review: paden via `<skill>`, `tectonic` zonder `cd`, maximaal 3 pogingen per crop, standaardopmerkingen in de taal van de les. Verbatim geeft het aantal pagina's vooraf mee voor het paginabudget.
- Skill `latex-notes` zit nu in `apps/verbatim/skill/`; `~/.claude/skills/latex-notes` is een link daarnaartoe (install.sh legt die). De kopie in de anthropic-skills-plugin blijft apart.
- Fouten uit de review opgelost: PPTX-afbeeldingen ontbraken bij een Verbatim-les; niet-besproken slides hadden geen tekst; previews van meerdere decks overschreven elkaar. Nieuw: pagina's van andere lessen blijven weg uit grote decks.
- Knop LaTeX-notities op het lesscherm: wachtrij, Claude Sonnet 5.5 via `claude -p`, stappen op Bezig, daarna PDF openen. Voorbereiding en cursusmap doet Verbatim zelf, dat spaart quota. Zelfde daglimiet en schema als de notities. Resultaat in `~/Documents/Lesnotities/<vak>/`.
- Getest: prepare op 3 echte lessen (PDF, PPTX, twee decks), sjabloon compileert met Tectonic, rechten met een kleine echte run (Read, Write, tectonic mogen; `touch` geweigerd). 261 Verbatim-tests. Nog geen volledige LaTeX-run met Sonnet: die kost quota.
- Sequo: een opname zonder "Les" telt nu op het laatste getal in de naam; les 5 opnieuw gemeld met nummer 5.

## 2026-11-02 — Verbatim-badges op de juiste les in Sequo, tab Bezig
- Eigenaarstest: niets van Verbatim te zien bij de juiste les. De berichten kwamen aan (9), maar 7 badges stonden op latere lessen (les 1 op 4 november) en 1 ontbrak: de nummering was verschoven na het verwerken, en een bericht werd nooit opnieuw bekeken.
- Sequo rekent de badges nu bij elke sync uit alle `notes.ready`-berichten (`reconcileNotes`). Gesimuleerd op een privékopie van de hubdata: 7 weg, 8 gezet, tweede ronde 0 wijzigingen.
- Beperking: een opname zonder lesnummer in de titel en zonder les op die datum vindt geen les.
- Verbatim: tab Bezig is een eigen pagina met alleen lopende lessen, altijd zichtbaar; Bibliotheek heeft nog één knop ernaartoe. Bekeken op 375 en 1440 px, licht en donker.
- Slides: elke les bewaart al een eigen kopie in `jobs/<les>/slides/` (9 van 9 nagekeken), bruikbaar voor de LaTeX-skill.
- Tests: 132 unit, 234+ Verbatim, 133 schermtests; `design light` faalde eenmalig in Firefox, daarna 3/3 goed.

## 2026-11-02 — slides over meerdere lessen
- Keuze eigenaar: een les zonder eigen slides wacht 30 minuten en krijgt dan alle slides van het vak; de uitlijning kiest. Voorheen wachtte ze voor altijd.
- `Les 3-6` telt nu voor les 3 t/m 6 (ook `t/m`, `tot`, `–`). Wachttijd loopt vanaf de aankomst in de map, niet vanaf de oude bestandsdatum.

## 2026-11-02 — Verbatim toont weer wat het doet
- Eigenaarstest: keten werkt, opname en slides samen opgepikt ("19 pages, 40 terms"). De run hergebruikte de bestaande lesmap, audio en transcript: geen dubbele les, de eerdere waarschuwing was fout.
- Eigenaar vond de voortgang onduidelijk. Oorzaken: percentage alleen bij transcriberen, stap "termen" ontbrak (scherm toonde dan Audio), bij minder animatie was de balk vol.
- Nu: statusregel met stap, percentage en deel ("Termen nakijken · 28% · deel 12 van 40"), vijf stappen, zachte puls bij minder animatie, oude `stepsHtml` weg.
- Bekeken op 375 en 1440 px, licht en donker, met nagebootste taken: 0 px horizontale overloop, geen JS-fouten.
- Knop Bestanden: opende niets bij een les die nog bezig is (map `outputs` bestaat dan niet) en meldde toch ok; opent nu de lesmap. Op een afgewerkte les bevestigd: venster `outputs` ging open.

## 2026-11-02 — Velox 4.5.0 uit
- Dubbele opname verwijderd, Verbatim geïnstalleerd, worker herstart (daemon-reload nodig).

## 2026-11-02 — slides-knop getest, Verbatim wacht niet meer zonder lesnummer
- Eigenaarstest in Zen: knop werkt op echt Toledo, ook met PPTX. Tabbalk op de iPhone is goed. Namen: volgens de eigenaar klaar.
- Verbatim bleef wachten bij een opname zonder lesnummer naast genummerde slides, en dat veranderde nooit. Nu krijgt zo'n opname alle slides en kiest de uitlijning. Een opname met een nummer wacht nog wel op zijn eigen slides.
- De test-opname bleek byte-gelijk aan een les die al in de bibliotheek staat; na de herstart zou ze opnieuw verwerkt worden. Tests: 233 Verbatim.

## 2026-11-02 — slides-knop in Velox
- Keuze eigenaar, na de tests: een knop op de Toledo-rij in plaats van de keuzelijst. Elk vak heeft een andere indeling, dus Velox kan niet betrouwbaar raden wat slides zijn. De eerdere keuzelijst en de aanvinkregel hieronder vervallen.
- Knop alleen bij PDF en PPTX, in een open map, met "Downloads naar Verbatim" aan. Overschrijft dezelfde naam. Een loginpagina i.p.v. een bestand wordt weer gewist.
- API-tests op Toledo gaven geen lijst: relatieve adressen kwamen op de CDN uit; waarom is niet bewezen. Niet verder onderzocht, de knop heeft de API niet nodig.
- Tests: 94 unit en 31 e2e SwiftSkip, 128 unit, lint 0 fouten. Niet getest: echt Toledo, Zen, PPTX-label, schermformaten van de knop op Toledo.
- Lek: het testscript bewaarde een toegangscode van de Toledo-sessie in `fixtures/private/` (niet in de repo); gewist uit de test-JSON, staat nog in de opgeslagen pagina.

## 2026-11-02 — slides-stroom gekozen
- Keuze eigenaar: keuzelijst bij de download, best passende slides al aangevinkt, één tik om te bevestigen. Niet volledig automatisch: een verkeerde keuze zou pas in Verbatim opvallen.
- Echte vakpagina bekeken: Toledo is Blackboard Ultra, bestanden hebben een `bbcswebdav`-link, maar die staan alleen in de pagina als de map openstaat.
- Dat vak heeft slides per hoofdstuk, niet per les, dus aanvinken op lesnummer lukt daar niet. Beslissing: titels met een lesnummer → die ene; anders → alle slides van het vak, want Verbatim neemt dan alle decks en de uitlijning kiest wat getoond werd. Slides eerst downloaden, dan de opname, zodat de inbox niet zonder begint.
- Nog onbekend: of de REST-API van Blackboard werkt met de Toledo-sessie. Test: `fixtures/private/toledo-test.js`.

## 2026-11-02 — Velox 4.4.1, oude repo's weg
- Keuze eigenaar: niemand gebruikt nog oude Velox-versies, dus de repo's mochten weg. Volgorde: eerst 4.4.1, anders hadden de knoppen in 4.4.0 naar een dode pagina gewezen.
- Afwijking van de vorige aanname: Velox 4.3.0 stond in Zen op uitgeschakeld door de gebruiker, niet door de tijdelijke add-on. Oplossing: 4.4.0 rechtstreeks geïnstalleerd; knop vastgemaakt via het Extensies-paneel (`extensions.unifiedExtensions.button.always_visible`).
- Velox 4.4.1 gereleased: gecontroleerd in de echte `.xpi` (geen links naar de oude repo) en in de updatefeed. GitHub-repo's `studie-ecosysteem` en `SwiftSkip` verwijderd. Eén contributor op `trivium`.

## 2026-11-02 — oude repo's voorbereid om te verwijderen
- Eigenaar: `studie-ecosysteem` en `SwiftSkip` mogen weg. Links in Velox en README's wijzen nu naar `trivium`, de 4.0.x-regels met downloads uit de oude repo zijn uit `updates.json`. Velox 4.4.1 moet dit nog uitbrengen; daarna de repo's verwijderen en de valkuilen in `CLAUDE.md` bijwerken.
- `gh`-token mist nog de scope `delete_repo`.
- Lokale mappen `~/Documents/SwiftSkip` en `SwiftSkip_Firefox` verwijderd (eerst gecontroleerd: niets ongepusht, `.env` gelijk aan die in `apps/swiftskip`).

## 2026-11-02 — tabbalk lager op de iPhone, oude Verbatim-map weg
- Tabbalk: nieuw token `--dock-bottom`, de balk gaat 12 px in de safe area. Gemeten met gesimuleerde safe area van 34 px: 46 → 22 px van de onderrand; zonder safe area 12 px. Plusknop, toast en selectiebalk rekenen op hetzelfde token.
- `~/Documents/lecture-transcriber` verwijderd (3,0 GB, had geen remote). Eerst gecontroleerd: notities byte-gelijk in `apps/verbatim`, geen actieve verwijzingen. Repo's `studie-ecosysteem` en `SwiftSkip` blijven, die bedienen oude Velox-installaties.
- Na de maphernoeming wezen de venvs van hub en Verbatim nog naar het oude pad: opnieuw geïnstalleerd.
- Velox in Zen: een tijdelijke add-on wint van de geïnstalleerde 4.3.0 met het oude logo. Gepubliceerde 4.4.0 gecontroleerd: nieuw logo, updatefeed geeft 4.4.0.
- Eenmalig mislukte schermtest "knop Bekeken ... overleeft herladen" (wacht vast 200 ms op de opslag): daarna 6/6 goed, ook zonder deze wijziging. Niet aangepast.
- Tests: 128 unit, 134 schermtests, 233 Verbatim.

## 2026-11-02 — menu altijd zichtbaar, instellingen in tabs, map Trivium
- Verbatim: het menu blijft ook op het lesscherm staan. De twee kolommen van het lesscherm beginnen nu vanaf 1300 px.
- Sequo en Verbatim: instellingen in vier tabs met één onderwerp tegelijk, in één kolom van 720 px; uitlegteksten bij secties weg in Verbatim.
- Vakken staan overal op alfabet, ook vakken zonder open lessen (Sequo: sneltoets 1-9 volgt die volgorde).
- Map hernoemd naar `~/Documents/trivium`; `lecture` opnieuw geïnstalleerd omdat de editable install naar het oude pad wees.
- Tests: 128 unit, 134 schermtests, 233 Verbatim.

## 2026-11-02 — Velox 4.4.0 en repo Trivium
- Velox 4.4.0 gereleased, met update-adres op `/trivium/`. Repo hernoemd naar `trivium`. De kleine repo `studie-ecosysteem` bewaart het oude update-adres voor versies t/m 4.3.0.

## 2026-11-02 — Verbatim en Sequo als tweeling
- Bibliotheek heeft nu dezelfde opbouw als het overzicht: titel, keuzeknoppen en lijst links, getalkaart rechts. Rijen, velden en groepstitels op dezelfde maten.
- Gemeten op 1440 px: overzicht 234 van 252 waarden gelijk, instellingen 162 van 168, de zijbalk volledig. De rest komt door de inhoud (meldingen, rijen met drie regels).
- Sequo: titel is nu Overzicht, en "Inhaalplan" hersteld (de hernoeming had er Sequoplan van gemaakt).
- Repo blijft voorlopig `studie-ecosysteem`: het update-adres van Velox staat vast in elke installatie en Pages stuurt niet door. Eerst release 4.4.0 met het nieuwe adres.

## 2026-11-02 — vakkleuren, logo's en Swiftskip-instellingen
- Namen (keuze eigenaar): het geheel heet Trivium, Inhaal wordt Sequo, SwiftSkip wordt Velox, in alles wat je ziet. Mappen, id's, opslag en adressen blijven `inhaal`/`swiftskip`. Logo A gekozen.
  Beschikbaarheid van de namen is niet gecontroleerd: nog doen vóór fase 6.
- Vakkleuren: de hub geeft `colorKey` mee, Verbatim haalt ze op via `/api/course-colors` (zelfde koppeling als het importeren: code, dan naam) en onthoudt ze.
  Niets nieuws in `courses.yaml`, dus de worker hoeft niet te herstarten.
- Logo's: Verbatim blauw met de hoek van Inhaal, nieuw SwiftSkip-icoon (`apps/swiftskip/branding/icon.svg`, PNG's opnieuw gemaakt). Boekje past nu binnen het raster.
- SwiftSkip: downloadknop terug linksboven. Instellingen tonen op de laptop één sectie tegelijk: de pagina was te kort om naar Links, Sites of About te scrollen.
  Nieuw: Weergave (systeem, licht, donker) voor popup, instellingen en welkomstpagina. De overlay blijft donker.
- Gemeten: zijbalk 288 px op 1000, 1440 en 1920 px in Inhaal en Verbatim, 288 px in SwiftSkip.
- Tests: 128 unit, 89 + 27 SwiftSkip, 233 Verbatim, 16 hub.

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
