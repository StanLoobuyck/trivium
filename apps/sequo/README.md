# Sequo

_English: [README_EN.md](README_EN.md)_

Welke lessen moet ik nog inhalen? Sequo leest je rooster, zet elke voorbije les op je lijst en toont bovenaan in één
getal wat er nog openstaat. Eén tik vinkt een les af.

**Openen:** [stanloobuyck.github.io/trivium/sequo/](https://stanloobuyck.github.io/trivium/sequo/). Werkt op iPhone,
Android en laptop, ook offline. Geen account: alles blijft in je browser.

> Technisch heet Sequo `sequo` (map, opslag en adres), zodat bestaande installaties blijven werken.

## Beginnen

1. **Op je beginscherm zetten.** iPhone: tik in Safari op *Deel* → *Zet op beginscherm*. Doe dat zeker: anders kan
   Safari je gegevens wissen als je de app een week niet opent. Android en laptop: *Installeren* in het browsermenu.
2. **Rooster uploaden.** Exporteer je rooster als `.ics`-bestand (bij de KU Leuven via TimeEdit) en kies het in Sequo.
   Voorbije lessen komen vanzelf op je lijst. Begint je export later dan het semester, dan kan je een tweede `.ics`
   als aanvulling uploaden of lessen zelf toevoegen.
3. **Afvinken.** Tik op een les als je ze gezien hebt. Vergist? Tik op *Ongedaan* in de melding onderaan.

## Wat nog meer

- **Per vak** zie je wat openstaat, met een eigen kleur. Lessen die uit je rooster verdwijnen, krijg je eerst te zien
  voor ze als geschrapt gemarkeerd worden.
- **Koppelen met [Velox](../velox/README_NL.md):** Instellingen → *Koppel met Velox*. Opnames die je op Toledo
  bekijkt, worden dan vanzelf afgevinkt.
- **Back-up:** Instellingen → Gegevens → *Exporteer back-up (JSON)* en *Herstel back-up*.
- **Sneltoetsen op de laptop:** J en K om te bewegen, X of spatie om af te vinken, N om toe te voegen, 1 tot 9 voor een
  vak, Z om ongedaan te maken.

## Privacy

Sequo stuurt niets naar de maker of naar derden: geen account, geen statistieken. Zie het
[privacybeleid](https://stanloobuyck.github.io/trivium/privacy/#sequo).

## Ontwikkelen

Vanuit de root van de repo:

```bash
npm install
npm run dev        # Sequo lokaal
npm test           # domeinlogica (Vitest)
npm run build      # bouwt _site/
npm run test:e2e   # schermen op 375 en 1440 px, licht en donker (Playwright)
```

Alle rekenlogica zit in `src/domain/` als pure, geteste functies. Opslag: Dexie op IndexedDB. Stijl:
`packages/design`.

Sequo is een onafhankelijk studentenproject ([MIT-licentie](../../LICENSE)), los van de KU Leuven.
