import type { JobEventRead } from "../api/types";
import { redactObject, redactText } from "../utils/redaction";

export function JobTimeline({ events }: { events: JobEventRead[] }) {
  const sorted = [...events].sort((left, right) => left.id - right.id);

  return (
    <ol className="timeline" aria-label="Job timeline">
      {sorted.map((event) => (
        <li key={event.id}>
          <div className="timeline-state">
            <span>{event.from_state ?? "created"}</span>
            <span aria-hidden="true">-&gt;</span>
            <strong>{event.to_state}</strong>
          </div>
          <pre>{redactText(redactObject(event.payload))}</pre>
        </li>
      ))}
    </ol>
  );
}
