/** Presentation only: never trim, normalize, append to, or persist server text. */
export function revealEnd(text: string, visible: number, elapsed: number): number {
  const backlog = Math.max(0, text.length - visible);
  const count = Math.max(1, Math.floor(Math.min(elapsed, 50) / 1000 * (90 + backlog * 4)));
  let end = Math.min(text.length, visible + count);
  // Never split a UTF-16 surrogate pair (e.g. emoji) between frames.
  if (end < text.length && /[\uD800-\uDBFF]/.test(text[end - 1])) end++;
  return end;
}
