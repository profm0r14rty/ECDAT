/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL the API client targets; defaults to same-origin (dev proxy). */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}