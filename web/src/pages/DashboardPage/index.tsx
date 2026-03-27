import { useEffect, useState } from 'react'
import { simApi } from '../../api'

export function DashboardPage() {
  const [runs, setRuns] = useState<any[]>([])
  const [selected, setSelected] = useState<any | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const data = await simApi.list()
      setRuns(data.runs)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleSelect = async (sim_id: string) => {
    const data = await simApi.get(sim_id)
    setSelected(data)
  }

  const formatDuration = (started: number, completed: number | null) => {
    const end = completed ?? Date.now() / 1000
    const secs = Math.round(end - started)
    return secs < 60 ? `${secs}s` : `${Math.round(secs / 60)}m`
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Run list */}
      <div className="w-72 border-r border-border flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-medium text-text-primary">Simulation Runs</h2>
          <button className="text-xs text-text-secondary hover:text-text-primary" onClick={load}>Refresh</button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 text-xs text-text-secondary">Loading...</div>
          ) : runs.length === 0 ? (
            <div className="p-4 text-xs text-text-secondary">No runs yet. Launch a simulation from the Forge.</div>
          ) : (
            runs.map((run) => (
              <button
                key={run.sim_id}
                onClick={() => handleSelect(run.sim_id)}
                className={`w-full text-left px-4 py-3 border-b border-border transition-colors hover:bg-surface
                  ${selected?.sim_id === run.sim_id ? 'bg-surface' : ''}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <code className="text-xs font-mono text-text-secondary">{run.sim_id.slice(0, 8)}</code>
                  <span className={
                    run.status === 'complete' ? 'badge-green' :
                    run.status === 'error' ? 'badge-red' :
                    'badge-yellow'
                  }>{run.status}</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-text-secondary">
                  <span className="badge-gray">{run.ensemble_type}</span>
                  <span>{formatDuration(run.started_at, run.completed_at)}</span>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-text-secondary text-sm">
            Select a simulation run to view results
          </div>
        ) : (
          <div className="max-w-3xl space-y-6">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <code className="text-sm font-mono text-text-secondary">{selected.sim_id}</code>
                <span className={
                  selected.status === 'complete' ? 'badge-green' :
                  selected.status === 'error' ? 'badge-red' :
                  'badge-yellow'
                }>{selected.status}</span>
                <span className="badge-gray">{selected.ensemble_type}</span>
              </div>
              {selected.error && (
                <p className="text-sm text-danger mt-2">{selected.error}</p>
              )}
            </div>

            {selected.results && (
              <>
                {/* Summary */}
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: 'Ticks', value: selected.results.ticks },
                    { label: 'Metrics', value: Object.keys(selected.results.metric_series).length },
                    { label: 'Snapshots', value: selected.results.snapshot_count },
                  ].map(({ label, value }) => (
                    <div key={label} className="card p-4 text-center">
                      <div className="text-2xl font-semibold text-text-primary font-mono">{value}</div>
                      <div className="text-xs text-text-secondary mt-1">{label}</div>
                    </div>
                  ))}
                </div>

                {/* KPI panels */}
                {Object.entries(selected.results.metric_series).length > 0 && (
                  <div>
                    <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-3">
                      Outcome Metrics
                    </h3>
                    <div className="grid grid-cols-2 gap-3">
                      {Object.entries(selected.results.metric_series).map(([mid, series]: [string, any]) => {
                        const name = selected.results.metric_names?.[mid] ?? mid
                        const last = series[series.length - 1] as number
                        const first = series[0] as number
                        const delta = last - first
                        return (
                          <div key={mid} className="card p-4">
                            <p className="text-xs text-text-secondary mb-1 truncate">{name}</p>
                            <p className="text-xl font-semibold font-mono text-text-primary">
                              {last.toFixed(3)}
                            </p>
                            <p className={`text-xs font-mono mt-1 ${delta >= 0 ? 'text-success' : 'text-danger'}`}>
                              {delta >= 0 ? '+' : ''}{delta.toFixed(3)}
                            </p>
                            {/* Sparkline */}
                            <div className="flex items-end gap-0.5 mt-2 h-8">
                              {series.filter((_: any, i: number) => i % Math.ceil(series.length / 20) === 0)
                                .map((v: number, i: number) => (
                                <div
                                  key={i}
                                  className="flex-1 bg-accent/40 rounded-sm min-h-[2px]"
                                  style={{ height: `${Math.max(4, v * 100)}%` }}
                                />
                              ))}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Final env */}
                {Object.keys(selected.results.final_env).length > 0 && (
                  <div>
                    <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-3">
                      Final Environment State
                    </h3>
                    <div className="card divide-y divide-border">
                      {Object.entries(selected.results.final_env).sort().map(([k, v]: [string, any]) => (
                        <div key={k} className="flex items-center justify-between px-4 py-2 text-xs">
                          <code className="font-mono text-text-secondary">{k}</code>
                          <span className="font-mono text-text-primary">{(v as number).toFixed(4)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Theory IDs */}
                <div>
                  <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">
                    Theory Ensemble
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {selected.theory_ids.map((tid: string) => (
                      <code key={tid} className="text-xs font-mono text-accent/80 bg-surface border border-border px-2 py-1 rounded">
                        {tid}
                      </code>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
