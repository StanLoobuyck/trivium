// What the current browser build supports (__BROWSER__ is set at build time).

// Safari has no downloads API: lectures are saved like a normal download from
// the player frame (content/safari-download.js), always straight into
// Downloads. So no Verbatim course folders and no slide buttons there.
export const SUPPORTS_FOLDERS = __BROWSER__ !== "safari";
