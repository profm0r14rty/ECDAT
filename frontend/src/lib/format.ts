/** Shared display helpers for the dashboard. */

/** Format an ISO-8601 timestamp (or null) for display; empty string when null. */
export function formatDateTime(iso: string | null): string {
  if (iso === null) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString()
}