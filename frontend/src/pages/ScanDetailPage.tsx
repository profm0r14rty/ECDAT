import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Download, Loader2 } from 'lucide-react'
import { PieChart, Pie, Cell, Tooltip, Legend } from 'recharts'

import {
  api,
  apiErrorMessage,
  type ScanRunDetail,
  type ScanStatus,
  type Artefact,
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
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { formatDateTime } from '@/lib/format'
import { usePageTitle } from '@/lib/pageTitle'
import { RISK_COLORS, RISK_LABELS } from '@/lib/colors'
import ArtefactsTab from '@/pages/ArtefactsTab'

/** Poll interval while a scan is queued or running (milliseconds). */
const POLL_INTERVAL_MS = 1500
/** Statuses that stop the live-polling loop. */
const TERMINAL_STATUSES: ReadonlySet<ScanStatus> = new Set(['done', 'failed'])

const STATUS_VARIANT: Record<
  ScanStatus,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  queued: 'secondary',
  running: 'outline',
  done: 'default',
  failed: 'destructive',
}

const STATUS_LABEL: Record<ScanStatus, string> = {
  queued: 'Queued — waiting to start',
  running: 'Running — analysing codebase',
  done: 'Done',
  failed: 'Failed',
}

export default function ScanDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [scan, setScan] = useState<ScanRunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  usePageTitle(scan ? `Scan ${scan.id}` : 'Scan')

  // Fetch on mount, then poll every 1.5s while the scan is queued/running.
  // The interval is cleared once the status turns terminal (done/failed) and
  // on unmount, so no stale timers or setState-after-unmount can fire.
  useEffect(() => {
    if (id === undefined) return
    const scanId: string = id
    let cancelled = false
    let timerId: ReturnType<typeof setInterval> | undefined

    async function fetchScan(): Promise<void> {
      try {
        const next = await api.getScan(scanId)
        if (cancelled) return
        setScan(next)
        setError(null)
        if (TERMINAL_STATUSES.has(next.status)) {
          if (timerId !== undefined) {
            clearInterval(timerId)
            timerId = undefined
          }
        }
      } catch (err) {
        if (!cancelled) setError(apiErrorMessage(err))
      }
    }

    void fetchScan()
    timerId = setInterval(() => {
      void fetchScan()
    }, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      if (timerId !== undefined) clearInterval(timerId)
    }
  }, [id])

  if (error !== null) {
    return (
      <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
        <Alert variant="destructive">
          <AlertTitle>Could not load scan</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button asChild variant="outline" className="w-fit">
          <Link to="/">Back to scans</Link>
        </Button>
      </main>
    )
  }

  if (scan === null) {
    return (
      <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-full" />
      </main>
    )
  }

  const meta: Array<[string, string]> = [
    ['Source', scan.source_type],
    ['Created', formatDateTime(scan.created_at)],
    ['Completed', formatDateTime(scan.completed_at)],
    ['Files scanned', scan.files_scanned?.toString() ?? '—'],
  ]

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <Button asChild variant="outline" className="w-fit">
        <Link to="/">Back to scans</Link>
      </Button>

      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Scan {scan.id}
          </h1>
          <p className="font-mono text-sm text-muted-foreground">
            {scan.target}
          </p>
        </div>
        <Badge variant={STATUS_VARIANT[scan.status]}>{scan.status}</Badge>
      </header>

      {scan.status === 'queued' || scan.status === 'running' ? (
        <ScanningState scan={scan} meta={meta} />
      ) : scan.status === 'failed' ? (
        <FailedState scan={scan} meta={meta} />
      ) : (
        <DoneState scan={scan} meta={meta} />
      )}
    </main>
  )
}

/** In-flight progress: spinner + status label (files_scanned is null until done). */
function ScanningState({
  scan,
  meta,
}: {
  scan: ScanRunDetail
  meta: Array<[string, string]>
}) {
  return (
    <>
      <Card>
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
      <MetaCard meta={meta} />
    </>
  )
}

/**
 * Done state: overview with stat cards, risk distribution chart,
 * and top-5 urgency artefacts.
 */
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

  // Fetch artefacts once when the scan is done (to compute classically-broken count client-side)
  useEffect(() => {
    if (scan.id === undefined || scan.status !== 'done') return
    let cancelled = false

    async function loadArtefacts(): Promise<void> {
      try {
        const res = await api.getArtefacts(scan.id, { page: 1, page_size: 500 })
        if (!cancelled) setArtefacts(res.items)
      } catch {
        // Silently ignore artefact fetch errors; the summary still renders
      } finally {
        if (!cancelled) setLoadingArtefacts(false)
      }
    }

    void loadArtefacts()
    return () => { cancelled = true }
  }, [scan.id, scan.status])

  // Compute classically-broken count client-side from the artefacts
  const classicallyBrokenCount = artefacts.filter((a) => a.classically_broken).length

  // Build chart data: only include levels with count > 0 to avoid empty slices
  const chartData = summary
    ? (Object.entries(summary.risk_level_counts) as Array<[string, number]>)
        .filter(([, count]) => count > 0)
        .map(([level, count]) => ({
          name: RISK_LABELS[level] ?? level,
          value: count,
          level,
        }))
    : []

  // Algorithm families are data-driven from this scan's own results so the
  // Artefacts tab's filter options always match what is actually present.
  const artefactFamilies = summary !== null
    ? Object.keys(summary.algorithm_family_counts)
    : []

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Scan complete</CardTitle>
          <CardDescription>
            {summary !== null
              ? `${summary.total_detections} detections found`
              : 'No detections recorded'}
          </CardDescription>
        </CardHeader>
      </Card>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="artefacts">Artefacts</TabsTrigger>
          <TabsTrigger value="recommendations">Recommendations</TabsTrigger>
          <TabsTrigger value="export">Export</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="flex flex-col gap-6 pt-4">
          {/* Stat cards */}
          {summary !== null && (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
              <StatCard
                value={summary.total_detections}
                label="Total detections"
              />
              <StatCard
                value={scan.files_scanned ?? 0}
                label="Files scanned"
              />
              <StatCard
                value={summary.quantum_vulnerable_count}
                label="Quantum vulnerable"
                highlight="destructive"
              />
              <StatCard
                value={summary.quantum_vulnerable_percentage.toFixed(1) + '%'}
                label="Vulnerable share"
                highlight="destructive"
              />
              <StatCard
                value={loadingArtefacts ? undefined : classicallyBrokenCount}
                label="Classically broken"
                highlight="destructive"
                loading={loadingArtefacts}
              />
            </div>
          )}

          {/* Risk distribution chart + Top-5 urgency side-by-side on larger screens */}
          <div className="grid gap-6 md:grid-cols-2">
            {/* Risk distribution pie chart */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Risk distribution</CardTitle>
              </CardHeader>
              <CardContent>
                {chartData.length > 0 ? (
                  <div className="flex justify-center">
                    <PieChart width={320} height={260}>
                      <Pie
                        data={chartData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={90}
                        label={({ name, value }) => `${name}: ${value}`}
                      >
                        {chartData.map((entry) => (
                          <Cell
                            key={entry.level}
                            fill={RISK_COLORS[entry.level] ?? '#94a3b8'}
                          />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </div>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    No risk data available
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Top-5 highest-urgency artefacts */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Top-5 highest urgency</CardTitle>
                <CardDescription>
                  Artefacts requiring migration attention first
                </CardDescription>
              </CardHeader>
              <CardContent>
                {summary?.top_5_urgency && summary.top_5_urgency.length > 0 ? (
                  <ol className="flex flex-col gap-2">
                    {summary.top_5_urgency.map((item, idx) => (
                      <li
                        key={item.detection_id}
                        className="flex items-start gap-3 rounded-md border px-3 py-2 text-sm"
                      >
                        <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                          {idx + 1}
                        </span>
                        <div className="flex flex-col gap-0.5">
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
                              {item.algorithm_family}
                            </span>
                            <span className="ml-auto font-mono text-xs text-muted-foreground">
                              urgency {item.urgency_ratio.toFixed(1)}
                            </span>
                          </div>
                          <span className="truncate text-xs text-muted-foreground">
                            {item.file_path}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    No urgency data available
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="artefacts" className="pt-4">
          <ArtefactsTab scanId={scan.id} families={artefactFamilies} />
        </TabsContent>

        <TabsContent value="recommendations" className="pt-4">
          <RecommendationsTab scanId={scan.id} />
        </TabsContent>

        <TabsContent value="export" className="pt-4">
          <ExportTab scanId={scan.id} />
        </TabsContent>
      </Tabs>

      <MetaCard meta={meta} />
    </>
  )
}

/** Single stat card with a large value and descriptive label. */
function StatCard({
  value,
  label,
  highlight,
  loading = false,
}: {
  value: number | string | undefined
  label: string
  highlight?: 'destructive'
  loading?: boolean
}) {
  return (
    <Card>
      <CardContent className="pt-4">
        {loading ? (
          <Skeleton className="h-8 w-16" aria-label={`Loading ${label}`} />
        ) : (
          <p
            className={`text-2xl font-bold tracking-tight ${
              highlight === 'destructive' ? 'text-red-600' : ''
            }`}
          >
            {value}
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
    <Card>
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

function RecommendationsTab({ scanId }: { scanId: string }) {
  const [artefacts, setArtefacts] = useState<Artefact[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load(): Promise<void> {
      try {
        const res = await api.getArtefacts(scanId, { page: 1, page_size: 500 })
        if (!cancelled) setArtefacts(res.items)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [scanId])

  if (loading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  const groups = new Map<string, {
    count: number
    riskCounts: Map<string, number>
    recommendation: Artefact['recommendation']
  }>()

  for (const a of artefacts) {
    const existing = groups.get(a.algorithm_family)
    if (existing) {
      existing.count++
      existing.riskCounts.set(
        a.risk_assessment.risk_level,
        (existing.riskCounts.get(a.risk_assessment.risk_level) ?? 0) + 1,
      )
    } else {
      const riskCounts = new Map<string, number>()
      riskCounts.set(a.risk_assessment.risk_level, 1)
      groups.set(a.algorithm_family, {
        count: 1,
        riskCounts,
        recommendation: a.recommendation,
      })
    }
  }

  if (groups.size === 0) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-muted-foreground">
          No detections in this scan — no recommendations to display.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {[...groups.entries()].map(([family, group]) => {
        const riskParts = [...group.riskCounts.entries()]
          .sort((a, b) => {
            const order = ['critical', 'high', 'medium', 'low', 'quantum-safe']
            return order.indexOf(a[0]) - order.indexOf(b[0])
          })
          .map(([level, count]) => {
            const label = RISK_LABELS[level] ?? level
            const color = RISK_COLORS[level] ?? undefined
            return (
              <span key={level} className="font-medium" style={{ color }}>
                {count} {label}{count !== 1 ? 's' : ''}
              </span>
            )
          })

        const riskProfile = riskParts.reduce<ReactNode[]>((acc, part, i) => {
          if (i > 0) acc.push(<span key={`sep-${i}`} className="text-muted-foreground">, </span>)
          acc.push(part)
          return acc
        }, [])

        return (
          <Card key={family}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle className="text-base">{family}</CardTitle>
                  <CardDescription>
                    {group.count} artefact{group.count !== 1 ? 's' : ''} affected — {riskProfile}
                  </CardDescription>
                </div>
                <Badge variant="outline" className="shrink-0">
                  {group.count}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <p className="text-xs font-medium text-muted-foreground">Recommended replacement</p>
                <p className="font-medium">{group.recommendation.recommended_algorithm}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">FIPS reference</p>
                <p className="font-medium">{group.recommendation.fips_reference}</p>
              </div>
              <div className="sm:col-span-2">
                <p className="text-xs font-medium text-muted-foreground">Rationale</p>
                <p>{group.recommendation.rationale}</p>
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function ExportTab({ scanId }: { scanId: string }) {
  const [downloading, setDownloading] = useState<'cbom' | 'report' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleDownload(type: 'cbom' | 'report'): Promise<void> {
    setError(null)
    setDownloading(type)
    try {
      const result = type === 'cbom'
        ? await api.downloadCbom(scanId)
        : await api.downloadReport(scanId)
      triggerDownload(result.blob, result.filename)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setDownloading(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Download exports</CardTitle>
        <CardDescription>
          Export the full CycloneDX 1.6 CBOM or the executive summary report.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {error !== null && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div className="flex gap-4">
          <Button
            variant="outline"
            disabled={downloading !== null}
            onClick={() => { void handleDownload('cbom') }}
          >
            <Download className="mr-2 size-4" />
            {downloading === 'cbom' ? 'Downloading…' : 'Download CBOM (CycloneDX 1.6 JSON)'}
          </Button>
          <Button
            variant="outline"
            disabled={downloading !== null}
            onClick={() => { void handleDownload('report') }}
          >
            <Download className="mr-2 size-4" />
            {downloading === 'report' ? 'Downloading…' : 'Download Report'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}