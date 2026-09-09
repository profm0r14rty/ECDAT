/**
 * Scan overview page: stat cards, risk distribution pie chart, top-5
 * highest-urgency artefacts, and in-flight / failure states.
 *
 * Extracted from ScanDetailPage.tsx (Phase 22) into a standalone route
 * component for the Phase 24 routing restructure. No content changes.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { PieChart, Pie, Cell, Tooltip, Legend } from 'recharts'

import {
  api,
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
import { formatDateTime } from '@/lib/format'
import { usePageTitle } from '@/lib/pageTitle'
import { RISK_COLORS, RISK_LABELS } from '@/lib/colors'
import { useScan } from '@/lib/scanContext'

// -------------------------------------------------------------------
// Inline sub-components (carried from Phase 22 ScanDetailPage.tsx)
// -------------------------------------------------------------------

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

// -------------------------------------------------------------------
// Done state: overview with stat cards, pie chart, and top-5
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

  const classicallyBrokenCount = artefacts.filter((a) => a.classically_broken).length

  const chartData = summary
    ? (Object.entries(summary.risk_level_counts) as Array<[string, number]>)
        .filter(([, count]) => count > 0)
        .map(([level, count]) => ({
          name: RISK_LABELS[level] ?? level,
          value: count,
          level,
        }))
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

      <div className="flex flex-col gap-6">
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

        {/* Risk distribution chart + Top-5 urgency side-by-side */}
        <div className="grid gap-6 md:grid-cols-2">
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
                              borderColor: RISK_COLORS[item.risk_level] ?? undefined,
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
      </div>

      <MetaCard meta={meta} />
    </>
  )
}

// -------------------------------------------------------------------
// Main page component
// -------------------------------------------------------------------

export default function ScanOverviewPage() {
  const { currentScan: scan, scanError: error } = useScan()
  usePageTitle(scan ? `Scan ${scan.id} — Overview` : 'Scan')

  // Error state
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

  // Loading skeleton
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
