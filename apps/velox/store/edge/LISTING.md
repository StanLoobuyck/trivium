# Velox in Microsoft Edge Add-ons — store listing

Everything to paste into Partner Center (Edge → Extensions → Create new extension). Package:
`velox-chrome-<version>.zip` from `npm run build` in `apps/velox` (the Chrome build; Edge takes it as is).
Images: `logo-300.png` (Extension Store logo) and `screenshots/` (1280×800; `-en` for English, `-nl` for Dutch).
Screenshots are remade with `STORE_SHOTS=1 npx playwright test store-shots`.

## Availability

- **Visibility:** Public
- **Markets:** all markets

## Properties

- **Category:** Productivity
- **Privacy policy:** Yes → https://stanloobuyck.github.io/trivium/privacy/#velox
- **Website:** https://stanloobuyck.github.io/trivium/
- **Support contact:** https://github.com/StanLoobuyck/trivium/issues
- **Mature content:** No

## Store listing — English (default)

**Short description**

Keyboard shortcuts, resume, speed memory and downloads for Toledo (KU Leuven) and other Kaltura lecture recordings.

**Description**

Velox makes lecture recordings on Toledo (KU Leuven) and other Kaltura players nicer to watch.

• Keyboard shortcuts: pause, skip 10 seconds, speed up or slow down, change the volume, jump to any point. They work as soon as the page is open, without clicking in the player first. Press ? to see them all; change them in the settings.
• Continue where you left off: reopen a lecture and it starts where you stopped.
• Remembers your playback speed.
• Download a lecture as an ordinary .mp4 file with a clear name (course – lecture – date), to watch offline or in any video player.
• Works on other sites with lecture videos too: click the Velox icon and choose "Enable on" followed by the site's name.

Velox collects no personal data and sends nothing to the developer or anyone else. There are no accounts, no analytics and no tracking. Your settings and resume positions stay in your browser. A download fetches the recording from the same servers your browser already uses.

Velox is free and open source, made by a student, independent of KU Leuven.

**Search terms** (max 7)

Toledo, KU Leuven, Kaltura, lecture recordings, playback speed, keyboard shortcuts, video download

## Store listing — Nederlands

**Korte beschrijving**

Sneltoetsen, verdergaan waar je was, snelheid onthouden en downloads voor Toledo (KU Leuven) en andere Kaltura-lesopnames.

**Beschrijving**

Velox maakt lesopnames op Toledo (KU Leuven) en andere Kaltura-spelers aangenamer om te kijken.

• Sneltoetsen: pauzeren, 10 seconden springen, sneller of trager, volume, naar elk punt springen. Ze werken zodra de pagina open is, zonder eerst in de speler te klikken. Druk op ? om ze allemaal te zien; pas ze aan in de instellingen.
• Verdergaan waar je was: open een les opnieuw en ze start waar je stopte.
• Onthoudt je afspeelsnelheid.
• Download een les als gewoon .mp4-bestand met een duidelijke naam (vak – les – datum), om offline of in elke videospeler te kijken.
• Werkt ook op andere sites met lesvideo's: klik op het Velox-icoon en kies "Aanzetten op" met de naam van de site.

Velox verzamelt geen persoonsgegevens en stuurt niets naar de maker of naar iemand anders. Geen account, geen statistieken, geen tracking. Je instellingen en waar je was blijven in je browser. Een download haalt de opname bij dezelfde servers die je browser al gebruikt.

Velox is gratis en open source, gemaakt door een student, los van de KU Leuven.

**Zoektermen** (max. 7)

Toledo, KU Leuven, Kaltura, lesopnames, afspeelsnelheid, sneltoetsen, video downloaden

## Notes for certification (for Microsoft's reviewers)

Velox adds keyboard shortcuts, resume, speed memory and an MP4 download to Kaltura lecture players. Its main
site, Toledo (KU Leuven), needs a university login, so here is how to test without one:

1. Open any public page with an HTML5 video, for example https://www.w3schools.com/html/html5_video.asp
2. Click the Velox icon in the toolbar and choose "Enable on www.w3schools.com" (this asks for permission for that site only).
3. Click on the page (outside the video), then press ] to speed up (an overlay shows "1.25×"), ← / → to skip
   10 s, and ? to see all shortcuts.

The download button appears on Kaltura streams (HLS); a public Kaltura player page shows it too.

Permissions:

- kuleuven.be, kuleuven.cloud, kaltura.com: the lecture pages and the Kaltura player where Velox runs.
- 127.0.0.1 and localhost: Verbatim, the developer's companion app that runs locally on port 7861 (Velox stays off
  on every other local port).
- _.ts.net/share/_: lecture pages that Verbatim users share from their own computer.
- Optional access to other sites: only after the user clicks "Enable on <site>" in the popup, for that one site.
- downloads: saving the lecture as .mp4. offscreen: joining the stream segments into one file. storage: settings
  and resume positions. scripting, activeTab: running on sites the user enabled.

Velox makes no network requests of its own except fetching the recording the user asks to download.
