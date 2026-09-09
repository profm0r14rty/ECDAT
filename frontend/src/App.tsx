import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'

import AppShell from '@/components/AppShell'
import ScanListPage from '@/pages/ScanListPage'
import { ScanProvider } from '@/lib/scanContext'
import ScanOverviewPage from '@/pages/scan/ScanOverviewPage'
import ScanArtefactsPage from '@/pages/scan/ScanArtefactsPage'
import ScanRecommendationsPage from '@/pages/scan/ScanRecommendationsPage'
import ScanExportsPage from '@/pages/scan/ScanExportsPage'

const router = createBrowserRouter([
  {
    // Landing page (Phase 25 scope — unchanged for now)
    path: '/',
    element: <ScanListPage />,
  },
  {
    // App shell — wraps all dashboard routes
    path: '/app',
    element: (
      <ScanProvider>
        <AppShell />
      </ScanProvider>
    ),
    children: [
      {
        index: true,
        element: <ScanListPage />,
      },
      {
        path: 'scans/:id',
        children: [
          // /app/scans/:id → redirect to /app/scans/:id/overview
          {
            index: true,
            element: <Navigate to="overview" replace />,
          },
          {
            path: 'overview',
            element: <ScanOverviewPage />,
          },
          {
            path: 'artefacts',
            element: <ScanArtefactsPage />,
          },
          {
            path: 'recommendations',
            element: <ScanRecommendationsPage />,
          },
          {
            path: 'exports',
            element: <ScanExportsPage />,
          },
        ],
      },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}