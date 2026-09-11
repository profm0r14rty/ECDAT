/**
 * ColdStartBanner — shown during a Render free-tier cold start instead of a
 * destructive error.  Communicates that the server is waking up and the wait
 * is expected / temporary.
 *
 * Phase 38: replaces the raw error alert that previously appeared during the
 * ~60-second wake window, which looked broken to someone unfamiliar with the
 * free-tier sleep behaviour.
 */

import { Loader2 } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

export default function ColdStartBanner() {
  return (
    <Alert variant="default" className="border-accent/30 bg-accent/5">
      <Loader2 className="size-4 animate-spin text-accent" />
      <AlertTitle className="text-accent">Waking up the server</AlertTitle>
      <AlertDescription>
        The API is waking up from sleep — this can take about a minute on the
        first request. The dashboard will load automatically once the server
        is ready.
      </AlertDescription>
    </Alert>
  )
}
