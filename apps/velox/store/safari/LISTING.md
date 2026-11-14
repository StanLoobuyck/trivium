# Velox in the Mac App Store: store listing

Velox for Safari is a macOS app that contains the Safari extension. It is published under the account holder's
Apple Developer account (individual) with Apple's **Safari Web Extension Packager** in App Store Connect: we upload
the extension as a zip and Apple builds and signs the app. No Xcode, no certificates, no API key.
(`scripts/safari-mac.sh` stays for unsigned local testing on the Mac.)

## Once: role and app record

1. **Account holder:** Users and Access → People → the developer → role **App Manager** (create apps, edit the
   listing, upload, submit; no finances, no users).
2. App Store Connect → Apps → **+** → New App: platform **macOS**, name **Velox – Lecture Recordings** ("Velox" is taken), primary language **English (U.K.)**,
   bundle ID **be.trivium.velox**, SKU **velox-safari**, user access Full.

## Each version

1. `node scripts/build.js safari --zip` → `web-ext-artifacts/velox-safari-<version>.zip` (manifest at the root,
   icons up to 1024 px for the app icon). The version in the store comes from `manifest.json`.
2. **Account holder** (an App Manager gets "failed to create packaging job", 2026-11-14): Users and Access → **Xcode Cloud** tab → Safari Web Extension Packager → **Upload** → the zip. Use Chromium or
   Safari: uploads from Firefox on Linux fail with "NetworkError" (Apple forums, Aug 2026). Packaging uses the
   25 h/month of Xcode Cloud in the membership.
3. When packaging is done, the build is in TestFlight. Version page → Build → pick it, fill in "What's New" (not for
   the first version), Add for Review → Submit. Users get it through the App Store's automatic updates.

## App Information

- **Name:** Velox – Lecture Recordings (in Safari itself: Velox)
- **Subtitle** (max 30): Shortcuts for lecture videos
- **Category:** Productivity; secondary: Education
- **Content rights:** "Does your app contain, show, or access third-party content?" → Yes; "Do you have all necessary
  rights?" → Yes (Velox only plays and saves recordings the signed-in user already has access to).
- **Age rating:** every question None / No → 4+.

## Pricing and Availability

- **Price:** Free (USD 0)
- **Availability:** all countries or regions

## App Privacy

- **Privacy policy URL:** https://stanloobuyck.github.io/trivium/privacy/#velox
- **Data collection:** No, we do not collect data from this app → "Data Not Collected".

## Version page (English (U.K.))

**Screenshots** (1280×800, Mac): `../edge/screenshots/1-speed-en.png`, `2-shortcuts-en.png`, `3-download-en.png`.
Not `4-popup`: in Safari the download runs from the player, not the popup (guideline 2.3: no features the app
doesn't have).

**Promotional text**

Keyboard shortcuts, resume and speed memory for lecture recordings on Toledo and other Kaltura players.

**Description**

Velox makes lecture recordings on Toledo (KU Leuven) and other Kaltura players nicer to watch in Safari.

• Keyboard shortcuts: pause, skip 10 seconds, speed up or slow down, change the volume, jump to any point. They work as soon as the page is open, without clicking in the player first. Press ? to see them all; change them in the settings.
• Continue where you left off: reopen a lecture and it starts where you stopped.
• Remembers your playback speed.
• Download a lecture as an ordinary .mp4 file with a clear name (course – lecture – date), with the download button in the player, to watch offline or in QuickTime.
• Works on other sites with lecture videos too: click the Velox icon and choose "Enable on" followed by the site's name.

After installing, open Velox once and turn it on in Safari → Settings → Extensions.

Velox collects no personal data and sends nothing to the developer or anyone else. There are no accounts, no analytics and no tracking. Your settings and resume positions stay in Safari. A download fetches the recording from the same servers Safari already uses.

Velox is free and open source, made by a student, independent of KU Leuven.

**Keywords** (max 100 characters)

Toledo,KU Leuven,Kaltura,lecture,recordings,playback speed,shortcuts,video,download,student

**Support URL:** https://github.com/StanLoobuyck/trivium/issues
**Marketing URL:** https://stanloobuyck.github.io/trivium/
**Version:** any; it follows the build once one is attached
**Copyright:** filled in by the account holder (year and name)

## Version page (Dutch), optional localisation

**Promotietekst**

Sneltoetsen, verdergaan waar je was en snelheid onthouden voor lesopnames op Toledo en andere Kaltura-spelers.

**Beschrijving**

Velox maakt lesopnames op Toledo (KU Leuven) en andere Kaltura-spelers aangenamer om te kijken in Safari.

• Sneltoetsen: pauzeren, 10 seconden springen, sneller of trager, volume, naar elk punt springen. Ze werken zodra de pagina open is, zonder eerst in de speler te klikken. Druk op ? om ze allemaal te zien; pas ze aan in de instellingen.
• Verdergaan waar je was: open een les opnieuw en ze start waar je stopte.
• Onthoudt je afspeelsnelheid.
• Download een les als gewoon .mp4-bestand met een duidelijke naam (vak – les – datum), met de downloadknop in de speler, om offline of in QuickTime te kijken.
• Werkt ook op andere sites met lesvideo's: klik op het Velox-icoon en kies "Aanzetten op" met de naam van de site.

Open Velox na het installeren één keer en zet het aan in Safari → Instellingen → Extensies.

Velox verzamelt geen persoonsgegevens en stuurt niets naar de maker of naar iemand anders. Geen account, geen statistieken, geen tracking. Je instellingen en waar je was blijven in Safari. Een download haalt de opname bij dezelfde servers die Safari al gebruikt.

Velox is gratis en open source, gemaakt door een student, los van de KU Leuven.

**Trefwoorden**

Toledo,KU Leuven,Kaltura,les,lesopnames,afspeelsnelheid,sneltoetsen,video,downloaden,student

## App Review Information

- **Sign-in required:** No (Velox itself has no account).
- **Notes:**

Velox is a Safari web extension for lecture recordings in Kaltura video players. Its main site, Toledo (KU Leuven's learning platform), needs a university login, so here is how to test without one:

1. Open Velox once, then enable it in Safari → Settings → Extensions.
2. In Safari, open a public page with an HTML5 video, for example https://www.w3schools.com/html/html5_video.asp
3. Click the Velox icon in the toolbar and choose "Enable on www.w3schools.com" (Safari asks permission for that site only).
4. Click on the page (outside the video), then press ] to speed up (an overlay shows "1.25×"), ← / → to skip 10 s, and ? to see all shortcuts.

The download button appears in Kaltura players that stream HLS. It saves the recording the signed-in student is already watching (their own course's lecture, which the university makes available to them) as one MP4 file for offline viewing. Velox doesn't bypass any protection or download from other video services.

Velox collects no data and makes no network requests of its own except fetching the recording the user asks to download. The localhost permission is for Verbatim, the developer's open-source companion app that runs on the user's own computer (port 7861).
