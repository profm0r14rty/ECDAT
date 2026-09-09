/**
 * Fixed, consistent color palette shared across the whole app for risk levels.
 * critical = unambiguously "bad" (red family), quantum-safe = unambiguously "good" (green family).
 * Every chart/badge should reference these values so the UI is visually consistent.
 *
 * Shades are Tailwind 700-level so the colored text used in badges / top-5 /
 * recommendations meets WCAG AA (>= 4.5:1) against white/neutral card
 * backgrounds (verified: critical 6.47, high 5.18, medium 4.92, low 4.99,
 * quantum-safe 5.02 — the previous 500-level shades all fell below 4.5:1).
 * They also work as chart fills (large graphical areas need only 3:1).
 */
export const RISK_COLORS: Record<string, string> = {
  critical: '#b91c1c',         // red-700 — unambiguously bad, AA on white
  high: '#c2410c',             // orange-700
  medium: '#a16207',           // yellow-700
  low: '#4d7c0f',              // lime-700
  'quantum-safe': '#15803d',   // green-700 — unambiguously good, AA on white
}

/**
 * Label display names for risk levels (matching the risk_level Literal type).
 * Used when rendering badges, chart labels, etc.
 */
export const RISK_LABELS: Record<string, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  'quantum-safe': 'Quantum-safe',
}