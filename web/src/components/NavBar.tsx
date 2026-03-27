import { Link, useLocation } from 'react-router-dom'
import { useTheoryStore } from '../stores/theoryStore'
import { useEffect } from 'react'

export function NavBar() {
  const location = useLocation()
  const pendingCount = useTheoryStore((s) => s.pendingCount)
  const fetchPendingCount = useTheoryStore((s) => s.fetchPendingCount)

  useEffect(() => { fetchPendingCount() }, [])

  const link = (to: string, label: string, badge?: number) => {
    const active = location.pathname === to || location.pathname.startsWith(to + '/')
    return (
      <Link
        to={to}
        className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors
          ${active ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:text-text-primary hover:bg-surface'}`}
      >
        {label}
        {badge != null && badge > 0 && (
          <span className="badge-yellow text-xs">{badge}</span>
        )}
      </Link>
    )
  }

  return (
    <nav className="h-14 border-b border-border flex items-center px-6 gap-1 shrink-0">
      <Link to="/" className="text-text-primary font-semibold text-sm mr-6 tracking-wide">
        CRUCIBLE
      </Link>
      {link('/forge', 'Forge')}
      {link('/library', 'Library', pendingCount)}
      {link('/ensembles', 'Ensembles')}
      {link('/dashboard', 'Dashboard')}
    </nav>
  )
}
