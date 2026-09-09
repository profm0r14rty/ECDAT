import { useEffect } from 'react'

const SITE = 'ECDAT — Crypto Discovery Dashboard'

/**
 * Sets `document.title` for the current page, suffixed with the site name.
 * Called from page components so the browser tab reflects the route.
 */
export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = title ? `${title} · ${SITE}` : SITE
  }, [title])
}
