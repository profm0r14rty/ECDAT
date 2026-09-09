import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import ScanDetailPage from '@/pages/ScanDetailPage'
import ScanListPage from '@/pages/ScanListPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <ScanListPage />,
  },
  {
    // Scan detail: grows into overview/artefacts/etc. views (tabs or
    // sub-routes) in the following phases.
    path: '/scans/:id',
    element: <ScanDetailPage />,
  },
])

export default function App() {
  return <RouterProvider router={router} />
}