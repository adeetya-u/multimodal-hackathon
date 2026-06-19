/** Short random id; works over HTTP where crypto.randomUUID is unavailable. */
export function randomShortId(length = 8): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return crypto.randomUUID().replace(/-/g, "").slice(0, length);
  }
  let out = "";
  while (out.length < length) {
    out += Math.random().toString(16).slice(2);
  }
  return out.slice(0, length);
}

/** Safari on HTTP (e.g. LAN IP) exposes crypto but not randomUUID. */
export function ensureRandomUUID(): void {
  if (typeof globalThis.crypto?.randomUUID === "function") return;
  const cryptoRef = globalThis.crypto ?? (globalThis.crypto = {} as Crypto);
  cryptoRef.randomUUID = () =>
    "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
      const r = (Math.random() * 16) | 0;
      return (ch === "x" ? r : (r & 0x3) | 0x8).toString(16);
    }) as `${string}-${string}-${string}-${string}-${string}`;
}
