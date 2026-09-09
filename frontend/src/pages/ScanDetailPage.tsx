import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api, apiErrorMessage, type ScanRunDetail } from '@/api/client'
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

const RISK_LEVEL_VARIANT: Record<string, 'destructive' | 'secondary' | 'outline'> = {
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

  const load = useCallback(() => {
    if (id === undefined) return
    setError(null)
    setScan(null)
    api
      .getScan(id)
      .then(setScan)
      .catch((err: unknown) => setError(apiErrorMessage(err)))
  }, [id])

  useEffect(load, [load])

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

  const summary = scan.summary

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Scan {scan.id}
          </h1>
          <p className="font-mono text-sm text-muted-foreground">
            {scan.target}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={scan.status === 'done' ? 'default' : 'outline'}>
            {scan.status}
          </Badge>
          <Button variant="outline" size="sm" onClick={load}>
            Refresh
          </Button>
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Overview</CardTitle>
          <CardDescription>
            Risk statistics appear once the scan completes (queued → running → done).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
          <span>
            Source:{' '}
            <span className="font-medium">{scan.source_type}</span>
          </span>
          <span>
            Created:{' '}
            <span className="font-medium">
              {formatDateTime(scan.created_at)}
            </span>
          </span>
          <span>
            Completed:{' '}
            <span className="font-medium">
              {formatDateTime(scan.completed_at)}
            </span>
          </span>
          <span>
            Files scanned:{' '}
            <span className="font-medium">{scan.files_scanned ?? '—'}</span>
          </span>
        </CardContent>
      </Card>

      {summary !== null && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-3xl">{summary.total_detections}</CardTitle>
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

      <Card>
        <CardContent className="pt-6 text-sm text-muted-foreground">
          Artefact listing, risk overrides, charts and the CBOM download land in
          the next phases.
        </CardContent>
      </Card>
    </main>
  )
}