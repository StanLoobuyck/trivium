// Where Velox runs. Pure (used by the build script and the extension).

// Always on, granted at install: Toledo, KU Leuven's Kaltura (KAF) and
// Kaltura's own players/CDN — the latter also covers other schools that embed
// Kaltura in their learning platform.
export const REQUIRED_HOSTS = ["*://*.kuleuven.be/*", "*://*.kuleuven.cloud/*", "*://*.kaltura.com/*"];

// Verbatim, the lecture tool on your own laptop, at its default address. Match patterns can't hold a port, so the
// manifest covers all of 127.0.0.1 and localhost, and the content script only stays on Verbatim's port.
export const VERBATIM_HOSTS = ["http://127.0.0.1/*", "http://localhost/*"];
export const VERBATIM_PORT = "7861";

function local(url) {
  try {
    const { protocol, hostname, port } = new URL(url);
    return protocol === "http:" && ["127.0.0.1", "localhost"].includes(hostname) ? port : null;
  } catch {
    return null;
  }
}

// Lectures someone shared with you from their Verbatim, at <their hub>/share/ (Tailscale Funnel: always *.ts.net).
// The hub's name differs per person, so the pattern covers every *.ts.net host, but only its /share/ pages.
export const SHARE_HOSTS = ["https://*.ts.net/share/*"];

export function isSharePage(url) {
  try {
    const { protocol, hostname, pathname } = new URL(url);
    return protocol === "https:" && hostname.endsWith(".ts.net") && pathname.startsWith("/share/");
  } catch {
    return false;
  }
}

// A page on this laptop (127.0.0.1 / localhost)?
export const isLocalPage = (url) => local(url) !== null;
// Verbatim's own pages?
export const isVerbatim = (url) => local(url) === VERBATIM_PORT;

// Anything else is opt-in, one site at a time, from the popup.
export const OPTIONAL_HOSTS = ["*://*/*"];

// "https://example.edu/some/page" → "https://example.edu/*" (what we ask for).
export function originPattern(url) {
  try {
    const { protocol, host } = new URL(url);
    if (protocol !== "http:" && protocol !== "https:") return null;
    return `${protocol}//${host}/*`;
  } catch {
    return null;
  }
}

// "https://example.edu/*" → "example.edu"
export function patternHost(pattern) {
  return pattern.replace(/^[^:]+:\/\//, "").replace(/\/\*$/, "");
}

// Does a match pattern like "*://*.kaltura.com/*" cover this URL?
export function patternMatches(pattern, url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  const match = /^(\*|https?):\/\/(\*|(?:\*\.)?[^/*]+)\/(.*)$/.exec(pattern);
  if (!match) return false;
  const [, scheme, host] = match;
  if (scheme === "*" ? !["http:", "https:"].includes(parsed.protocol) : parsed.protocol !== `${scheme}:`) {
    return false;
  }
  if (host === "*") return true;
  if (host.startsWith("*.")) {
    const base = host.slice(2);
    return parsed.hostname === base || parsed.hostname.endsWith(`.${base}`);
  }
  return parsed.host === host || parsed.hostname === host;
}

// Is this URL one where Velox always runs?
export function isBuiltInSite(url) {
  return (
    isVerbatim(url) || isSharePage(url) || REQUIRED_HOSTS.some((pattern) => patternMatches(pattern, url))
  );
}
