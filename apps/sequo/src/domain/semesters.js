// Welk semester actief is. Twee toestellen die elk een rooster uploaden voor ze gesynct zijn, laten elk hun eigen
// semester actief achter. Overal dezelfde regel: de nieuwste upload wint, de rest is verouderd. Zie ook hub/store.py.
const newestFirst = (a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? "") || b.id.localeCompare(a.id);

export function pickActiveSemester(semesters) {
  const active = semesters.filter((s) => s.isActive && !s.deletedAt).sort(newestFirst);
  return { active: active[0] ?? null, stale: active.slice(1) };
}
