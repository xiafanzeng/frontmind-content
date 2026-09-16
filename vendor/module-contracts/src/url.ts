export function normalizeShareUrl(value: unknown): string | undefined {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    hasAsciiControlCharacter(value)
  )
    return undefined;
  try {
    const url = new URL(value.trim());
    return isSafeExternalHttpUrl(url) ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

function hasAsciiControlCharacter(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code <= 0x1f || code === 0x7f) return true;
  }
  return false;
}

function isSafeExternalHttpUrl(url: URL): boolean {
  return (
    (url.protocol === "https:" || url.protocol === "http:") &&
    !url.username &&
    !url.password
  );
}
