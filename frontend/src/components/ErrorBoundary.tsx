import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * Top-level error boundary: catches render errors anywhere in the tree and
 * shows a recoverable fallback instead of a blank page. A "Reload" button
 * retries the current route; the API-unreachable case is additionally
 * surfaced by the pages' own error states (this covers unexpected crashes).
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('ECDAT render error:', error, info.componentStack)
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center gap-4 px-6 py-10 text-center">
          <AlertTriangle className="size-10 text-destructive" />
          <Alert variant="destructive" className="w-full">
            <AlertTitle>Something went wrong</AlertTitle>
            <AlertDescription>
              The dashboard hit an unexpected error. Reload to try again.
            </AlertDescription>
          </Alert>
          <Button onClick={() => window.location.reload()}>Reload</Button>
        </main>
      )
    }
    return this.props.children
  }
}
