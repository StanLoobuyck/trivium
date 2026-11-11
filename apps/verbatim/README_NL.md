# Verbatim

_English: [README.md](README.md) (met alle technische details)_

> **Experimenteel.** Verbatim wordt elke dag gebruikt door de maker en er verandert nog veel. Verwacht ruwe randjes.
> **Windows:** een gewone installer, geen technische kennis nodig: zie de [handleiding en download](https://stanloobuyck.github.io/trivium/verbatim/).

Verbatim maakt van een lesopname (MP4) en de slides (PDF of PPTX) een transcript per slide, ondertitels en
studienotities. Uitschrijven gebeurt **lokaal op je NVIDIA-GPU** (faster-whisper large-v3). Notities schrijft Claude
via je eigen Claude-abonnement, met Gemini als reserve. Op vraag maakt Verbatim ook LaTeX-lesnotities per vak.

- **Werkt op:** Windows 10/11 ([installer](https://stanloobuyck.github.io/trivium/verbatim/): eerst Groq, als reserve de processor of NVIDIA-GPU van je
  laptop) en Linux (gemaakt op Arch), best met een NVIDIA-GPU. Zonder GPU heb je een gratis Groq-sleutel nodig.
- **Samen met [Velox](../velox/README_NL.md):** Velox bewaart Toledo-opnames en slides meteen in de inbox van
  Verbatim. **Met [Sequo](../sequo/README.md):** een les krijgt daar een badge zodra haar notities klaar zijn.

## Installeren (Windows)

Download de installer via de [handleiding](https://stanloobuyck.github.io/trivium/verbatim/) en volg de stappen daar. Verbatim kijkt zelf of er een nieuwe
versie is en toont dan een knop **Bijwerken**.

## Installeren (Arch Linux)

```bash
sudo pacman -S --needed ffmpeg uv libnotify             # nodig (plus de NVIDIA-driver voor lokaal uitschrijven)
sudo pacman -S --needed libreoffice-fresh pandoc-cli    # optioneel: PPTX-slides, export naar .docx/.pdf
sudo pacman -S --needed tectonic                        # optioneel: LaTeX-notities als PDF
apps/verbatim/scripts/install.sh
systemctl --user enable --now lecture-worker.service    # de achtergrondwerker
```

`install.sh` gebruikt een eigen Python 3.12 via uv (de systeem-Python blijft onaangeroerd), zet het commando
`lecture` in `~/.local/bin` en maakt `~/.config/lecture-transcriber/.env` aan. Het Whisper-model (~3 GB) wordt bij
het eerste gebruik gedownload. Daarna: `lecture doctor` controleert alles.

**Sleutels** (optioneel) in `~/.config/lecture-transcriber/.env`: `GROQ_API_KEY` (uitschrijven zonder GPU, reserve
voor notities) en `GEMINI_API_KEY` (reserve voor notities; gebruik een persoonlijk Google-account, bij KU
Leuven-accounts staat AI Studio vaak uit). Voor Claude-notities: installeer [Claude Code](https://claude.com/claude-code)
en log in met je eigen abonnement.

## Gebruiken

- Open **Verbatim** via je app-menu of met `lecture ui`. Voeg lessen toe (recente opnames kiezen of bestanden
  slepen, slides erbij) en kies wanneer de notities gemaakt worden: nu, vannacht of nooit. Je mag de browser sluiten:
  de werker doet de rest en geeft een melding per les.
- **Inbox:** zet een opname in `~/Lectures/inbox/<vak>/` en Verbatim pikt ze op. Velox bewaart opnames en slides
  in `~/Downloads/Verbatim/<vakcode>/` (zet *Downloads naar Verbatim* aan in Velox); ook die map wordt opgepikt.
  Slides in dezelfde map met hetzelfde lesnummer ("les 4") horen bij die les.
- Per les: de opname naast de notities, klik op een tijd om ernaartoe te springen. Tabbladen voor transcript,
  trefwoorden, kwaliteitscontrole en suggesties voor verkeerd verstane woorden.
- **LaTeX-notities:** de knop op een afgewerkte les. Resultaat in `~/Documents/Lesnotities/<vak>/`, één `main.pdf`
  per vak. Per vak kies je in Instellingen → Vakken of de notities **naast de slides** gelezen worden (kort, verwijzen
  naar de slide) of **zonder slides** (zelfstandig leesbaar).

## Privacy

Opnames en slides blijven op je computer. Audio gaat alleen naar Groq of naar een eigen modelserver als je dat
instelt; transcript- en slidetekst gaan naar de notitiedienst die je kiest (Claude, Gemini of Groq). Kijk de regels
van je onderwijsinstelling na voor het doorsturen van opnames, en denk eraan dat vragen uit de zaal stemmen van
medestudenten bevatten. Zie het [privacybeleid](https://stanloobuyck.github.io/trivium/privacy/#verbatim).

Verbatim is een onafhankelijk studentenproject ([MIT-licentie](../../LICENSE)), los van de KU Leuven.
