/**
 * Scan overview page: stat cards, risk-distribution pie, algorithm-mix
 * donut, exposure-by-family stacked bar, and actionable top-5 priority cards.
 *
 * Phase 26: reskin to --color-surface / --color-accent design-token system
 * (Phase 24 tokens), add donut + stacked-bar charts, reframe top-5 as
 * actionable recommendation cards with artefact-detail links, and add
 * count-up animation on stat numbers + hover-lift micro-interaction on
 * all cards.
 */

import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, ArrowRight } from 'lucide-react'
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Curve,
  type PieLabelRenderProps,
  type PieProps,
  type TooltipContentProps,
} from 'recharts'

import {
  api,
  type ScanRunDetail,
  type ScanStatus,
  type Artefact,
  type RiskLevel,
} from '@/api/client'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { truncatePath } from '@/lib/paths'
import { formatDateTime } from '@/lib/format'
import { usePageTitle } from '@/lib/pageTitle'
import { RISK_COLORS, RISK_LABELS } from '@/lib/colors'
import { useScan } from '@/lib/scanContext'
import { useCountUp } from '@/lib/useCountUp'
import ColdStartBanner from '@/components/ColdStartBanner'

// -------------------------------------------------------------------
// Chart palette — distinct hues for algorithm families
// -------------------------------------------------------------------

const FAMILY_PALETTE = [
  '#44e0a4', // accent green
  '#60a5fa', // blue
  '#f472b6', // pink
  '#fbbf24', // amber
  '#a78bfa', // violet
  '#34d399', // emerald
  '#fb923c', // orange
  '#f87171', // red
  '#38bdf8', // sky
  '#c084fc', // purple
  '#2dd4bf', // teal
  '#e879f9', // fuchsia
]

// -------------------------------------------------------------------
// Slice labels: threshold strategy — inline labels only for slices at
// or above ~6%; below that, colour + legend + hover tooltip only.
// -------------------------------------------------------------------

const LABEL_MIN_PERCENT = 0.06

/** Inline label for a slice — `null` (nothing rendered) below the threshold. */
function renderSliceLabel(props: PieLabelRenderProps): string | null {
  const { name, value, percent } = props
  if (percent === undefined || percent < LABEL_MIN_PERCENT) return null
  return `${name ?? ''}: ${value ?? 0}`
}

/**
 * Connector line only for labeled slices: Recharts draws the callout line
 * for every slice when `labelLine` is truthy, so returning `null` for
 * sub-threshold slices is what actually removes the orphaned lines.
 * Cast: Recharts' d.ts types the callback `(props: any) => ReactElement`
 * but the runtime forwards the function's return — `null` included.
 */
const renderSliceLabelLine = ((
  props: PieLabelRenderProps,
): ReactElement | null => {
  if (props.percent === undefined || props.percent < LABEL_MIN_PERCENT) {
    return null
  }
  const { key: _key, ...lineProps } = props
  return <Curve type="linear" className="recharts-pie-label-line" {...lineProps} />
}) as unknown as PieProps['labelLine']

// -------------------------------------------------------------------
// Inline sub-components
// -------------------------------------------------------------------

/** Animated stat card with count-up number + hover-lift micro-interaction. */
function StatCard({
  value,
  label,
  highlight,
  loading = false,
  numericValue,
}: {
  value: number | string | undefined
  label: string
  highlight?: 'accent'
  loading?: boolean
  numericValue?: number
}) {
  const countRef = useCountUp(numericValue ?? 0)

  return (
    <Card className="bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-accent/5">
      <CardContent className="pt-4">
        {loading ? (
          <Skeleton className="h-8 w-16" aria-label={`Loading ${label}`} />
        ) : (
          <p
            className={`text-2xl font-bold tracking-tight ${
              highlight === 'accent' ? 'text-accent' : ''
            }`}
          >
            {numericValue !== undefined ? (
              <span ref={countRef}>0</span>
            ) : (
              value
            )}
          </p>
        )}
        <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
      </CardContent>
    </Card>
  )
}

/** Scan-run metadata row (source, created, completed, files scanned). */
function MetaCard({ meta }: { meta: Array<[string, string]> }) {
  return (
    <Card className="bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-accent/5">
      <CardContent className="flex flex-wrap items-center gap-x-8 gap-y-2 pt-6 text-sm">
        {meta.map(([label, value]) => (
          <span key={label}>
            {label}: <span className="font-medium">{value}</span>
          </span>
        ))}
      </CardContent>
    </Card>
  )
}

/** In-flight progress: spinner + status label. */
function ScanningState({
  scan,
  meta,
}: {
  scan: ScanRunDetail
  meta: Array<[string, string]>
}) {
  const STATUS_LABEL: Record<ScanStatus, string> = {
    queued: 'Queued — waiting to start',
    running: 'Running — analysing codebase',
    done: 'Done',
    failed: 'Failed',
  }
  return (
    <>
      <Card className="bg-surface">
        <CardContent className="flex items-center gap-4 py-8">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
          <div>
            <p className="font-medium">Scanning…</p>
            <p className="text-sm text-muted-foreground">
              {STATUS_LABEL[scan.status]}
            </p>
          </div>
        </CardContent>
      </Card>
      <MetaCard meta={meta} />
    </>
  )
}

/** Terminal failure: the backend's error_message shown prominently. */
function FailedState({
  scan,
  meta,
}: {
  scan: ScanRunDetail
  meta: Array<[string, string]>
}) {
  return (
    <>
      <Alert variant="destructive">
        <AlertTitle>Scan failed</AlertTitle>
        <AlertDescription>
          {scan.error_message ?? 'No error details were provided by the backend.'}
        </AlertDescription>
      </Alert>
      <Button asChild variant="outline" className="mt-4 w-fit">
        <Link to="/app">Back to scans</Link>
      </Button>
      <MetaCard meta={meta} />
    </>
  )
}

// -------------------------------------------------------------------
// Shared chart tooltip (Phase 41) — one styled component for the risk
// pie, the algorithm donut, and the exposure stacked bar. Slice
// payloads carry `percent` on their data object; stacked-bar payloads
// are one entry per risk level with a family `label` header instead.
// -------------------------------------------------------------------

interface SliceTooltipDatum {
  name?: string
  value?: number
  percent?: number
}

function ChartTooltip({
  active,
  payload,
  label,
}: TooltipContentProps) {
  const ICON_RADIUS = 9

  if (!active || !payload || payload.length === 0) return null

  const firstPayload = payload[0].payload as Partial<SliceTooltipDatum> | null
  const isSlicePayload =
    firstPayload !== null && typeof firstPayload === 'object' && 'percent' in firstPayload

  return (
    <div
      style={{
        background: '#0b1a12', // duplicate of --color-surface: Recharts inline styles can't resolve CSS vars
        border: '1px solid oklch(1 0 0 / 12%)',
        borderRadius: '0.5rem',
        padding: '0.5rem 0.625rem',
        fontSize: 12,
        lineHeight: 1.5,
        color: 'oklch(0.85 0.02 160)',
      }}
    >
      {isSlicePayload
        ? payload.map((entry) => {
            const datum = entry.payload as SliceTooltipDatum
            const percent =
              typeof datum.percent === 'number' ? datum.percent * 100 : undefined
            return (
              <div
                key={entry.name ?? String(entry.dataKey)}
                style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}
              >
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                  <span
                    style={{
                      display: 'inline-block',
                      width: ICON_RADIUS,
                      height: ICON_RADIUS,
                      borderRadius: '9999px',
                      background: entry.color ?? 'oklch(0.65 0.015 160)',
                    }}
                  />
                  {datum.name ?? entry.name}
                </span>
                <span style={{ fontWeight: 600, color: 'oklch(0.95 0.015 160)' }}>
                  {datum.value ?? 0}
                  {percent !== undefined ? ` (${percent.toFixed(1)}%)` : ''}
                </span>
              </div>
            )
          })
        : (
            <>
              <p style={{ fontWeight: 600, margin: '0 0 0.25rem', color: 'oklch(0.95 0.015 160)' }}>
                {label}
              </p>
              {payload
                .filter((entry) => typeof entry.value === 'number' && entry.value > 0)
                .map((entry) => (
                  <div
                    key={String(entry.dataKey)}
                    style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}
                  >
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          width: ICON_RADIUS,
                          height: ICON_RADIUS,
                          borderRadius: '9999px',
                          background: entry.color ?? 'oklch(0.65 0.015 160)',
                        }}
                      />
                      {entry.name}
                    </span>
                    <span style={{ fontWeight: 600, color: 'oklch(0.95 0.015 160)' }}>
                      {entry.value}
                    </span>
                  </div>
                ))}
            </>
          )}
    </div>
  )
}

// -------------------------------------------------------------------
// Exposure-by-family stacked bar data (computed from artefacts)
// -------------------------------------------------------------------

const RISK_LEVEL_ORDER: RiskLevel[] = [
  'critical',
  'high',
  'medium',
  'low',
  'quantum-safe',
]

interface FamilyRiskRow {
  family: string
  critical: number
  high: number
  medium: number
  low: number
  'quantum-safe': number
}

function computeFamilyRiskData(artefacts: Artefact[]): FamilyRiskRow[] {
  const map = new Map<string, Record<string, number>>()
  for (const a of artefacts) {
    if (!map.has(a.algorithm_family)) {
      map.set(a.algorithm_family, {
        critical: 0,
        high: 0,
        medium: 0,
        low: 0,
        'quantum-safe': 0,
      })
    }
    const bucket = map.get(a.algorithm_family)!
    bucket[a.risk_assessment.risk_level] =
      (bucket[a.risk_assessment.risk_level] ?? 0) + 1
  }
  return Array.from(map.entries())
    .map(([family, counts]) => ({
      family,
      ...counts,
    } as FamilyRiskRow))
    .sort((a, b) => b.critical - a.critical)
}

// -------------------------------------------------------------------
// Done state: overview with all charts + actionable top-5
// -------------------------------------------------------------------

function DoneState({
  scan,
  meta,
}: {
  scan: ScanRunDetail
  meta: Array<[string, string]>
}) {
  const summary = scan.summary
  const [artefacts, setArtefacts] = useState<Artefact[]>([])
  const [loadingArtefacts, setLoadingArtefacts] = useState(true)

  useEffect(() => {
    if (scan.id === undefined || scan.status !== 'done') return
    let cancelled = false

    async function loadArtefacts(): Promise<void> {
      try {
        const res = await api.getArtefacts(scan.id, {
          page: 1,
          page_size: 500,
        })
        if (!cancelled) setArtefacts(res.items)
      } catch {
        // Silently ignore artefact fetch errors; the summary still renders
      } finally {
        if (!cancelled) setLoadingArtefacts(false)
      }
    }

    void loadArtefacts()
    return () => {
      cancelled = true
    }
  }, [scan.id, scan.status])

  const classicallyBrokenCount = artefacts.filter(
    (a) => a.classically_broken,
  ).length

  // --- Risk distribution pie data ---
  const pieData = summary
    ? (Object.entries(summary.risk_level_counts) as Array<[string, number]>)
        .filter(([, count]) => count > 0)
        .map(([level, count]) => ({
          name: RISK_LABELS[level] ?? level,
          value: count,
          level,
        }))
    : []

  // --- Algorithm-mix donut data ---
  const donutData = useMemo(() => {
    if (!summary) return []
    return Object.entries(summary.algorithm_family_counts)
      .filter(([, count]) => count > 0)
      .map(([family, count]) => ({ name: family, value: count }))
      .sort((a, b) => b.value - a.value)
  }, [summary])

  // --- Exposure-by-family stacked bar data ---
  const familyRiskData = useMemo(
    () => (artefacts.length > 0 ? computeFamilyRiskData(artefacts) : []),
    [artefacts],
  )

  // --- Measured thinning for bar x-axis (Phase 41) ---
  // Rotate -90° labels at fontSize 10 each occupy ~13px of horizontal axis.
  // Measure the actual container width and compute how many ticks fit so that
  // at narrow viewports the labels are thinned (evenly, keeping first+last)
  // instead of overlapping.
  const TICK_PX = 14
  const barContainerRef = useRef<HTMLDivElement>(null)
  const [barContainerWidth, setBarContainerWidth] = useState(0)
  const barReady = familyRiskData.length > 0
  useEffect(() => {
    if (!barReady) return
    const el = barContainerRef.current
    if (!el) return
    setBarContainerWidth(el.clientWidth || el.getBoundingClientRect().width)
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width
      if (w) setBarContainerWidth(w)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [barReady])
  const axisAvailable = Math.max(barContainerWidth - 80, 40) // y-axis ~50 + margins ~30
  const maxTicks = Math.max(Math.floor(axisAvailable / TICK_PX), 1)
  const visibleFamilyTicks = useMemo(() => {
    const allNames = familyRiskData.map((d) => d.family)
    const n = allNames.length
    if (n <= maxTicks) return allNames
    // Spacing in band space: each rotated label needs ~TICK_PX of axis, so
    // consecutive selected indices must be at least ceil(TICK_PX/bandPx) apart
    // or the label bboxes overlap even when evenly spaced.
    const bandPx = Math.max(axisAvailable / n, 1)
    const minGap = Math.max(Math.ceil(TICK_PX / bandPx), 1)
    const indices: number[] = []
    for (let i = 0; i < n; i += minGap) indices.push(i)
    const last = indices[indices.length - 1]
    if (last !== n - 1 && n - 1 - last >= minGap) indices.push(n - 1)
    return indices.map((i) => allNames[i])
  }, [familyRiskData, maxTicks, axisAvailable])

  // --- Lookup artefact by detection_id for actionable top-5 ---
  const artefactMap = useMemo(
    () => new Map(artefacts.map((a) => [a.id, a])),
    [artefacts],
  )

  return (
    <>
      <Card className="bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-accent/5">
        <CardHeader>
          <CardTitle>Scan complete</CardTitle>
          <CardDescription>
            {summary !== null
              ? `${summary.total_detections} detections found`
              : 'No detections recorded'}
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="flex flex-col gap-6">
        {/* Stat cards */}
        {summary !== null && (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <StatCard
              value={summary.total_detections}
              numericValue={summary.total_detections}
              label="Total detections"
            />
            <StatCard
              value={scan.files_scanned ?? 0}
              numericValue={scan.files_scanned ?? 0}
              label="Files scanned"
            />
            <StatCard
              value={summary.quantum_vulnerable_count}
              numericValue={summary.quantum_vulnerable_count}
              label="Quantum vulnerable"
              highlight="accent"
            />
            <StatCard
              value={
                summary.quantum_vulnerable_percentage.toFixed(1) + '%'
              }
              label="Vulnerable share"
              highlight="accent"
            />
            <StatCard
              value={loadingArtefacts ? undefined : classicallyBrokenCount}
              numericValue={loadingArtefacts ? undefined : classicallyBrokenCount}
              label="Classically broken"
              highlight="accent"
              loading={loadingArtefacts}
            />
          </div>
        )}

        {/* Row 1: Risk distribution pie + Algorithm mix donut */}
        <div className="grid gap-6 md:grid-cols-2">
          <Card className="bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-accent/5">
            <CardHeader>
              <CardTitle className="text-base">Risk distribution</CardTitle>
            </CardHeader>
            <CardContent>
              {pieData.length > 0 ? (
                <ResponsiveContainer width="100%" height={320}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      paddingAngle={1}
                      label={renderSliceLabel}
                      labelLine={renderSliceLabelLine}
                    >
                      {pieData.map((entry) => (
                        <Cell
                          key={entry.level}
                          fill={RISK_COLORS[entry.level] ?? '#94a3b8'}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={ChartTooltip} />
                    <Legend
                      iconType="circle"
                      iconSize={10}
                      wrapperStyle={{ fontSize: 12, lineHeight: 1.6, paddingTop: 6 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No risk data available
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-accent/5">
            <CardHeader>
              <CardTitle className="text-base">Algorithm mix</CardTitle>
              <CardDescription>
                Distribution of detected algorithm families
              </CardDescription>
            </CardHeader>
            <CardContent>
              {donutData.length > 0 ? (
                <ResponsiveContainer width="100%" height={360}>
                  <PieChart>
                    <Pie
                      data={donutData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={55}
                      outerRadius={90}
                      paddingAngle={1}
                      label={renderSliceLabel}
                      labelLine={renderSliceLabelLine}
                    >
                      {donutData.map((_, idx) => (
                        <Cell
                          key={`donut-${idx}`}
                          fill={FAMILY_PALETTE[idx % FAMILY_PALETTE.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={ChartTooltip} />
                    <Legend
                      iconType="circle"
                      iconSize={10}
                      wrapperStyle={{ fontSize: 12, lineHeight: 1.6, paddingTop: 6 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No algorithm data available
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Row 2: Exposure by algorithm family stacked bar */}
        {familyRiskData.length > 0 && (
          <Card className="bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-accent/5">
            <CardHeader>
              <CardTitle className="text-base">
                Exposure by algorithm family
              </CardTitle>
              <CardDescription>
                Artefact count per family, stacked by risk level
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div ref={barContainerRef}>
                <ResponsiveContainer width="100%" height={320}>
                  <BarChart
                    data={familyRiskData}
                    margin={{ top: 5, right: 20, bottom: 5, left: 0 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="oklch(1 0 0 / 12%)"
                    />
                    <XAxis
                      dataKey="family"
                      ticks={visibleFamilyTicks}
                      interval={0}
                      angle={-90}
                      textAnchor="end"
                      height={110}
                      tickMargin={6}
                      tick={{ fill: 'oklch(0.65 0.015 160)', fontSize: 10 }}
                      tickFormatter={(name: string) =>
                        name.length > 15 ? `${name.slice(0, 15)}…` : name
                      }
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fill: 'oklch(0.65 0.015 160)', fontSize: 12 }}
                    />
                    <Tooltip content={ChartTooltip} />
                    {RISK_LEVEL_ORDER.map((level) => (
                      <Bar
                        key={level}
                        dataKey={level}
                        stackId="family"
                        fill={RISK_COLORS[level]}
                        name={RISK_LABELS[level]}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Row 3: Actionable top-5 priority cards */}
        <Card className="bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-accent/5">
          <CardHeader>
            <CardTitle className="text-base">
              Priority actions
            </CardTitle>
            <CardDescription>
              Highest-urgency artefacts — act on these first
            </CardDescription>
          </CardHeader>
          <CardContent>
            {summary?.top_5_urgency &&
            summary.top_5_urgency.length > 0 ? (
              <ol className="flex flex-col gap-2">
                {summary.top_5_urgency.map((item, idx) => {
                  const artefact = artefactMap.get(item.detection_id)
                  const recommended =
                    artefact?.recommendation?.recommended_algorithm
                  return (
                    <li
                      key={item.detection_id}
                      className="flex items-start gap-3 rounded-md border border-border bg-bg/40 px-3 py-2.5 text-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:shadow-accent/5"
                    >
                      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-accent/10 text-xs font-semibold text-accent">
                        {idx + 1}
                      </span>
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <Badge
                            variant="outline"
                            className="text-xs"
                            style={{
                              color: RISK_COLORS[item.risk_level] ?? undefined,
                              borderColor:
                                RISK_COLORS[item.risk_level] ?? undefined,
                            }}
                          >
                            {item.risk_level}
                          </Badge>
                          <span className="font-medium">
                            {recommended
                              ? `Replace ${item.algorithm_family}`
                              : item.algorithm_family}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
                          {recommended ? (
                            <>
                              in{' '}
                              <span className="font-mono text-foreground/70">
                                {truncatePath(item.file_path, 60)}
                              </span>{' '}
                              with{' '}
                              <span className="font-medium text-accent-soft">
                                {recommended}
                              </span>
                            </>
                          ) : (
                            <span className="font-mono text-foreground/70">
                              {truncatePath(item.file_path, 60)}
                            </span>
                          )}
                        </p>
                      </div>
                      <Button
                        asChild
                        variant="ghost"
                        size="sm"
                        className="shrink-0 text-xs text-accent hover:bg-accent/10 hover:text-accent"
                      >
                        <Link
                          to={`/app/scans/${scan.id}/artefacts?highlight=${item.detection_id}`}
                        >
                          View
                          <ArrowRight className="ml-1 size-3" />
                        </Link>
                      </Button>
                    </li>
                  )
                })}
              </ol>
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No urgency data available
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <MetaCard meta={meta} />
    </>
  )
}

// -------------------------------------------------------------------
// Main page component
// -------------------------------------------------------------------

export default function ScanOverviewPage() {
  const { currentScan: scan, scanError: error, coldStartPending } = useScan()
  usePageTitle(scan ? `Scan ${scan.id} — Overview` : 'Scan')

  if (coldStartPending && scan === null) {
    return <ColdStartBanner />
  }

  if (error !== null && scan === null) {
    return (
      <>
        <Alert variant="destructive">
          <AlertTitle>Could not load scan</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button asChild variant="outline" className="mt-4 w-fit">
          <Link to="/app">Back to scans</Link>
        </Button>
      </>
    )
  }

  if (scan === null) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-full" />
      </div>
    )
  }

  const meta: Array<[string, string]> = [
    ['Source', scan.source_type],
    ['Created', formatDateTime(scan.created_at)],
    ['Completed', formatDateTime(scan.completed_at)],
    ['Files scanned', scan.files_scanned?.toString() ?? '—'],
  ]

  if (scan.status === 'queued' || scan.status === 'running') {
    return <ScanningState scan={scan} meta={meta} />
  }

  if (scan.status === 'failed') {
    return <FailedState scan={scan} meta={meta} />
  }

  return <DoneState scan={scan} meta={meta} />
}
