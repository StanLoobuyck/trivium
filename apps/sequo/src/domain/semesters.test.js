import { describe, expect, it } from "vitest";
import { pickActiveSemester } from "./semesters.js";

const sem = (id, createdAt, extra = {}) => ({ id, createdAt, isActive: true, deletedAt: null, ...extra });

describe("actief semester", () => {
  it("kiest de nieuwste upload als twee toestellen elk een semester actief zetten", () => {
    const { active, stale } = pickActiveSemester([sem("a", "2026-11-02T16:44:40.654Z"), sem("b", "2026-11-02T16:47:39.430Z")]);
    expect(active.id).toBe("b");
    expect(stale.map((s) => s.id)).toEqual(["a"]);
  });

  it("geeft op elk toestel hetzelfde, ook bij gelijke tijd", () => {
    const list = [sem("a", "2026-11-02T16:00:00.000Z"), sem("b", "2026-11-02T16:00:00.000Z")];
    expect(pickActiveSemester(list).active.id).toBe(pickActiveSemester([...list].reverse()).active.id);
  });

  it("negeert verwijderde en niet-actieve semesters", () => {
    const { active, stale } = pickActiveSemester([
      sem("a", "2026-11-03T00:00:00.000Z", { deletedAt: "2026-11-03T01:00:00.000Z" }),
      sem("b", "2026-11-04T00:00:00.000Z", { isActive: false }),
      sem("c", "2026-11-01T00:00:00.000Z"),
    ]);
    expect(active.id).toBe("c");
    expect(stale).toEqual([]);
  });

  it("geeft niets zonder semester", () => {
    expect(pickActiveSemester([])).toEqual({ active: null, stale: [] });
  });
});
