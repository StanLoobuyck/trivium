# Contract tussen Sequo, Velox, Verbatim en de hub

Versie 0 (fase 0). Dit bestand en de JSON Schema's in `schema/` zijn de enige afspraak tussen de apps. Elke app
blijft alleen bruikbaar; een bericht dat niet aankomt, breekt niets.

## Vakcodes
- De vakcode uit het rooster is de gedeelde sleutel, bv. `H01L1a`. Eén vak kan meerdere codes hebben
  (`Course.codes[]`), omdat hoorcollege en oefenzitting elk een eigen code hebben.
- **Vergelijk codes altijd hoofdletterongevoelig.** Het rooster schrijft `H01L1a`, Toledo schrijft `[H01L1A]`.
  Sleutel = code zonder witruimte, in hoofdletters. Toon de schrijfwijze van het rooster.

## Sessie-id
- Sessie uit het rooster: `id` is de iCal-`UID`, bv. `1234567-7654321-0@timeedit.com`.
- Manueel toegevoegde sessie: `id` is een UUID.
- Het lesnummer is nooit een id: het wordt berekend en verschuift als een les geschrapt wordt.
- De `UID` bleef gelijk tussen twee exports: alle 154 gedeelde sessies, geen enkele verplaatst. De export is wel een
  schuivend venster: oude weken vallen eraf en nieuwe komen erbij. Een les die uit het bestand valt, is dus niet
  geschrapt; alleen wat binnen de periode van het bestand ontbreekt, wordt als geschrapt voorgesteld.

## Opname koppelen aan een les
Op volgorde: (1) vakcode + datum uit de Toledo-titel, (2) vakcode + lesnummer, (3) de gebruiker kiest, en Sequo
onthoudt die keuze. Een bericht met enkel een vakcode gaat dus nooit verloren. Daarom verwijzen opname-events naar
een opname en niet naar een sessie-id: Velox kent het rooster niet.

## Events
Elk event heeft dezelfde envelop (`schema/event.schema.json`):

| Veld | Betekenis |
| --- | --- |
| `id` | UUID, zodat een ontvanger dubbels herkent |
| `type` | Zie onder |
| `source` | `velox` of `verbatim` |
| `occurredAt` | ISO 8601-tijdstip met tijdzone |
| `payload` | Hangt af van `type` |

| Type | Route | Payload (bovenop de opname) | Effect in Sequo |
| --- | --- | --- | --- |
| `recording.watched` | Browser | `watchedFraction` ≥ 0,9 | Les afgevinkt, met undo-melding |
| `recording.progress` | Browser | `positionSec` | Positie bewaard als halverwege |
| `recording.downloaded` | Browser | `fileName` | Bestandsnaam bij de les |
| `notes.ready` | Hub | `kind` (`transcript` of `notes`), `verbatimJob` | Badge "notities" bij de les |

Elke payload bevat `recording`: `courseCode`, en waar gekend `title`, `recordedOn` (`JJJJ-MM-DD`), `lectureNumber`,
`part` (deel van een les), `fileName` en `url`. `recording.watched` en `recording.progress` dragen ook `durationSec`. Tijden en posities staan in seconden.

## Hubroute (Verbatim → Sequo)
Optioneel en alleen met een eigen hub. Verbatim stuurt `notes.ready` met `POST /api/events` en de koppelcode; wat niet
aankomt, wacht en wordt opnieuw gestuurd. Elk Sequo-toestel leest `GET /api/events?after=<cursor>` en zet de badge bij de
les: eerst op `fileName`, want die is gelijk aan de download van Velox, dan zoals bij opnames. Vindt Sequo geen les,
dan blijft de badge weg. `GET /api/courses` geeft Verbatim de vakken van het actieve semester: `name`, `codes`, `language`, `colorKey`.

## Browserroute (Velox ↔ Sequo)
De koppeling is opt-in. Sequo opent `https://www.kuleuven.be/#velox-koppel=<eigen adres, URL-gecodeerd>`. Velox
draait daar al en toont dan zijn instellingen met dat adres; de gebruiker bevestigt en de browser vraagt toestemming.
Daarna draait op dat adres alleen een klein script dat met de pagina praat via `window.postMessage`, met
`channel: "velox-sequo"`, op de eigen origin:

| Van | `from` / `type` | Inhoud | Betekenis |
| --- | --- | --- | --- |
| Sequo | `sequo` / `ready` | | Sequo luistert en wil de wachtrij |
| Velox | `velox` / `hello` | `version` | Gekoppeld |
| Velox | `velox` / `events` | `events[]` | De hele wachtrij; kan dubbels bevatten |
| Sequo | `sequo` / `ack` | `ids[]` | Verwerkt, Velox mag ze vergeten |

Een opname is herkenbaar aan `courseCode` + `title`. Sequo bewaart die koppeling bij de les.

Een les in delen (`part`, of meerdere opnames bij één les) wordt afgevinkt zodra de bekeken tijd samen 80% van de lesduur
haalt; tot dan staat ze op halverwege. Een opname uit één stuk volgt `recording.watched`.

## Regels
- Nieuwe velden mogen altijd; ontvangers negeren wat ze niet kennen.
- Een veld van betekenis veranderen of verwijderen = nieuw eventtype.
- Geen namen, e-mailadressen of andere persoonsgegevens in events.
