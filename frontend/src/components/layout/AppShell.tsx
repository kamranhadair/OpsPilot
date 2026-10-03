import { NavLink, Outlet } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/anomalies', label: 'Anomalies', end: false },
] as const

/** Sections that later specs attach real views to. */
const UPCOMING = ['Briefs', 'Actions', 'System'] as const

function linkClass({ isActive }: { isActive: boolean }): string {
  return isActive
    ? 'border-b-2 border-slate-900 pb-1 font-medium text-slate-900'
    : 'border-b-2 border-transparent pb-1 text-slate-600 hover:text-slate-900'
}

export function AppShell() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-end justify-between gap-4 px-6 pt-4">
          <div className="pb-3">
            <h1 className="text-xl font-semibold">OpsPilot</h1>
            <p className="text-sm text-slate-600">
              AI Support Operations Command Center
            </p>
          </div>
          <nav aria-label="Primary">
            <ul className="flex flex-wrap gap-5 text-sm">
              {LINKS.map((link) => (
                <li key={link.to}>
                  <NavLink to={link.to} end={link.end} className={linkClass}>
                    {link.label}
                  </NavLink>
                </li>
              ))}
              {UPCOMING.map((section) => (
                <li key={section} className="pb-1 text-slate-400">
                  <span aria-disabled="true">{section}</span>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-6">
        <Outlet />
      </main>
    </div>
  )
}
