import type { ActorRead } from "../api/types";
import { proxiedImageUrl } from "../utils/imageProxy";
import { useImageSafetyMode } from "./ImageSafetyMode";

export function ActorPortrait({ actor }: { actor: ActorRead }) {
  const { imageSafetyModeEnabled } = useImageSafetyMode();
  const source = proxiedImageUrl(actor.portrait_source_url);
  if (!source) {
    return (
      <div
        aria-label={`${actor.canonical_name} 缺少头像`}
        className="portrait placeholder"
        role="img"
      >
        <span>无头像</span>
      </div>
    );
  }

  return (
    <img
      alt={`${actor.canonical_name} 头像`}
      aria-label={
        imageSafetyModeEnabled
          ? `${actor.canonical_name} 头像，安全模式已模糊，悬停、聚焦或轻点可临时查看`
          : `${actor.canonical_name} 头像`
      }
      className={`portrait safety-image${imageSafetyModeEnabled ? " is-blurred" : ""}`}
      data-image-safety={imageSafetyModeEnabled ? "blurred" : "visible"}
      src={source}
      tabIndex={imageSafetyModeEnabled ? 0 : undefined}
      title={
        imageSafetyModeEnabled
          ? "安全模式已开启，悬停、聚焦或轻点头像可临时查看。"
          : "安全模式已关闭。"
      }
    />
  );
}
