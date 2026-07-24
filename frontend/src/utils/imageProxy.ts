export function proxiedImageUrl(url: string | null | undefined): string | null {
  if (!url) {
    return null;
  }
  if (!/^https?:\/\//i.test(url)) {
    return url;
  }
  return `/api/manual/image-proxy?url=${encodeURIComponent(url)}`;
}
