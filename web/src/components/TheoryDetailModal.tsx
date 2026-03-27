import type { TheoryDetail } from '../types'

interface Props {
  theory: TheoryDetail
  onClose: () => void
  onAdd?: () => void
}

export function TheoryDetailModal({ theory, onClose, onAdd }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative card w-full max-w-2xl max-h-[85vh] overflow-y-auto">
        <div className="sticky top-0 bg-surface border-b border-border px-6 py-4 flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-text-primary">{theory.name}</h2>
            <div className="flex gap-1 mt-1">
              {theory.domains.map((d) => (
                <span key={d} className="badge-indigo">{d}</span>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {onAdd && (
              <button className="btn-primary text-sm" onClick={onAdd}>Add to ensemble</button>
            )}
            <button className="btn-secondary text-sm" onClick={onClose}>Close</button>
          </div>
        </div>

        <div className="p-6 space-y-6">
          <div>
            <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">Description</h3>
            <p className="text-sm text-text-primary leading-relaxed">{theory.description}</p>
          </div>

          {theory.reference && (
            <div>
              <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">Reference</h3>
              <p className="text-sm text-text-secondary italic">{theory.reference}</p>
            </div>
          )}

          {theory.parameters.length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">
                Parameters ({theory.parameters.length})
              </h3>
              <div className="space-y-2">
                {theory.parameters.map((p) => (
                  <div key={p.name} className="bg-bg rounded p-3 border border-border">
                    <div className="flex items-center gap-2 mb-1">
                      <code className="text-xs font-mono text-accent">{p.name}</code>
                      <span className="text-xs text-text-secondary font-mono">{p.type}</span>
                      {p.has_default && (
                        <span className="text-xs text-text-secondary">
                          default: <code className="text-accent/80">{String(p.default)}</code>
                        </span>
                      )}
                    </div>
                    {p.description && (
                      <p className="text-xs text-text-secondary">{p.description}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {(theory.reads.length > 0 || theory.writes.length > 0) && (
            <div>
              <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">
                Environment Keys
              </h3>
              <div className="grid grid-cols-2 gap-4">
                {theory.reads.length > 0 && (
                  <div>
                    <p className="text-xs text-text-secondary mb-1">Reads</p>
                    <div className="space-y-1">
                      {theory.reads.map((k) => (
                        <code key={k} className="block text-xs font-mono text-text-secondary bg-bg px-2 py-1 rounded">
                          {k}
                        </code>
                      ))}
                    </div>
                  </div>
                )}
                {theory.writes.length > 0 && (
                  <div>
                    <p className="text-xs text-text-secondary mb-1">Writes</p>
                    <div className="space-y-1">
                      {theory.writes.map((k) => (
                        <code key={k} className="block text-xs font-mono text-accent/70 bg-bg px-2 py-1 rounded">
                          {k}
                        </code>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
