import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import {
  api,
  apiErrorMessage,
  type ScanRunDetail,
  type ScanStatus,
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

const RISK_LEVEL_VARIANT: Record<
  string,
  'destructive' | 'secondary' | 'outline'
> = {
  critical: 'destructive',
  high: 'destructive',
  medium: 'outline',
  low: 'outline',
  'quantum-safe': 'secondary',
}

export default function ScanDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [scan, setScan] = useState<ScanRunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

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
 * Done state: a placeholder overview ("scan complete, N detections found")
 * behind inert tabs ready for Overview / Artefacts / Recommendations / Export
 * to be filled in per phase. The real overview UI ships in a later phase.
 */
function DoneState({
  scan,
  meta,
}: {
  scan: ScanRunDetail
  meta: Array<[string, string]>
}) {
  const detections = scan.summary?.total_detections ?? scan.files_scanned
  const summary = scan.summary

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Scan complete</CardTitle>
          <CardDescription>
            {detections !== null && detections !== undefined
              ? `${detections} detections found`
              : 'No detections recorded'}
            . The full overview lands in a later phase.
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
          {summary !== null && (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-3xl">
                    {summary.total_detections}
                  </CardTitle>
                  <CardDescription>Total detections</CardDescription>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-3xl">
                    {summary.quantum_vulnerable_count}
                  </CardTitle>
                  <CardDescription>Quantum vulnerable</CardDescription>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-3xl">
                    {summary.quantum_vulnerable_percentage.toFixed(1)}%
                  </CardTitle>
                  <CardDescription>Vulnerable share</CardDescription>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(summary.risk_level_counts).map(
                      ([level, count]) => (
                        <Badge
                          key={level}
                          variant={RISK_LEVEL_VARIANT[level] ?? 'outline'}
                        >
                          {level}: {count}
                        </Badge>
                      ),
                    )}
                  </div>
                  <CardDescription className="pt-2">Risk levels</CardDescription>
                </CardHeader>
              </Card>
            </div>
          )}
          <InertTabPlaceholder text="Detailed overview, charts and risk distribution arrive in a later phase." />
        </TabsContent>

        <TabsContent value="artefacts" className="pt-4">
          <InertTabPlaceholder text="The paginated, filterable artefact listing arrives in a later phase." />
        </TabsContent>

        <TabsContent value="recommendations" className="pt-4">
          <InertTabPlaceholder text="Per-artefact PQC migration recommendations arrive in a later phase." />
        </TabsContent>

        <TabsContent value="export" className="pt-4">
          <InertTabPlaceholder text="CycloneDX 1.6 CBOM download and report export arrive in a later phase." />
        </TabsContent>
      </Tabs>

      <MetaCard meta={meta} />
    </>
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

/** Placeholder body for a tab whose real UI ships in a later phase. */
function InertTabPlaceholder({ text }: { text: string }) {
  return (
    <Card>
      <CardContent className="pt-6 text-sm text-muted-foreground">{text}</CardContent>
    </Card>
  )
}