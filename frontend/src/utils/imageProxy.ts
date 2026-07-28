export type ImageProxySource = "manual" | "xchina";

export function proxiedImageUrl(
  url: string | null | undefined,
  source: ImageProxySource = "manual",
): string | null {
  if (!url) {
    return null;
  }
  if (!/^https?:\/\//i.test(url)) {
    return url;
  }
  const endpoint =
    source === "xchina" ? "/api/xchina/image-proxy" : "/api/manual/image-proxy";
  return `${endpoint}?url=${encodeURIComponent(url)}`;
}
