import type { ReactNode } from 'react'
import { Atom, TriangleAlert } from 'lucide-react'

import type { RiskLevel } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { RISK_COLORS, RISK_LABELS } from '@/lib/colors'

/**
 * Badges and status indicators for the artefacts table and detail dialog.
 *
 * The quantum-vulnerable / classically-broken distinction is loaded here on
 * purpose: these are two *different* failure modes (broken by Shor/Grover vs
 * broken by classical attacks today) and the UI must never visually merge
 * them back together — a classically-broken artefact must never look like the
 * deliberate "quantum-safe" green (that mislabeling was a real backend bug,
 * Fix Phases 1–5). Hence amber+atom for quantum-vulnerable and red+alert for
 * classically-broken, with muted dashes for the "no" states.
 */

/** Risk-level badge colored from the shared Phase 18 palette. */
export function RiskLevelBadge({
  level,
  className,
}: {
  level: RiskLevel | string
  className?: string
}) {
  return (
    <Badge
      variant="outline"
      className={className}
      style={{
        color: RISK_COLORS[level] ?? undefined,
        borderColor: RISK_COLORS[level] ?? undefined,
      }}
    >
      {RISK_LABELS[level] ?? level}
    </Badge>
  )
}

/** Amber "Quantum-vulnerable" badge — broken by Shor's/Grover's algorithms. */
export function QuantumVulnerableBadge() {
  return (
    <Badge className="gap-1 border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400">
      <Atom data-icon="inline-start" />
      Quantum-vulnerable
    </Badge>
  )
}

/** Red "Classically broken" badge — already broken today, independent of quantum. */
export function ClassicallyBrokenBadge() {
  return (
    <Badge className="gap-1 border-red-500/50 bg-red-500/10 text-red-700 dark:text-red-400">
      <TriangleAlert data-icon="inline-start" />
      Classically broken
    </Badge>
  )
}

/**
 * Muted "no" indicator for a status cell (e.g. not quantum-vulnerable).
 * Deliberately NOT a green checkmark: a "not vulnerable" cell must not read
 * as "safe" — a classically-broken artefact (red alert) sits right next to
 * this dash. Renders a dash by default; pass children to render text instead.
 */
export function StatusDash({
  label,
  className,
  children,
}: {
  label: string
  className?: string
  children?: ReactNode
}) {
  return (
    <span
      className={className ?? 'text-muted-foreground/60'}
      title={label}
      aria-label={label}
    >
      {children ?? '—'}
    </span>
  )
}