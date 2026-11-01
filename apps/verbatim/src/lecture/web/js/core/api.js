// The local JSON API (webapp.py). Writes carry the x-lecture-ui header the server requires.
export async function api(path, opts = {}) {
  const init = { ...opts, headers: { "x-lecture-ui": "1", ...(opts.headers || {}) } };
  if (opts.json !== undefined) {
    init.method = init.method || "POST";
    init.body = JSON.stringify(opts.json);
    init.headers["content-type"] = "application/json";
  }
  const r = await fetch(path, init);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch { /* not JSON */ }
    throw new Error(msg);
  }
  return r.json();
}
export const post = (path, json = {}) => api(path, { method: "POST", json });
