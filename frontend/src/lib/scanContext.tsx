import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useParams } from 'react-router-dom'

import { api, apiErrorMessage, type ScanRunDetail } from '@/api/client'

interface ScanContextValue {
  /** The current scan loaded from the route param, or null if no scan is open / still loading. */
  currentScan: ScanRunDetail | null
  /** The scan ID from the route, or null when not under a /scans/:id route. */
  scanId: string | null
  /** Error loading the scan, if any. */
  scanError: string | null
}

const ScanContext = createContext<ScanContextValue>({
  currentScan: null,
  scanId: null,
  scanError: null,
})

/**
 * Returns the current scan context. Used by AppShell (top bar, sidebar nav
 * highlight state) and child routes that need scan metadata without a
 * duplicate fetch.
 */
export function useScan(): ScanContextValue {
  return useContext(ScanContext)
}

const POLL_INTERVAL_MS = 1500
const TERMINAL_STATUSES = new Set(['done', 'failed'])

/**
 * Provides scan context to the entire app shell subtree. Fetches and
 * (re-)polls the scan when a `:id` route param is present. When no
 * `:id` param is present (e.g. `/app` scan list), context is null.
 */
export function ScanProvider({ children }: { children: ReactNode }) {
  const { id } = useParams<{ id: string }>()
  const [currentScan, setCurrentScan] = useState<ScanRunDetail | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)

  // Reset state when the route param changes (navigating to a different scan
  // or leaving a scan route entirely).
  useEffect(() => {
    if (id === undefined) {
      setCurrentScan(null)
      setScanError(null)
      return
    }

    const scanId: string = id
    let cancelled = false
    let timerId: ReturnType<typeof setInterval> | undefined

    async function fetchScan(): Promise<void> {
      try {
        const next = await api.getScan(scanId)
        if (cancelled) return
        setCurrentScan(next)
        setScanError(null)
        if (TERMINAL_STATUSES.has(next.status)) {
          if (timerId !== undefined) {
            clearInterval(timerId)
            timerId = undefined
          }
        }
      } catch (err) {
        if (!cancelled) setScanError(apiErrorMessage(err))
      }
    }

    void fetchScan()
    timerId = setInterval(() => { void fetchScan() }, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      if (timerId !== undefined) clearInterval(timerId)
    }
  }, [id])

  return (
    <ScanContext.Provider value={{ currentScan, scanId: id ?? null, scanError }}>
      {children}
    </ScanContext.Provider>
  )
}
