/**
 * Artefacts route page: wraps the existing ArtefactsTab (Phase 19)
 * with scan metadata fetched from the scan context.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
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

  return <ArtefactsTab scanId={scanId} families={families} />
}
