import { type ReactNode } from 'react'
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
  useResolvedPath,
  useRoutes,
} from 'react-router-dom'
import { CirclePlus, LayoutDashboard, List, Lock, FileBarChart, Download } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { type ScanStatus } from '@/api/client'
import { useScan } from '@/lib/scanContext'

// -------------------------------------------------------------------
// Sidebar nav-item helpers
// -------------------------------------------------------------------

/** Badge variant driven by the scan's current status. */
const STATUS_VARIANT: Record<ScanStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  queued: 'secondary',
  running: 'outline',
  done: 'default',
  failed: 'destructive',
}

function SidebarLink({
  to,
  icon: Icon,
  label,
  disabled = false,
  onClick,
}: {
  to: string
  icon: React.FC<{ className?: string }>
  label: string
  disabled?: boolean
  onClick?: () => void
}) {
  const resolved = useResolvedPath(to)
  // isSamePath: check whether the current route starts with this nav item's path.
  // NavLink doesn't support "active if current URL starts with this path" out of the box.
  const match = useRoutes([{ path: resolved.pathname, element: null }])
  const isActive = match !== null

  if (disabled) {
    return (
      <span className="flex items-center justify-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-foreground/30 select-none md:justify-start md:px-3">
        <Icon className="size-4 shrink-0" />
        <span className="hidden md:inline">{label}</span>
      </span>
    )
  }

  return (
    <NavLink
      to={to}
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`flex items-center justify-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors md:justify-start md:px-3 ${
        isActive
          ? 'bg-sidebar-active font-medium text-accent'
          : 'text-foreground/70 hover:bg-sidebar-active/50 hover:text-foreground'
      }`}
    >
      <Icon className="size-4 shrink-0" />
      <span className="hidden md:inline">{label}</span>
    </NavLink>
  )
}

/** Discrete section heading inside the sidebar. */
function SidebarSection({ children }: { children: ReactNode }) {
  return (
    <span className="mt-4 mb-1 hidden px-3 text-[11px] font-semibold uppercase tracking-wider text-foreground/30 md:block">
      {children}
    </span>
  )
}

// -------------------------------------------------------------------
// AppShell layout
// -------------------------------------------------------------------

export default function AppShell() {
  const { currentScan, scanId } = useScan()
  const hasScan = currentScan !== null || scanId !== null
  const location = useLocation()

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ---- Sidebar ----
          Below `md` the sidebar collapses to an icon-only rail (labels hidden,
          icons centered, nav items keep `title`/`aria-label` for accessibility)
          so the dashboard stays usable on narrow/phone viewports. */}
      <aside className="flex w-14 shrink-0 flex-col bg-sidebar border-r border-border md:w-64">
        {/* Brand — clicks through to the landing page */}
        <Link
          to="/"
          title="Back to landing page"
          className="flex h-12 items-center justify-center gap-2 border-b border-border px-2 transition-colors hover:bg-sidebar-active/50 md:justify-start md:px-4"
        >
          <Lock className="size-4 shrink-0 text-accent" />
          <span className="hidden text-sm font-semibold tracking-tight text-foreground md:block">ECDAT</span>
        </Link>

        {/* Primary nav */}
        <nav className="flex flex-col gap-0.5 px-2 py-3">
          <SidebarLink to="/app/scans" icon={List} label="Scan Runs" />
          <SidebarLink to="/app/scans" icon={CirclePlus} label="New Scan" />

          {/* Scan-contextual nav — only present when a scan is open */}
          {hasScan && (
            <>
              <SidebarSection>Current scan</SidebarSection>
              <SidebarLink
                to={`/app/scans/${scanId ?? ''}/overview`}
                icon={LayoutDashboard}
                label="Overview"
                disabled={!hasScan}
              />
              <SidebarLink
                to={`/app/scans/${scanId ?? ''}/artefacts`}
                icon={FileBarChart}
                label="Artefacts"
                disabled={!hasScan}
              />
              <SidebarLink
                to={`/app/scans/${scanId ?? ''}/recommendations`}
                icon={List}
                label="Recommendations"
                disabled={!hasScan}
              />
              <SidebarLink
                to={`/app/scans/${scanId ?? ''}/exports`}
                icon={Download}
                label="Exports"
                disabled={!hasScan}
              />
            </>
          )}
        </nav>

        {/* Footer spacer */}
        <div className="mt-auto hidden border-t border-border px-4 py-3 md:block">
          <p className="text-[11px] text-foreground/30">Crypto Discovery Dashboard</p>
        </div>
      </aside>

      {/* ---- Main area ---- */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <TopBar scan={currentScan} />

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
            <div key={location.pathname} className="page-enter">
              <Outlet />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

// -------------------------------------------------------------------
// Top bar
// -------------------------------------------------------------------

function TopBar({ scan }: { scan: import('@/api/client').ScanRunDetail | null }) {
  const navigate = useNavigate()

  return (
    <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-4 md:px-6">
      {/* Left: current scan info (only when a scan is open) */}
      <div className="flex items-center gap-3 min-w-0">
        {scan !== null ? (
          <>
            <span className="truncate font-mono text-sm text-foreground/80" title={scan.target}>
              {scan.target}
            </span>
            <Badge variant={STATUS_VARIANT[scan.status]} className="shrink-0 text-xs">
              {scan.status}
            </Badge>
          </>
        ) : (
          <span className="text-sm text-foreground/40">ECDAT Dashboard</span>
        )}
      </div>

      {/* Right: quick-action */}
      <Button
        size="sm"
        variant="outline"
        className="shrink-0 border-accent/30 text-accent hover:bg-accent/10 hover:text-accent"
        onClick={() => { navigate('/app/scans') }}
      >
        <CirclePlus className="mr-1.5 size-3.5" />
        Run new scan
      </Button>
    </header>
  )
}
