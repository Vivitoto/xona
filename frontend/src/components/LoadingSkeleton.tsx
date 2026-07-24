interface LoadingSkeletonProps {
  title?: string;
  description?: string;
  rows?: number;
  variant?: "cards" | "table";
}

export function LoadingSkeleton({
  title = "正在加载",
  description = "读取本地数据，请稍候。",
  rows = 3,
  variant = "cards",
}: LoadingSkeletonProps) {
  return (
    <div className={`skeleton-panel skeleton-${variant}`} role="status" aria-label={title}>
      <div className="skeleton-copy">
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
      <div className="skeleton-stack" aria-hidden="true">
        {Array.from({ length: rows }).map((_, index) => (
          <span className="skeleton-line" key={index} />
        ))}
      </div>
    </div>
  );
}
