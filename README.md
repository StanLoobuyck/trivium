# Trivium

Drie tools om je lessen bij te houden, elk apart te gebruiken. Downloads en uitleg:
**[stanloobuyck.github.io/trivium](https://stanloobuyck.github.io/trivium/)**.

| App | Wat het doet | Status |
| --- | --- | --- |
| [Sequo](apps/inhaal/README.md) | Toont welke lessen je nog moet inhalen | Publiek |
| [Velox](apps/swiftskip/README_NL.md) | Maakt Toledo-opnames kijkbaar en downloadbaar | Publiek |
| [Verbatim](apps/verbatim/README_NL.md) | Maakt transcripts en notities van opnames | Experimenteel |

Geen accounts, geen statistieken: zie het [privacybeleid](https://stanloobuyck.github.io/trivium/privacy/).
Een onafhankelijk studentenproject, los van de KU Leuven.

## English

Three tools to keep up with your lectures, each usable on its own: [Sequo](apps/inhaal/README_EN.md) (which lectures
you still need to catch up on), [Velox](apps/swiftskip/README_EN.md) (watch and download Toledo recordings) and
[Verbatim](apps/verbatim/README.md) (transcripts and notes, experimental). Downloads on the
[Trivium page](https://stanloobuyck.github.io/trivium/), [privacy policy](https://stanloobuyck.github.io/trivium/privacy/).

## Ontwikkelen

```bash
npm install
npm run dev        # Sequo lokaal
npm test           # domein, design, contract en site
npm run build      # bouwt _site/
npm run test:e2e   # schermen op 375 en 1440 px, licht en donker
```

Velox (`apps/swiftskip`) en Verbatim (`apps/verbatim`) bouw en test je in hun eigen map; zie hun README.

## Licentie

[MIT](LICENSE). Het lettertype Inter valt onder de [SIL Open Font License](packages/design/fonts/OFL.txt).
