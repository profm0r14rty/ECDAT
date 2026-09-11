/**
 * Typed API client for the ECDAT backend.
 *
 * Every backend call in the app MUST go through this module — components never
 * call `fetch`/`axios` directly, so response shapes live in exactly one place.
 *
 * Response interfaces mirror the Pydantic response models in
 * `backend/app/routers/scans.py` (field names and nullability match 1:1).
 *
 * Base URL resolution:
 * - `VITE_API_BASE_URL`, when set, is used verbatim (e.g.
 *   `http://localhost:8000` to hit a backend on another origin, or a
 *   containerized API behind a port forward).
 * - When unset, calls go to the *same origin*: in dev that means Vite's
 *   server proxy (see `vite.config.ts`) forwards `/api` (and `/health`) to
 *   `http://localhost:8000`, so the default dev flow is CORS-free. The
 *   backend's CORS middleware exists for the set-`VITE_API_BASE_URL` case.
 */

import axios from 'axios'

/** Base URL for all API calls. Defaults to same-origin (dev proxy). */
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

const http = axios.create({ baseURL: BASE_URL })

// ---------------------------------------------------------------------------
// Types — mirror backend/app/routers/scans.py response models exactly
// ---------------------------------------------------------------------------

export type ScanSourceType = 'git_url' | 'local_path'
export type ScanStatus = 'queued' | 'running' | 'done' | 'failed'
export type RiskLevel = 'critical' | 'high' | 'medium' | 'low' | 'quantum-safe'
export type AssetType =
  | 'algorithm'
  | 'certificate'
  | 'protocol'
  | 'related-crypto-material'

/** Request body for `POST /api/scans` (mirrors `CreateScanRequest`). */
export interface CreateScanRequest {
  source_type: ScanSourceType
  target: string
}

/** `202` body for `POST /api/scans` (mirrors `ScanCreatedResponse`). */
export interface ScanCreatedResponse {
  id: string
  status: ScanStatus
}

/** One entry of `GET /api/scans` (mirrors `ScanRunListItem`). */
export interface ScanRunListItem {
  id: string
  target: string
  source_type: ScanSourceType
  status: ScanStatus
  created_at: string
  completed_at: string | null
  files_scanned: number | null
}

/** One entry of `GET /api/scans/{id}/report`'s `top_5_urgency`. */
export interface TopUrgencyItem {
  detection_id: string
  algorithm_family: string
  risk_level: RiskLevel
  urgency_ratio: number
  file_path: string
  line_number: number
}

/**
 * `export_summary()`-shaped summary from `ecdat_core.cbom_export`, served by
 * `GET /api/scans`, `GET /api/scans/{id}` and `GET /api/scans/{id}/report`.
 */
export interface ScanSummary {
  total_detections: number
  quantum_vulnerable_count: number
  quantum_vulnerable_percentage: number
  risk_level_counts: Record<RiskLevel, number>
  algorithm_family_counts: Record<string, number>
  top_5_urgency: TopUrgencyItem[]
}

/** Full scan run detail (mirrors `ScanRunDetail`); `summary` is null until done. */
export interface ScanRunDetail extends ScanRunListItem {
  error_message: string | null
  summary: ScanSummary | null
}

/** Risk assessment portion of a flattened artefact (mirrors `ArtefactRiskAssessment`). */
export interface ArtefactRiskAssessment {
  migration_time_years: number
  shelf_life_years: number
  threat_horizon_years: number
  urgency_ratio: number
  risk_level: RiskLevel
  mosca_violation: boolean
}

/** Recommendation portion of a flattened artefact (mirrors `ArtefactRecommendation`). */
export interface ArtefactRecommendation {
  recommended_algorithm: string
  fips_reference: string
  rationale: string
  latency_note: string
  migration_note: string
}

/** One artefact: detection + risk assessment + recommendation (mirrors `Artefact`). */
export interface Artefact {
  id: string
  file_path: string
  line_number: number
  matched_text: string
  asset_type: AssetType
  algorithm_family: string
  key_size_bits: number | null
  quantum_vulnerable: boolean
  classically_broken: boolean
  confidence: number
  language: string
  detection_method: string
  risk_assessment: ArtefactRiskAssessment
  recommendation: ArtefactRecommendation
}

/** Paginated artefact listing (mirrors `ArtefactListResponse`). */
export interface ArtefactListResponse {
  items: Artefact[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/** Query params for `getArtefacts` (mirrors the router's `Query` params). */
export interface ArtefactListParams {
  /** Optional risk level filter (e.g. "critical"). */
  risk_level?: RiskLevel | string
  /** Optional algorithm family filter (e.g. "RSA"). */
  algorithm_family?: string
  /** 1-indexed page number. */
  page?: number
  /** Items per page (1-500). */
  page_size?: number
}

/** PATCH body (mirrors `ArtefactOverrideRequest`); `null` = use heuristics. */
export interface ArtefactOverrideRequest {
  shelf_life_years?: number | null
  migration_time_years?: number | null
}

/** CycloneDX 1.6 CBOM document — keep generic, structure owned by ecdat_core. */
export type CbomDocument = Record<string, unknown>

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

/** Best-effort human-readable message from any thrown error. */
export function apiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data as { detail?: unknown } | undefined
    if (typeof detail?.detail === 'string') return detail.detail
    return err.message
  }
  return err instanceof Error ? err.message : 'Unknown error'
}

export const api = {
  /** `GET /health` — liveness probe; same-origin in dev, so proxied by Vite. */
  async getHealth(): Promise<string> {
    const { data } = await http.get<{ status: string }>('/health')
    return data.status
  },

  /** `POST /api/scans` — create a queued scan run. */
  async createScan(payload: CreateScanRequest): Promise<ScanCreatedResponse> {
    const { data } = await http.post<ScanCreatedResponse>('/api/scans', payload)
    return data
  },

  /** `GET /api/scans` — list scan runs, most recent first. */
  async listScans(): Promise<ScanRunListItem[]> {
    const { data } = await http.get<ScanRunListItem[]>('/api/scans')
    return data
  },

  /** `GET /api/scans/{id}` — full scan run detail (summary when done). */
  async getScan(scanId: string): Promise<ScanRunDetail> {
    const { data } = await http.get<ScanRunDetail>(
      `/api/scans/${encodeURIComponent(scanId)}`,
    )
    return data
  },

  /** `GET /api/scans/{id}/artefacts` — paginated, filterable artefact list. */
  async getArtefacts(
    scanId: string,
    params: ArtefactListParams = {},
  ): Promise<ArtefactListResponse> {
    const { data } = await http.get<ArtefactListResponse>(
      `/api/scans/${encodeURIComponent(scanId)}/artefacts`,
      { params },
    )
    return data
  },

  /** `GET /api/scans/{id}/cbom` — full CycloneDX 1.6 CBOM document. */
  async getCbom(scanId: string): Promise<CbomDocument> {
    const { data } = await http.get<CbomDocument>(
      `/api/scans/${encodeURIComponent(scanId)}/cbom`,
    )
    return data
  },

  /** `GET /api/scans/{id}/report` — the `export_summary()`-shaped report. */
  async getReport(scanId: string): Promise<ScanSummary> {
    const { data } = await http.get<ScanSummary>(
      `/api/scans/${encodeURIComponent(scanId)}/report`,
    )
    return data
  },

  /**
   * `GET /api/scans/{id}/cbom` — download the CycloneDX 1.6 CBOM as a blob.
   *
   * Returns the raw blob plus the filename from the Content-Disposition header
   * (falls back to `cbom-<scanId>.json` when the header is absent).
   */
  async downloadCbom(
    scanId: string,
  ): Promise<{ blob: Blob; filename: string }> {
    const { data, headers } = await http.get<Blob>(
      `/api/scans/${encodeURIComponent(scanId)}/cbom`,
      { responseType: 'blob' },
    )
    return {
      blob: data,
      filename: _filenameFromDisposition(headers, `cbom-${scanId}.json`),
    }
  },

  /**
   * `GET /api/scans/{id}/report` — download the summary report as a JSON blob.
   *
   * Returns the raw blob plus the filename from the Content-Disposition header
   * (falls back to `report-<scanId>.json` when the header is absent).
   */
  async downloadReport(
    scanId: string,
  ): Promise<{ blob: Blob; filename: string }> {
    const { data, headers } = await http.get<Blob>(
      `/api/scans/${encodeURIComponent(scanId)}/report`,
      { responseType: 'blob' },
    )
    return {
      blob: data,
      filename: _filenameFromDisposition(headers, `report-${scanId}.json`),
    }
  },

  /** `PATCH /api/scans/{id}/artefacts/{detectionId}` — override risk params. */
  async patchArtefact(
    scanId: string,
    detectionId: string,
    overrides: ArtefactOverrideRequest,
  ): Promise<Artefact> {
    const { data } = await http.patch<Artefact>(
      `/api/scans/${encodeURIComponent(scanId)}/artefacts/${encodeURIComponent(detectionId)}`,
      overrides,
    )
    return data
  },
}

/**
 * Extract the filename from a Content-Disposition header, e.g.
 * `attachment; filename="cbom.json"` → `"cbom.json"`.
 * Returns the provided `fallback` when the header is absent or malformed.
 */
function _filenameFromDisposition(
  headers: unknown,
  fallback: string = 'download.json',
): string {
  if (headers === null || typeof headers !== 'object') return fallback
  const header = (headers as Record<string, unknown>)['content-disposition']
  const headerStr = typeof header === 'string' ? header : ''
  const match = /filename="?([^";\n]+)"?/i.exec(headerStr)
  return match?.[1]?.trim() ?? fallback
}

export default api