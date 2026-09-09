import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { FormEvent } from 'react'

import {
  api,
  apiErrorMessage,
  type CreateScanRequest,
  type ScanRunListItem,
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

type HealthState = 'checking' | 'ok' | 'unreachable'

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
      navigate(`/scans/${created.id}`)
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
          <div className="grid grid-cols-[180px_1fr] items-center gap-4">
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

function ScanList() {
  const navigate = useNavigate()
  const [scans, setScans] = useState<ScanRunListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .listScans()
      .then(setScans)
      .catch((err: unknown) => setError(apiErrorMessage(err)))
  }, [])

  useEffect(load, [load])

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
                    onClick={() => navigate(`/scans/${scan.id}`)}
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
  const [health, setHealth] = useState<HealthState>('checking')

  useEffect(() => {
    api
      .getHealth()
      .then((status) => setHealth(status === 'ok' ? 'ok' : 'unreachable'))
      .catch(() => setHealth('unreachable'))
  }, [])

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">ECDAT</h1>
          <p className="text-sm text-muted-foreground">
            Enterprise Cryptographic Discovery &amp; Analysis Tool
          </p>
        </div>
        <Badge
          variant={health === 'ok' ? 'default' : 'destructive'}
          aria-label={`Backend health: ${health}`}
        >
          {health === 'checking'
            ? 'Checking backend…'
            : health === 'ok'
              ? 'Backend ok'
              : 'Backend unreachable'}
        </Badge>
      </header>

      <NewScanForm />
      <ScanList />
    </main>
  )
}