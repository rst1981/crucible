import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { theoryApi } from '../../api'
import type { PendingTheory } from '../../types'
import { useTheoryStore } from '../../stores/theoryStore'

export function PendingPage() {
  const [theories, setTheories] = useState<PendingTheory[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<PendingTheory | null>(null)
  const [acting, setActing] = useState<string | null>(null)
  const fetchPendingCount = useTheoryStore((s) => s.fetchPendingCount)

  const load = async () => {
    setLoading(true)
    try {
      const data = await theoryApi.listPending()
      setTheories(data.pending)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleApprove = async (id: string) => {
    setActing(id)
    try {
      await theoryApi.approvePending(id)
      await load()
      fetchPendingCount()
      if (selected?.pending_id === id) setSelected(null)
    } finally { setActing(null) }
  }

  const handleReject = async (id: string) => {
    setActing(id)
    try {
      await theoryApi.rejectPending(id)
      await load()
      fetchPendingCount()
      if (selected?.pending_id === id) setSelected(null)
    } finally { setActing(null) }
  }

  const handleSelect = async (id: string) => {
    const detail = await theoryApi.getPending(id)
    setSelected(detail)
  }

  const statusBadge = (status: string, smoke: boolean) => {
    if (status === 'approved') return <span className="badge-green">approved</span>
    if (status === 'rejected') return <span className="badge-red">rejected</span>
    return smoke
      ? <span className="badge-green">smoke ✓</span>
      : <span className="badge-red">smoke ✗</span>
  }

  return (
    <div className="flex h-full">
      {/* List panel */}
      <div className="w-80 border-r border-border flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div>
            <Link to="/library" className="text-xs text-text-secondary hover:text-text-primary">← Library</Link>
            <h2 className="text-sm font-medium text-text-primary mt-1">Pending Review</h2>
          </div>
          <span className="badge-gray">{theories.filter(t => t.status === 'pending').length}</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 text-xs text-text-secondary">Loading...</div>
          ) : theories.length === 0 ? (
            <div className="p-4 text-xs text-text-secondary">No pending theories.</div>
          ) : (
            theories.map((t) => (
              <button
                key={t.pending_id}
                onClick={() => handleSelect(t.pending_id)}
                className={`w-full text-left px-4 py-3 border-b border-border transition-colors hover:bg-surface
                  ${selected?.pending_id === t.pending_id ? 'bg-surface' : ''}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-text-primary truncate">{t.display_name}</span>
                  {statusBadge(t.status, t.smoke_test.passed)}
                </div>
                <div className="text-xs text-text-secondary truncate">{t.citation}</div>
                <div className="flex gap-1 mt-1">
                  {t.domains.slice(0, 2).map(d => (
                    <span key={d} className="badge-gray">{d}</span>
                  ))}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 overflow-y-auto">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-text-secondary text-sm">
            Select a theory to review
          </div>
        ) : (
          <div className="p-6 space-y-6 max-w-3xl">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-base font-semibold text-text-primary">{selected.display_name}</h2>
                <p className="text-xs text-text-secondary mt-1">{selected.citation}</p>
                <div className="flex gap-1 mt-2">
                  {selected.domains.map(d => <span key={d} className="badge-indigo">{d}</span>)}
                  {statusBadge(selected.status, selected.smoke_test.passed)}
                </div>
              </div>
              {selected.status === 'pending' && (
                <div className="flex gap-2 shrink-0">
                  <button
                    className="btn-success"
                    disabled={acting === selected.pending_id}
                    onClick={() => handleApprove(selected.pending_id)}
                  >
                    {acting === selected.pending_id ? 'Working...' : 'Approve'}
                  </button>
                  <button
                    className="btn-danger"
                    disabled={acting === selected.pending_id}
                    onClick={() => handleReject(selected.pending_id)}
                  >
                    Reject
                  </button>
                </div>
              )}
            </div>

            {selected.abstract_snippet && (
              <div>
                <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">Abstract</h3>
                <p className="text-sm text-text-secondary leading-relaxed">{selected.abstract_snippet}</p>
              </div>
            )}

            <div>
              <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">
                Smoke Test — {selected.smoke_test.passed ? '✓ Passed' : '✗ Failed'}
              </h3>
              {selected.smoke_test.error && (
                <pre className="bg-bg border border-danger/30 rounded p-3 text-xs text-danger font-mono whitespace-pre-wrap">
                  {selected.smoke_test.error}
                </pre>
              )}
              {selected.smoke_test.passed && (
                <p className="text-xs text-success">Import, instantiation, and update() all passed.</p>
              )}
            </div>

            <div>
              <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">Generated Code</h3>
              <pre className="bg-bg border border-border rounded p-4 text-xs font-mono text-text-secondary
                             overflow-x-auto whitespace-pre leading-relaxed max-h-96 overflow-y-auto">
                {selected.generated_code}
              </pre>
            </div>

            <div className="flex items-center gap-3 text-xs text-text-secondary">
              <span>Source: {selected.source_type}</span>
              {selected.source_url && (
                <a href={selected.source_url} target="_blank" rel="noopener noreferrer"
                   className="text-accent hover:underline">
                  View paper →
                </a>
              )}
              <span>Queued: {new Date(selected.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
