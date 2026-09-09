import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'

import AppShell from '@/components/AppShell'
import LandingPage from '@/pages/LandingPage'
import ScanListPage from '@/pages/ScanListPage'
import { ScanProvider } from '@/lib/scanContext'
import ScanOverviewPage from '@/pages/scan/ScanOverviewPage'
import ScanArtefactsPage from '@/pages/scan/ScanArtefactsPage'
import ScanRecommendationsPage from '@/pages/scan/ScanRecommendationsPage'
import ScanExportsPage from '@/pages/scan/ScanExportsPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <LandingPage />,
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
        element: <Navigate to="scans" replace />,
      },
      {
        path: 'scans',
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