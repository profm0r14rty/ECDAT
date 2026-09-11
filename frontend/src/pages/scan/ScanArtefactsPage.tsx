/**
 * Artefacts route page: wraps the existing ArtefactsTab (Phase 19)
 * with scan metadata fetched from the scan context.
 *
 * Supports a `?highlight=<detection_id>` query parameter: when present,
 * ArtefactsTab auto-scrolls to the matching artefact row and applies a
 * temporary highlight ring.  The param is consumed once, then cleared
 * from the URL to avoid re-triggering on future navigations within the
 * same page.
 */

import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useScan } from '@/lib/scanContext'
import { usePageTitle } from '@/lib/pageTitle'
import ArtefactsTab from '@/pages/ArtefactsTab'
import ColdStartBanner from '@/components/ColdStartBanner'

export default function ScanArtefactsPage() {
  const { currentScan: scan, scanError: error, scanId, coldStartPending } = useScan()
  const [families, setFamilies] = useState<string[]>([])
  const [searchParams, setSearchParams] = useSearchParams()
  const highlightId = searchParams.get('highlight')

  // Consume the highlight param once so it doesn't re-trigger on back/forward.
  useEffect(() => {
    if (highlightId) {
      // Small delay: let the browser apply the URL first, then clear the param
      // from the address bar without a full navigation.
      const timer = setTimeout(() => {
        setSearchParams((prev) => {
          prev.delete('highlight')
          return prev
        }, { replace: true })
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [highlightId, setSearchParams])

  usePageTitle(scan ? `Scan ${scan.id} — Artefacts` : 'Artefacts')

  useEffect(() => {
    if (scan?.summary === null || scan?.summary === undefined) return
    setFamilies(Object.keys(scan.summary.algorithm_family_counts))
  }, [scan?.summary])

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

  if (scan === null || scanId === null) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (scan.status === 'failed') {
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
      </>
    )
  }

  return <ArtefactsTab scanId={scanId} families={families} highlightId={highlightId} />
}
