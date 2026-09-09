/**
 * Recommendations route page: groups artefacts by algorithm family
 * into an executive-style summary with NIST PQC replacements.
 *
 * Extracted from ScanDetailPage.tsx (Phase 22) into a standalone route
 * component for the Phase 24 routing restructure. No content changes.
 */

import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
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

import { api, apiErrorMessage, type Artefact } from '@/api/client'
import { useScan } from '@/lib/scanContext'
import { usePageTitle } from '@/lib/pageTitle'
import { RISK_COLORS, RISK_LABELS } from '@/lib/colors'

export default function ScanRecommendationsPage() {
  const { currentScan: scan, scanError: error, scanId } = useScan()
  const [artefacts, setArtefacts] = useState<Artefact[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  usePageTitle(scan ? `Scan ${scan.id} — Recommendations` : 'Recommendations')

  useEffect(() => {
    if (scanId === null) return
    let cancelled = false

    async function load(): Promise<void> {
      try {
        const res = await api.getArtefacts(scanId!, { page: 1, page_size: 500 })
        if (!cancelled) setArtefacts(res.items)
      } catch (err) {
        if (!cancelled) setLoadError(apiErrorMessage(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => { cancelled = true }
  }, [scanId])

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

  if (loading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  if (loadError !== null) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Could not load artefacts</AlertTitle>
        <AlertDescription>{loadError}</AlertDescription>
      </Alert>
    )
  }

  // Group artefacts by algorithm family
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
