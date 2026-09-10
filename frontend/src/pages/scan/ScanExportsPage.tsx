/**
 * Exports route page: download CBOM and summary report as blobs.
 *
 * Extracted from ScanDetailPage.tsx (Phase 22) into a standalone route
 * component for the Phase 24 routing restructure. No content changes.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FileJson, FileText } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

import { api, apiErrorMessage } from '@/api/client'
import { useScan } from '@/lib/scanContext'
import { usePageTitle } from '@/lib/pageTitle'

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

export default function ScanExportsPage() {
  const { currentScan: scan, scanError: error, scanId } = useScan()
  const [downloading, setDownloading] = useState<'cbom' | 'report' | null>(null)
  const [dlError, setDlError] = useState<string | null>(null)

  usePageTitle(scan ? `Scan ${scan.id} — Exports` : 'Exports')

  async function handleDownload(type: 'cbom' | 'report'): Promise<void> {
    if (scanId === null) return
    setDlError(null)
    setDownloading(type)
    try {
      const result = type === 'cbom'
        ? await api.downloadCbom(scanId)
        : await api.downloadReport(scanId)
      triggerDownload(result.blob, result.filename)
    } catch (err) {
      setDlError(apiErrorMessage(err))
    } finally {
      setDownloading(null)
    }
  }

  if (error !== null && scan === null) {
    return (
      <>
        <Alert variant="destructive">
          <AlertTitle>Could not load scan</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button asChild variant="outline" className="mt-4 w-fit border-border hover:bg-accent/5 hover:text-accent">
          <Link to="/app">Back to scans</Link>
        </Button>
      </>
    )
  }

  return (
    <Card className="bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-accent/5">
      <CardHeader>
        <CardTitle className="text-base">Download exports</CardTitle>
        <CardDescription>
          Export the full CycloneDX 1.6 CBOM or the executive summary report.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {dlError !== null && (
          <Alert variant="destructive">
            <AlertDescription>{dlError}</AlertDescription>
          </Alert>
        )}
        <div className="flex flex-wrap gap-4">
          <Button
            variant="outline"
            disabled={downloading !== null}
            onClick={() => { void handleDownload('cbom') }}
            className="border-border hover:bg-accent/10 hover:text-accent"
          >
            <FileJson className="mr-2 size-4" />
            {downloading === 'cbom' ? 'Downloading…' : 'Download CBOM (CycloneDX 1.6 JSON)'}
          </Button>
          <Button
            variant="outline"
            disabled={downloading !== null}
            onClick={() => { void handleDownload('report') }}
            className="border-border hover:bg-accent/10 hover:text-accent"
          >
            <FileText className="mr-2 size-4" />
            {downloading === 'report' ? 'Downloading…' : 'Download Report'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
