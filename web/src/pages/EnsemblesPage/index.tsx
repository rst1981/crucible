import { useEffect, useState } from 'react'
import { useEnsembleStore } from '../../stores/ensembleStore'

export function EnsemblesPage() {
  const { ensembles, loading, fetchEnsembles, deleteEnsemble, forkEnsemble } = useEnsembleStore()
  const [forkingId, setForkingId] = useState<string | null>(null)
  const [forkName, setForkName] = useState('')

  useEffect(() => { fetchEnsembles() }, [])

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete ensemble "${name}"?`)) return
    await deleteEnsemble(id)
  }

  const handleFork = async (id: string) => {
    if (!forkName.trim()) return
    await forkEnsemble(id, forkName.trim())
    setForkingId(null)
    setForkName('')
  }

  const sourceLabel = (source: string) => {
    if (source === 'system') return <span className="badge-indigo">system</span>
    if (source === 'recommended') return <span className="badge-yellow">recommended</span>
    return <span className="badge-gray">user</span>
  }

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border px-6 py-4">
        <h1 className="text-base font-semibold text-text-primary">Saved Ensembles</h1>
        <p className="text-xs text-text-secondary mt-0.5">
          Named theory combinations — fork, load into intake, or compare runs
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="text-text-secondary text-sm">Loading...</div>
        ) : ensembles.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-text-secondary text-sm">No saved ensembles yet.</p>
            <p className="text-text-secondary text-xs mt-1">
              Ensembles are created from the Forge after scoping a scenario.
            </p>
          </div>
        ) : (
          <div className="space-y-3 max-w-2xl">
            {ensembles.map((e) => (
              <div key={e.ensemble_id} className="card p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-medium text-text-primary truncate">{e.name}</h3>
                      {sourceLabel(e.source)}
                    </div>
                    <div className="text-xs text-text-secondary mb-2">
                      {e.theory_count} {e.theory_count === 1 ? 'theory' : 'theories'}
                      {e.forked_from && <span className="ml-2 text-text-secondary/60">forked</span>}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {e.theory_ids.slice(0, 5).map((tid) => (
                        <code key={tid} className="text-xs font-mono text-accent/70 bg-bg px-1.5 py-0.5 rounded">
                          {tid}
                        </code>
                      ))}
                      {e.theory_ids.length > 5 && (
                        <span className="text-xs text-text-secondary">+{e.theory_ids.length - 5} more</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {forkingId === e.ensemble_id ? (
                      <div className="flex items-center gap-2">
                        <input
                          className="input w-36 text-xs py-1"
                          placeholder="Fork name..."
                          value={forkName}
                          onChange={(ev) => setForkName(ev.target.value)}
                          onKeyDown={(ev) => { if (ev.key === 'Enter') handleFork(e.ensemble_id) }}
                          autoFocus
                        />
                        <button className="btn-primary text-xs py-1 px-2" onClick={() => handleFork(e.ensemble_id)}>
                          Fork
                        </button>
                        <button className="btn-secondary text-xs py-1 px-2" onClick={() => setForkingId(null)}>
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          className="btn-secondary text-xs"
                          onClick={() => { setForkingId(e.ensemble_id); setForkName(e.name + ' (fork)') }}
                        >
                          Fork
                        </button>
                        <button
                          className="btn-danger text-xs"
                          onClick={() => handleDelete(e.ensemble_id, e.name)}
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </div>
                <div className="mt-2 text-xs text-text-secondary/60">
                  {new Date(e.created_at).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
