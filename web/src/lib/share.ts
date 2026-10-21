/** Where a read-only link opens on this site. sp-server's tokens are URL-safe, but encoding keeps any token safe. */
export function sharePath(token: string) {
  return `/r/${encodeURIComponent(token)}`;
}
