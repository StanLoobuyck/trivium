# Sequo

_Nederlands: [README.md](README.md)_

Which lectures do I still need to catch up on? Sequo reads your timetable, puts every past lecture on your list and
shows in one number at the top what's left. One tap ticks a lecture off.

**Open:** [stanloobuyck.github.io/trivium/inhaal/](https://stanloobuyck.github.io/trivium/inhaal/). Works on iPhone,
Android and laptop, also offline. No account: everything stays in your browser.

> Internally Sequo is called `inhaal` (folder, storage and address), so existing installs keep working.

## Getting started

1. **Add it to your home screen.** iPhone: in Safari tap *Share* → *Add to Home Screen*. Do this: otherwise Safari may
   erase your data if you don't open the app for a week. Android and laptop: *Install* in the browser menu.
2. **Upload your timetable.** Export your timetable as an `.ics` file (at KU Leuven through TimeEdit) and pick it in
   Sequo. Past lectures appear on your list by themselves. If your export starts later than the semester, upload a
   second `.ics` as a supplement or add those lectures yourself.
3. **Tick off.** Tap a lecture once you've watched it. Mistake? Tap *Undo* in the message at the bottom.

## More

- **Per course** you see what's open, in its own colour. Lectures that disappear from your timetable are shown to you
  before they're marked as cancelled.
- **Link with [Velox](../swiftskip/README_EN.md):** Settings → *Link with Velox*. Recordings you watch on Toledo are
  then ticked off by themselves.
- **Backup:** Settings → Data → *Export backup (JSON)* and *Restore backup*.
- **Keyboard shortcuts on a laptop:** J and K to move, X or space to tick off, N to add, 1 to 9 for a course, Z to undo.

## Privacy

Sequo sends nothing to the developer or to third parties: no account, no analytics. See the
[privacy policy](https://stanloobuyck.github.io/trivium/privacy/#sequo).

## Development

From the repository root:

```bash
npm install
npm run dev        # Sequo locally
npm test           # domain logic (Vitest)
npm run build      # builds _site/
npm run test:e2e   # screens at 375 and 1440 px, light and dark (Playwright)
```

All calculation logic lives in `src/domain/` as pure, tested functions. Storage: Dexie on IndexedDB. Style:
`packages/design`.

Sequo is an independent student project ([MIT license](../../LICENSE)), not affiliated with KU Leuven.
