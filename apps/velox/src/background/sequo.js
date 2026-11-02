// The optional link with Sequo: what to pass on, kept until Sequo has it.
// Without a link nothing is stored. See packages/contract/CONTRACT.md.

import { ext } from "../shared/ext.js";
import { addToQueue, buildRecording, createEvent, sequoPermission } from "../shared/sequo.js";

export const LINK_KEY = "sequoLink";
export const QUEUE_KEY = "sequoQueue";

export async function getSequoLink() {
  return (await ext.storage.local.get(LINK_KEY))[LINK_KEY] || null;
}

export function setSequoLink(address) {
  return ext.storage.local.set({ [LINK_KEY]: address });
}

export async function removeSequoLink() {
  const address = await getSequoLink();
  await ext.storage.local.remove([LINK_KEY, QUEUE_KEY]);
  if (address) await ext.permissions.remove({ origins: [sequoPermission(address)] }).catch(() => {});
}

// One writer at a time: reports from several tabs must not overwrite each other.
let queueWrites = Promise.resolve();
function changeQueue(change) {
  queueWrites = queueWrites.then(async () => {
    const queue = (await ext.storage.local.get(QUEUE_KEY))[QUEUE_KEY] || [];
    await ext.storage.local.set({ [QUEUE_KEY]: change(queue) });
  });
  queueWrites = queueWrites.catch(() => {});
  return queueWrites;
}

export async function reportToSequo(type, payload, { context, title, url }) {
  if (!(await getSequoLink())) return;
  const recording = buildRecording({
    code: context?.code,
    lecture: context?.lecture,
    recording: title,
    url,
  });
  if (!recording) return;
  const event = createEvent(type, recording, payload, {
    id: crypto.randomUUID(),
    occurredAt: new Date().toISOString(),
  });
  await changeQueue((queue) => addToQueue(queue, event));
}

export function forgetDelivered(ids) {
  const delivered = new Set(ids);
  return changeQueue((queue) => queue.filter((event) => !delivered.has(event.id)));
}
