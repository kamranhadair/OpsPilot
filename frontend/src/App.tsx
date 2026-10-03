import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'

import { AppShell } from './components/layout/AppShell'
import { AnomalyDrilldownPage } from './features/anomalies/AnomalyDrilldownPage'
import { AnomalyExplorerPage } from './features/anomalies/AnomalyExplorerPage'
import { OverviewPage } from './features/dashboard/OverviewPage'

function NotFoundPage() {
  return (
    <section aria-labelledby="not-found-heading">
      <h2 id="not-found-heading" className="text-lg font-semibold">
        Page not found
      </h2>
      <Link to="/" className="mt-2 inline-block text-sm text-sky-700 underline">
        Back to the operations overview
      </Link>
    </section>
  )
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="anomalies" element={<AnomalyExplorerPage />} />
        <Route path="anomalies/:evidenceId" element={<AnomalyDrilldownPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
