// Safari only (content.js loads it in the Safari build): runs a lecture
// download in the player frame, because Safari has no downloads API. This frame
// may fetch the stream (the player does the same), and a link with `download`
// on a blob URL saves the file to Downloads like any page download.
// Every message goes frame → background; see background/safari.js for why.

import { cancelHlsDownload, runHlsDownload } from "../shared/downloader.js";
import { ext } from "../shared/ext.js";
import { downloadFilename } from "../shared/filename.js";

// onState(state): the tab's download state after this progress (for the player's control).
function progressReporter(onState) {
  return (progress) => {
    ext.runtime
      .sendMessage({ action: "safariDownloadProgress", ...progress })
      .then((reply) => {
        if (reply?.cancel) cancelHlsDownload(progress.jobId);
        if (reply?.state) onState(reply.state);
      })
      .catch(() => {});
  };
}

async function saveFile(url, title, extension) {
  const link = document.createElement("a");
  link.href = url;
  link.download = downloadFilename(title, extension);
  link.hidden = true;
  document.documentElement.append(link);
  link.click();
  link.remove();
  return null; // no download id: Safari offers no "show in folder"
}

// After "startLectureDownload": fetch each file the background hands out
// (webcam, then slides) until it has none left.
export async function runSafariDownloads(jobId, onState) {
  const onProgress = progressReporter(onState);
  for (;;) {
    const reply = await ext.runtime.sendMessage({ action: "safariNextDownload", jobId }).catch(() => null);
    const job = reply?.job;
    if (!job) return;
    const result = await runHlsDownload({ ...job, onProgress, saveFile }).catch((error) => ({
      ok: false,
      error: error?.message || String(error),
    }));
    await ext.runtime.sendMessage({ action: "safariDownloadDone", jobId, result }).catch(() => {});
  }
}

export function cancelSafariDownload(jobId) {
  cancelHlsDownload(jobId);
}
