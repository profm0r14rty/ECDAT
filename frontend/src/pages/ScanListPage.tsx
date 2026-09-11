import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { FormEvent } from 'react'

import {
  api,
  apiErrorMessage,
  type CreateScanRequest,
  type ScanRunListItem,
  type ScanStatus,
} from '@/api/client'
import ColdStartBanner from '@/components/ColdStartBanner'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDateTime } from '@/lib/format'
import { usePageTitle } from '@/lib/pageTitle'

/**
 * Three-state health model:
 * - `'checking'` — initial state before the first probe completes.
 * - `'waking-up'` — at least one probe has failed, but not enough time has
 *   passed to distinguish a Render free-tier cold start (~60 s) from a real
 *   outage.  The badge shows a neutral "Backend waking up…" message so the
 *   user doesn't panic.
 * - `'ok'` — the most recent probe succeeded.
 * - `'unreachable'` — probes have been failing for longer than
 *   `WAKE_UP_GRACE_MS`, indicating a genuine outage rather than a cold start.
 */
type HealthState = 'checking' | 'waking-up' | 'ok' | 'unreachable'

/**
 * After the first failed health probe, wait this long before switching from
 * `'waking-up'` to `'unreachable'`.  Render free-tier cold starts take ~60 s;
 * 90 s gives comfortable headroom without making users wait too long when the
 * backend is genuinely down.
 */
const WAKE_UP_GRACE_MS = 90_000
const COLD_START_DELAY_MS = 3_000

/** How often to re-probe the backend health endpoint (ms). */
const HEALTH_POLL_INTERVAL_MS = 30_000

const STATUS_VARIANT: Record<ScanStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  queued: 'secondary',
  running: 'outline',
  done: 'default',
  failed: 'destructive',
}

function NewScanForm() {
  const navigate = useNavigate()
  const [form, setForm] = useState<CreateScanRequest>({
    source_type: 'git_url',
    target: '',
  })
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (form.target.trim() === '') return
    setCreating(true)
    setError(null)
    try {
      const created = await api.createScan(form)
      navigate(`/app/scans/${created.id}/overview`)
    } catch (err) {
      setError(apiErrorMessage(err))
      setCreating(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New scan</CardTitle>
        <CardDescription>
          Submit a Git URL or a local path to a codebase for crypto-artefact
          discovery.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-[180px_1fr]">
            <Label htmlFor="source-type">Source type</Label>
            <select
              id="source-type"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
              value={form.source_type}
              onChange={(e) =>
                setForm({ ...form, source_type: e.target.value as CreateScanRequest['source_type'] })
              }
            >
              <option value="git_url">Git URL</option>
              <option value="local_path">Local path</option>
            </select>
            <Label htmlFor="target">Target</Label>
            <Input
              id="target"
              placeholder={
                form.source_type === 'git_url'
                  ? 'https://github.com/org/repo.git'
                  : '/path/to/codebase'
              }
              value={form.target}
              onChange={(e) => setForm({ ...form, target: e.target.value })}
            />
          </div>
          {error !== null && (
            <Alert variant="destructive">
              <AlertTitle>Failed to create scan</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" disabled={creating || form.target.trim() === ''}>
            {creating ? 'Starting…' : 'Start scan'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function ScanList({ onBackendReachable }: { onBackendReachable: () => void }) {
  const navigate = useNavigate()
  const [scans, setScans] = useState<ScanRunListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [coldStartPending, setColdStartPending] = useState(false)
  const coldStartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const coldStartGraceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(() => {
    api
      .listScans()
      .then((data) => {
        setScans(data)
        setError(null)
        onBackendReachable()
        setColdStartPending(false)
        if (coldStartTimerRef.current !== null) {
          clearTimeout(coldStartTimerRef.current)
          coldStartTimerRef.current = null
        }
        if (coldStartGraceRef.current !== null) {
          clearTimeout(coldStartGraceRef.current)
          coldStartGraceRef.current = null
        }
      })
      .catch((err: unknown) => setError(apiErrorMessage(err)))
  }, [onBackendReachable])

  useEffect(() => {
    coldStartTimerRef.current = setTimeout(() => {
      setColdStartPending(true)
    }, COLD_START_DELAY_MS)

    load()

    return () => {
      if (coldStartTimerRef.current !== null) clearTimeout(coldStartTimerRef.current)
      if (coldStartGraceRef.current !== null) clearTimeout(coldStartGraceRef.current)
    }
  }, [load])

  useEffect(() => {
    coldStartGraceRef.current = setTimeout(() => {
      setColdStartPending(false)
    }, WAKE_UP_GRACE_MS)
    return () => {
      if (coldStartGraceRef.current !== null) clearTimeout(coldStartGraceRef.current)
    }
  }, [])

  if (coldStartPending && (scans === null || error !== null)) {
    return <ColdStartBanner />
  }

  if (error !== null) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Could not load scans</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Scan runs</CardTitle>
        <CardDescription>Most recent first.</CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Status</TableHead>
              <TableHead>Target</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Files</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {scans === null
              ? Array.from({ length: 4 }, (_, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      <Skeleton className="h-5 w-16" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-5 w-64" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-5 w-32" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-5 w-10" />
                    </TableCell>
                  </TableRow>
                ))
              : scans.map((scan) => (
                  <TableRow
                    key={scan.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/app/scans/${scan.id}`)}
                  >
                    <TableCell>
                      <Badge variant={STATUS_VARIANT[scan.status]}>
                        {scan.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {scan.target}
                    </TableCell>
                    <TableCell>{formatDateTime(scan.created_at)}</TableCell>
                    <TableCell>{scan.files_scanned ?? '—'}</TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export default function ScanListPage() {
  usePageTitle('Scan runs')
  const [health, setHealth] = useState<HealthState>('checking')
  const wakeUpTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const probe = useCallback(() => {
    api
      .getHealth()
      .then((status) => {
        if (wakeUpTimerRef.current !== null) {
          clearTimeout(wakeUpTimerRef.current)
          wakeUpTimerRef.current = null
        }
        setHealth(status === 'ok' ? 'ok' : 'unreachable')
      })
      .catch(() => {
        setHealth((prev) => {
          if (prev === 'ok' || prev === 'checking') {
            if (wakeUpTimerRef.current === null) {
              wakeUpTimerRef.current = setTimeout(() => {
                wakeUpTimerRef.current = null
                setHealth('unreachable')
              }, WAKE_UP_GRACE_MS)
            }
            return 'waking-up'
          }
          return prev
        })
      })
  }, [])

  useEffect(() => {
    probe()
    const interval = setInterval(probe, HEALTH_POLL_INTERVAL_MS)
    return () => {
      clearInterval(interval)
      if (wakeUpTimerRef.current !== null) clearTimeout(wakeUpTimerRef.current)
    }
  }, [probe])

  const handleBackendReachable = useCallback(() => {
    if (wakeUpTimerRef.current !== null) {
      clearTimeout(wakeUpTimerRef.current)
      wakeUpTimerRef.current = null
    }
    setHealth('ok')
  }, [])

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">ECDAT</h1>
          <p className="text-sm text-muted-foreground">
            Enterprise Cryptographic Discovery &amp; Analysis Tool
          </p>
        </div>
        <Badge
          variant={
            health === 'ok'
              ? 'default'
              : health === 'waking-up'
                ? 'outline'
                : 'destructive'
          }
          aria-label={`Backend health: ${health}`}
        >
          {health === 'checking'
            ? 'Checking backend…'
            : health === 'ok'
              ? 'Backend ok'
              : health === 'waking-up'
                ? 'Backend waking up…'
                : 'Backend unreachable'}
        </Badge>
      </header>

      <NewScanForm />
      <ScanList onBackendReachable={handleBackendReachable} />
    </main>
  )
}