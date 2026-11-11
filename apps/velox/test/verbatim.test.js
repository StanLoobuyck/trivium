import { test } from "node:test";
import assert from "node:assert/strict";
import { autoVerbatim, verbatimRunning } from "../src/shared/verbatim.js";
import { normalizeSettings } from "../src/shared/settings.js";

const page = (status, body) => async () => ({ ok: status === 200, text: async () => body });

test("Verbatim is recognised by its own page, not by anything on the port", async () => {
  assert.equal(await verbatimRunning(page(200, "<html><title>Verbatim</title>")), true);
  assert.equal(await verbatimRunning(page(200, "<title>Something else</title>")), false);
  assert.equal(await verbatimRunning(page(500, "<title>Verbatim</title>")), false);
  assert.equal(
    await verbatimRunning(async () => {
      throw new TypeError("connection refused");
    }),
    false,
  );
});

test("turned on once when Verbatim runs and the user never chose", async () => {
  const saved = [];
  const save = async (patch) => saved.push(patch);
  const fresh = normalizeSettings({});
  assert.equal(fresh.downloadsToVerbatim, false);
  assert.equal(fresh.downloadsToVerbatimChosen, false);
  assert.equal(await autoVerbatim(fresh, save, async () => false), false);
  assert.deepEqual(saved, []);
  assert.equal(await autoVerbatim(fresh, save, async () => true), true);
  assert.deepEqual(saved, [{ downloadsToVerbatim: true }]);
});

test("a choice of the user is never overruled", async () => {
  let probed = false;
  const probe = async () => (probed = true);
  const off = normalizeSettings({ downloadsToVerbatim: false, downloadsToVerbatimChosen: true });
  assert.equal(await autoVerbatim(off, async () => assert.fail("saved"), probe), false);
  const on = normalizeSettings({ downloadsToVerbatim: true });
  assert.equal(await autoVerbatim(on, async () => assert.fail("saved"), probe), true);
  assert.equal(probed, false);
});

test("a choice made while Velox was looking wins", async () => {
  const fresh = normalizeSettings({});
  const chose = normalizeSettings({ downloadsToVerbatim: false, downloadsToVerbatimChosen: true });
  const result = await autoVerbatim(
    fresh,
    async () => assert.fail("saved"),
    async () => true,
    async () => chose,
  );
  assert.equal(result, false);
});
