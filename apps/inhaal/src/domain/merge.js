// Een (nieuwe) roosterimport samenvoegen met wat er al is: toevoegen en wijzigen, nooit dubbel of stilletjes weg.
export function mergeRooster(existing, events) {
  const known = new Map(existing.filter((s) => !s.deletedAt).map((s) => [s.id, s]));
  const add = [];
  const update = [];

  for (const event of events) {
    const session = known.get(event.uid);
    if (!session) add.push(event);
    else if (session.start !== event.start || session.end !== event.end || (session.location ?? "") !== event.location) {
      update.push({ id: session.id, start: event.start, end: event.end, location: event.location, online: event.online });
    }
  }

  // Alleen binnen de periode van dit bestand: een export die later start, wist de vroegere lessen niet.
  const uids = new Set(events.map((e) => e.uid));
  const from = events[0]?.start;
  const to = events.at(-1)?.end;
  const vanished = existing.filter((s) => !s.deletedAt && s.source === "rooster" && s.status !== "cancelled"
    && s.start >= from && s.end <= to && !uids.has(s.id));

  return { add, update, vanished };
}
