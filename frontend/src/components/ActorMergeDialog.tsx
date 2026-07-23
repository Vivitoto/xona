import { useState } from "react";

import type { ActorRead } from "../api/types";
import { FormField } from "./FormField";

export function ActorMergeDialog({
  actor,
  onMerge,
  onClose,
}: {
  actor: ActorRead | null;
  onMerge: (duplicateActorId: number) => void;
  onClose: () => void;
}) {
  const [duplicateId, setDuplicateId] = useState("");

  if (!actor) {
    return null;
  }

  return (
    <div aria-modal="true" className="dialog-backdrop" role="dialog">
      <div className="dialog">
        <h2>Merge Actor</h2>
        <p className="muted">Merge a duplicate profile into {actor.canonical_name}.</p>
        <FormField label="Duplicate actor ID">
          <input
            inputMode="numeric"
            type="number"
            value={duplicateId}
            onChange={(event) => setDuplicateId(event.target.value)}
          />
        </FormField>
        <div className="button-row">
          <button
            type="button"
            onClick={() => onMerge(Number.parseInt(duplicateId, 10))}
          >
            Merge
          </button>
          <button className="secondary" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
