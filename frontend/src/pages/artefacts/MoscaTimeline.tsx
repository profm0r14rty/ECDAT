/**
 * Visual representation of Mosca's inequality for a single artefact.
 *
 * Renders a horizontal stacked bar: migration time (X) + shelf life (Y)
 * segments, against the threat horizon (Z) shown as a vertical reference
 * line — visually demonstrating whether X + Y crosses past Z (the Mosca
 * violation). Labels carry the actual numbers so judges can see the real
 * math.
 *
 * Classically-broken artefacts are visually distinguished: the Z line is
 * replaced with an "N/A — already broken" label, since the quantum threat
 * horizon isn't the operative constraint for something broken today.
 *
 * Quantum-safe artefacts render a special all-green "no quantum threat" state.
 */

import type { ArtefactRiskAssessment } from '@/api/client'
import { RISK_COLORS } from '@/lib/colors'

/** Props for {@link MoscaTimeline}. */
interface MoscaTimelineProps {
  risk: ArtefactRiskAssessment
  classicallyBroken: boolean
  quantumVulnerable: boolean
}

/**
 * Rounds a number to at most 2 decimal places, dropping any unnecessary
 * trailing zeros.
 */
function fmt(value: number): string {
  return value % 1 === 0 ? String(value) : value.toFixed(1)
}

export default function MoscaTimeline({
  risk,
  classicallyBroken,
  quantumVulnerable,
}: MoscaTimelineProps) {
  const { migration_time_years: x, shelf_life_years: y, threat_horizon_years: z } = risk
  const sum = x + y
  const violation = risk.mosca_violation

  // Quantum-safe: all zeros, no quantum threat.
  if (!classicallyBroken && !quantumVulnerable) {
    return (
      <div className="flex flex-col gap-2">
        <div className="relative h-7 overflow-hidden rounded-md border border-emerald-300/50 bg-emerald-500/10 dark:border-emerald-700/40">
          <div className="flex h-full items-center justify-center text-xs text-emerald-700 dark:text-emerald-400">
            No quantum threat — artefact is quantum-safe
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          <span className="font-medium">X + Y &gt; Z</span> does not apply.
          This artefact is not vulnerable to Shor's or Grover's quantum
          algorithms.
        </p>
      </div>
    )
  }

  // Classically broken: bar shows X+Y, Z line is replaced by "N/A — already broken".
  if (classicallyBroken) {
    return (
      <div className="flex flex-col gap-2">
        <div className="relative h-7 overflow-hidden rounded-md border border-red-300/60 bg-red-500/5 dark:border-red-700/50">
          <div className="absolute inset-0 flex items-center justify-center text-xs font-medium text-red-700 dark:text-red-400">
            N/A — already broken by classical attacks
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>
            <span className="inline-block size-2.5 rounded-sm bg-red-400/70 align-middle dark:bg-red-600" />{' '}
            <span className="font-medium">X (migration):</span> {fmt(x)} yr
          </span>
          <span>
            <span className="inline-block size-2.5 rounded-sm bg-amber-400/70 align-middle dark:bg-amber-600" />{' '}
            <span className="font-medium">Y (shelf life):</span> {fmt(y)} yr
          </span>
          <span>
            <span className="font-medium">Z (threat horizon):</span> N/A
          </span>
          <span className="font-medium text-red-600 dark:text-red-500">
            Urgency: {fmt(risk.urgency_ratio)}
          </span>
          <span className="font-medium text-red-600 dark:text-red-500">
            Broken today — quantum timeline irrelevant
          </span>
        </div>
      </div>
    )
  }

  // Normal quantum-vulnerable artefact: stacked bar vs Z reference line.
  const barMax = Math.max(sum, z, 1) // avoid division by zero
  const xPct = (x / barMax) * 100
  const yPct = (y / barMax) * 100
  const zPct = (z / barMax) * 100

  return (
    <div className="flex flex-col gap-2">
      {/* Stacked bar with Z reference line */}
      <div className="relative h-7 overflow-visible">
        {/* X segment (migration time) */}
        <div
          className="absolute top-0 bottom-0 left-0 bg-red-400/70 dark:bg-red-600/60"
          style={{ width: `${xPct}%` }}
        />
        {/* Y segment (shelf life) */}
        <div
          className="absolute top-0 bottom-0 bg-amber-400/70 dark:bg-amber-600/60"
          style={{ left: `${xPct}%`, width: `${yPct}%` }}
        />
        {/* Bar border */}
        <div className="pointer-events-none absolute inset-0 rounded-md border border-border" />
        {/* Z threshold line */}
        {z > 0 && (
          <div
            className="absolute top-0 z-10 h-full w-px border-l-2 border-dashed border-slate-800/60 dark:border-slate-200/60"
            style={{ left: `${zPct}%` }}
          />
        )}
        {/* Z label above the line */}
        {z > 0 && (
          <span
            className="absolute -top-0.5 z-20 -translate-x-1/2 whitespace-nowrap text-[10px] font-medium leading-none text-slate-700 dark:text-slate-300"
            style={{ left: `${Math.min(zPct, 97)}%` }}
          >
            Z={fmt(z)}yr
          </span>
        )}
        {/* X+Y total label below the bar */}
        <span
          className="absolute z-20 translate-x-1/2 whitespace-nowrap text-[10px] font-medium leading-none text-slate-700 dark:text-slate-300"
          style={{ left: `${Math.min(100, (sum / barMax) * 100)}%`, top: '100%', paddingTop: 4 }}
        >
          X+Y={fmt(sum)}yr
        </span>
      </div>

      {/* Legend + formula label */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>
          <span className="inline-block size-2.5 rounded-sm bg-red-400/70 align-middle dark:bg-red-600" />{' '}
          <span className="font-medium">X (migration):</span> {fmt(x)} yr
        </span>
        <span>
          <span className="inline-block size-2.5 rounded-sm bg-amber-400/70 align-middle dark:bg-amber-600" />{' '}
          <span className="font-medium">Y (shelf life):</span> {fmt(y)} yr
        </span>
        <span>
          <span className="inline-block w-px h-3 align-middle border-l-2 border-dashed border-slate-800/60 dark:border-slate-200/60" />{' '}
          <span className="font-medium">Z (threat horizon):</span> {fmt(z)} yr
        </span>
        <span className="font-medium" style={{ color: RISK_COLORS[risk.risk_level] }}>
          Urgency: {fmt(risk.urgency_ratio)}
          {violation && ' — Mosca violated'}
        </span>
      </div>
    </div>
  )
}
