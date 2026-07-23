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
        <h2>合并演员</h2>
        <p className="muted">将重复档案合并到 {actor.canonical_name}。</p>
        <FormField label="重复演员 ID">
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
            合并
          </button>
          <button className="secondary" type="button" onClick={onClose}>
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
