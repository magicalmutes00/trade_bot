/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute API origin (e.g. https://bof-edge-api.onrender.com). Empty = same-origin. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
