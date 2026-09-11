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
  /**
   * `true` while the initial scan fetch is taking long enough to suggest a
   * Render free-tier cold start (~60 s) rather than a genuine error.  When
   * this is `true` and `scanError` is non-null, consumers should show a
   * non-destructive "warming up" banner instead of a scary red error alert.
   *
   * Clears automatically when the first fetch succeeds, or after
   * `COLD_START_GRACE_MS` elapses without success.
   */
  coldStartPending: boolean
}

const ScanContext = createContext<ScanContextValue>({
  currentScan: null,
  scanId: null,
  scanError: null,
  coldStartPending: false,
})

export function useScan(): ScanContextValue {
  return useContext(ScanContext)
}

const POLL_INTERVAL_MS = 1500
const TERMINAL_STATUSES = new Set(['done', 'failed'])

/**
 * After the first scan fetch takes this long without succeeding, assume it's
 * a Render free-tier cold start rather than a genuine error.  3 s gives the
 * normal fetch path time to succeed or timeout (axios default is 5 s) before
 * we flip the cold-start heuristic.
 */
const COLD_START_DELAY_MS = 3_000

/**
 * Maximum time to show the cold-start banner before falling back to the
 * real error.  Aligns with the health badge's 90 s grace period in
 * ScanListPage — both cover the same Render wake window.
 */
const COLD_START_GRACE_MS = 90_000

export function ScanProvider({ children }: { children: ReactNode }) {
  const { id } = useParams<{ id: string }>()
  const [currentScan, setCurrentScan] = useState<ScanRunDetail | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)
  const [coldStartPending, setColdStartPending] = useState(false)

  useEffect(() => {
    if (id === undefined) {
      setCurrentScan(null)
      setScanError(null)
      setColdStartPending(false)
      return
    }

    const scanId: string = id
    let cancelled = false
    let timerId: ReturnType<typeof setInterval> | undefined
    let coldStartTimerId: ReturnType<typeof setTimeout> | undefined
    let coldStartGraceId: ReturnType<typeof setTimeout> | undefined

    coldStartTimerId = setTimeout(() => {
      if (!cancelled) setColdStartPending(true)
    }, COLD_START_DELAY_MS)

    async function fetchScan(): Promise<void> {
      try {
        const next = await api.getScan(scanId)
        if (cancelled) return
        setCurrentScan(next)
        setScanError(null)
        setColdStartPending(false)
        if (coldStartTimerId !== undefined) {
          clearTimeout(coldStartTimerId)
          coldStartTimerId = undefined
        }
        if (coldStartGraceId !== undefined) {
          clearTimeout(coldStartGraceId)
          coldStartGraceId = undefined
        }
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

    coldStartGraceId = setTimeout(() => {
      if (!cancelled) setColdStartPending(false)
    }, COLD_START_GRACE_MS)

    return () => {
      cancelled = true
      if (timerId !== undefined) clearInterval(timerId)
      if (coldStartTimerId !== undefined) clearTimeout(coldStartTimerId)
      if (coldStartGraceId !== undefined) clearTimeout(coldStartGraceId)
    }
  }, [id])

  return (
    <ScanContext.Provider value={{ currentScan, scanId: id ?? null, scanError, coldStartPending }}>
      {children}
    </ScanContext.Provider>
  )
}
