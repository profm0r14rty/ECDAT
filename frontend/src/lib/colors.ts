/**
 * Fixed, consistent color palette shared across the whole app for risk levels.
 * critical = unambiguously "bad" (red family), quantum-safe = unambiguously "good" (green family).
 * Every chart/badge should reference these values so the UI is visually consistent.
 */
export const RISK_COLORS: Record<string, string> = {
  critical: '#ef4444',         // red-500 unambiguously bad
  high: '#f97316',             // orange-500
  medium: '#eab308',           // yellow-500
  low: '#84cc16',              // lime-500
  'quantum-safe': '#22c55e',   // green-500 unambiguously good
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