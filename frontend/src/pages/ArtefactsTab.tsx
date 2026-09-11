import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { ChevronLeft, ChevronRight, Loader2, RotateCcw, Search } from 'lucide-react'

import {
  api,
  apiErrorMessage,
  type Artefact,
  type ArtefactListResponse,
  type RiskLevel,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { RISK_LABELS } from '@/lib/colors'
import { truncatePath } from '@/lib/paths'
import { ClassicallyBrokenBadge, QuantumVulnerableBadge, RiskLevelBadge, StatusDash } from './artefacts/badges'
import ArtefactDetailDialog from './artefacts/ArtefactDetailDialog'

/** The five canonical risk levels, ordered by severity (palette from Phase 18). */
const RISK_LEVELS: ReadonlyArray<RiskLevel> = [
  'critical',
  'high',
  'medium',
  'low',
  'quantum-safe',
]

/** Page-size choices wired straight to the API's `page_size` query param. */
const PAGE_SIZES: ReadonlyArray<number> = [10, 25, 50, 100]

/** Sentinel select value meaning "no filter" (the API param is omitted). */
const ALL = 'all'

/** Props for {@link ArtefactsTab}. */
interface ArtefactsTabProps {
  scanId: string
  families: string[]
  highlightId?: string | null
}

/**
 * The Artefacts tab: a filterable, paginated table of the scan's artefacts
 * driven by `GET /api/scans/{id}/artefacts` (risk-level and algorithm-family
 * filters, page/page_size/total_pages pagination), with a row click opening a
 * detail dialog whose risk-override PATCH updates the row in place.
 */
export default function ArtefactsTab({ scanId, families, highlightId }: ArtefactsTabProps) {
  const highlightRef = useRef(highlightId)
  const [riskLevel, setRiskLevel] = useState<string>(ALL)
  const [family, setFamily] = useState<string>(ALL)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [reloadKey, setReloadKey] = useState(0)
  const [data, setData] = useState<ArtefactListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Artefact | null>(null)
  const highlightApplied = useRef(false)
  const [highlightedId, setHighlightedId] = useState<string | null>(null)

  // Family options are data-driven from this scan's results: prefer the
  // summary's family counts (complete), fall back to families seen on the
  // current page when the summary is unavailable.
  const familyOptions = useMemo(() => {
    const seen = families.length > 0
      ? families
      : Array.from(new Set(data?.items.map((item) => item.algorithm_family) ?? []))
    return [...seen].sort()
  }, [families, data?.items])

  // Fetch the current page whenever the filters, page, or page size change.
  // Loading is armed by the event handlers that cause the refetch (React
  // discourages synchronous setState in effects); the first mount starts
  // with loading=true.
  useEffect(() => {
    let cancelled = false

    async function load(): Promise<void> {
      try {
        const fetchPageSize = highlightRef.current ? 500 : pageSize
        const res = await api.getArtefacts(scanId, {
          risk_level: riskLevel === ALL ? undefined : riskLevel,
          algorithm_family: family === ALL ? undefined : family,
          page: highlightRef.current ? 1 : page,
          page_size: fetchPageSize,
        })
        if (cancelled) return
        // An override on the last row of the last page can shrink total_pages
        // below the current page; recover by re-requesting the new last page.
        if (res.items.length === 0 && res.total > 0 && page > res.total_pages) {
          setPage(res.total_pages)
          return
        }
        setData(res)
        setError(null)
      } catch (err) {
        if (!cancelled) setError(apiErrorMessage(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [scanId, riskLevel, family, page, pageSize, reloadKey])

  function armReload(): void {
    setLoading(true)
    setError(null)
  }

  useEffect(() => {
    const hl = highlightRef.current
    if (!hl || highlightApplied.current || !data) return
    const target = data.items.find((a) => a.id === hl)
    if (!target) return
    highlightApplied.current = true
    setHighlightedId(hl)
    requestAnimationFrame(() => {
      document.querySelector<HTMLElement>(`[data-artefact-id="${hl}"]`)
        ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    })
    const timer = setTimeout(() => setHighlightedId(null), 3000)
    return () => clearTimeout(timer)
  }, [data])

  function handleRiskLevelChange(value: string): void {
    armReload()
    setRiskLevel(value)
    setPage(1)
  }

  function handleFamilyChange(value: string): void {
    armReload()
    setFamily(value)
    setPage(1)
  }

  function handlePageSizeChange(value: string): void {
    armReload()
    setPageSize(Number(value))
    setPage(1)
  }

  function handlePageChange(next: number): void {
    armReload()
    setPage(Math.max(1, Math.min(next, totalPages || 1)))
  }

  function clearFilters(): void {
    armReload()
    setRiskLevel(ALL)
    setFamily(ALL)
    setPage(1)
  }

  function matchesFilters(artefact: Artefact): boolean {
    if (riskLevel !== ALL && artefact.risk_assessment.risk_level !== riskLevel) return false
    if (family !== ALL && artefact.algorithm_family !== family) return false
    return true
  }

  // PATCH result from the dialog: update the row in place; if the new risk
  // level fell out of the active filter, refetch the page so totals stay
  // consistent with the server's filtered view.
  function handleSaved(updated: Artefact): void {
    setSelected(updated)
    setData((prev) =>
      prev === null
        ? prev
        : {
            ...prev,
            items: prev.items.map((item) =>
              item.id === updated.id ? updated : item,
            ),
          },
    )
    if (!matchesFilters(updated)) {
      armReload()
      setReloadKey((key) => key + 1)
    }
  }

  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 0
  const hasFilters = riskLevel !== ALL || family !== ALL

  return (
    <Card className="bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-accent/5">
      <CardHeader>
        <CardTitle className="text-base">Artefacts</CardTitle>
        <CardDescription>
          {total} artefact{total === 1 ? '' : 's'} detected in this scan
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* Filter controls */}
        <div className="flex flex-wrap items-end gap-3 p-3 rounded-md border border-border bg-bg/30">
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs">Risk level</Label>
            <Select value={riskLevel} onValueChange={handleRiskLevelChange}>
              <SelectTrigger className="w-44">
                <SelectValue placeholder="All risk levels" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All risk levels</SelectItem>
                {RISK_LEVELS.map((level) => (
                  <SelectItem key={level} value={level}>
                    {RISK_LABELS[level]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-xs">Algorithm family</Label>
            <Select value={family} onValueChange={handleFamilyChange}>
              <SelectTrigger className="w-44">
                <SelectValue placeholder="All families" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All families</SelectItem>
                {familyOptions.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-xs">Page size</Label>
            <Select value={String(pageSize)} onValueChange={handlePageSizeChange}>
              <SelectTrigger className="w-24">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZES.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5 flex-1 min-w-[200px]">
            <Label className="text-xs">Search</Label>
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Filter by file, algorithm, matched text…"
                className="pl-8 w-full max-w-xs"
                onChange={(_e) => {
                  // Search is client-side on current page data
                  // Could be extended to server-side if needed
                }}
              />
            </div>
          </div>

          {hasFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              <RotateCcw />
              Clear filters
            </Button>
          )}
        </div>

        {/* Artefact table */}
        <div className={`transition-opacity ${loading && data !== null ? 'pointer-events-none opacity-50' : ''}`}>
          <Table>
            <TableHeader className="border-border">
              <TableRow>
                <TableHead>Algorithm</TableHead>
                <TableHead>File</TableHead>
                <TableHead className="text-right">Line</TableHead>
                <TableHead>Risk level</TableHead>
                <TableHead title="Broken by Shor's/Grover's quantum algorithms">Quantum</TableHead>
                <TableHead title="Already broken by classical attacks today">Classical</TableHead>
                <TableHead className="text-right">Confidence</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && data === null ? (
                <SkeletonRows />
              ) : error !== null ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-6 text-center text-sm text-destructive">
                    {error}
                  </TableCell>
                </TableRow>
              ) : data !== null && data.items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                    No artefacts match the current filters.
                    {hasFilters && (
                      <Button variant="link" size="sm" onClick={clearFilters} className="ml-1 h-auto p-0">
                        Clear filters
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ) : (
                data?.items.map((artefact, _index) => (
                  <TableRow
                    key={artefact.id}
                    data-artefact-id={artefact.id}
                    className={`cursor-pointer stagger-enter${artefact.id === highlightedId ? ' ring-2 ring-accent/70 bg-accent/5' : ''}`}
                    style={{ '--stagger-index': Math.min(_index, 8) } as CSSProperties}
                    data-state={selected?.id === artefact.id ? 'selected' : undefined}
                    onClick={() => setSelected(artefact)}
                  >
                    <TableCell className="font-mono text-xs font-medium">
                      {artefact.algorithm_family}
                    </TableCell>
                    <TableCell>
                      <span
                        className="block max-w-56 truncate font-mono text-xs"
                        title={artefact.file_path}
                      >
                        {truncatePath(artefact.file_path)}
                      </span>
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {artefact.line_number}
                    </TableCell>
                    <TableCell>
                      <RiskLevelBadge level={artefact.risk_assessment.risk_level} />
                    </TableCell>
                    <TableCell>
                      {artefact.quantum_vulnerable ? (
                        <QuantumVulnerableBadge />
                      ) : (
                        <StatusDash label="Not vulnerable to Shor's/Grover's quantum algorithms" />
                      )}
                    </TableCell>
                    <TableCell>
                      {artefact.classically_broken ? (
                        <ClassicallyBrokenBadge />
                      ) : (
                        <StatusDash label="Not broken by any known classical attack" />
                      )}
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {Math.round(artefact.confidence * 100)}%
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between pt-1 text-sm text-muted-foreground border-t border-border">
          <span>
            {total} artefact{total === 1 ? '' : 's'}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1 || loading}
              onClick={() => handlePageChange(page - 1)}
              className="border-border hover:bg-accent/5 hover:text-accent"
            >
              <ChevronLeft />
              Previous
            </Button>
            <span className="text-xs text-foreground/70">
              Page {data !== null ? page : '—'} of {totalPages || 1}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={totalPages === 0 || page >= totalPages || loading}
              onClick={() => handlePageChange(page + 1)}
              className="border-border hover:bg-accent/5 hover:text-accent"
            >
              Next
              <ChevronRight />
            </Button>
          </div>
        </div>

        {loading && data === null && (
          <div className="flex items-center justify-center gap-2 py-4 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin text-accent" />
            Loading artefacts…
          </div>
        )}
      </CardContent>

      <ArtefactDetailDialog
        key={selected?.id ?? 'closed'}
        scanId={scanId}
        artefact={selected}
        onClose={() => setSelected(null)}
        onSaved={handleSaved}
      />
    </Card>
  )
}

/** Placeholder rows shown while the first page is being fetched. */
function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 6 }, (_, index) => (
        <TableRow key={index} className="stagger-enter" style={{ '--stagger-index': index } as CSSProperties}>
          <TableCell><Skeleton className="h-4 w-16" /></TableCell>
          <TableCell><Skeleton className="h-4 w-56" /></TableCell>
          <TableCell><Skeleton className="ml-auto h-4 w-8" /></TableCell>
          <TableCell><Skeleton className="h-4 w-20" /></TableCell>
          <TableCell><Skeleton className="h-4 w-24" /></TableCell>
          <TableCell><Skeleton className="h-4 w-24" /></TableCell>
          <TableCell><Skeleton className="ml-auto h-4 w-10" /></TableCell>
        </TableRow>
      ))}
    </>
  )
}