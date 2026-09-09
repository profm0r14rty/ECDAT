/**
 * Path display helpers for the artefacts table.
 *
 * File paths coming back from the scanner can be long (repo-relative or
 * absolute); truncate for the table cell while keeping the meaningful tail
 * (the deepest segments) intact. The full path is always exposed via the
 * cell's `title` attribute for hover.
 */

/**
 * Truncate a file path to roughly *maxLen* characters, keeping the tail.
 *
 * The deepest path segments are preserved and earlier segments are dropped,
 * each replacement prefix being a single ellipsis character, e.g.
 * `…/utils/hasher.py`. If the basename alone is longer than the budget it is
 * itself trimmed from the front.
 *
 * @param path The file path to truncate.
 * @param maxLen Maximum number of characters to keep (default 48).
 * @returns The truncated path; unchanged when it already fits.
 */
export function truncatePath(path: string, maxLen = 48): string {
  if (path.length <= maxLen) return path

  const segments = path.split('/')
  const basename = segments[segments.length - 1] ?? ''
  let tail = basename.length > maxLen ? `…${basename.slice(-(maxLen - 1))}` : basename

  // Keep adding parent segments while there is room, leaving space for '…/'.
  for (let i = segments.length - 2; i >= 0; i--) {
    const segment = segments[i] ?? ''
    const candidate = `${segment}/${tail}`
    if (candidate.length > maxLen - 2) break
    tail = candidate
  }

  return `…/${tail}`
}