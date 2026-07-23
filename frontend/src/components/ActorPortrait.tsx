import type { ActorRead } from "../api/types";

export function ActorPortrait({ actor }: { actor: ActorRead }) {
  const source = actor.portrait_source_url;
  if (!source) {
    return (
      <div
        aria-label={`${actor.canonical_name} portrait missing`}
        className="portrait placeholder"
        role="img"
      >
        <span>No portrait</span>
      </div>
    );
  }

  return (
    <img
      alt={`${actor.canonical_name} portrait`}
      className="portrait"
      src={source}
    />
  );
}
