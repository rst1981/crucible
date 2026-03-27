import type { TheorySummary } from '../types'

interface Props {
  theory: TheorySummary
  onClick: () => void
  selected?: boolean
  action?: { label: string; onClick: (e: React.MouseEvent) => void; variant?: 'primary' | 'success' }
}

const DOMAIN_COLORS: Record<string, string> = {
  geopolitics: 'badge-red',
  conflict:    'badge-red',
  market:      'badge-indigo',
  corporate:   'badge-indigo',
  macro:       'badge-yellow',
  social:      'badge-green',
  technology:  'badge-green',
  ecology:     'badge-green',
}

export function TheoryCard({ theory, onClick, selected, action }: Props) {
  return (
    <div
      onClick={onClick}
      className={`card p-4 cursor-pointer transition-all hover:border-accent/50
        ${selected ? 'border-accent bg-accent/5' : ''}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="text-sm font-medium text-text-primary leading-tight">{theory.name}</h3>
        <span className={`badge shrink-0 ${theory.source === 'discovered' ? 'badge-green' : 'badge-gray'}`}>
          {theory.source === 'discovered' ? 'discovered' : 'built-in'}
        </span>
      </div>
      <p className="text-xs text-text-secondary leading-relaxed line-clamp-2 mb-3">
        {theory.description}
      </p>
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap gap-1">
          {theory.domains.slice(0, 3).map((d) => (
            <span key={d} className={DOMAIN_COLORS[d.toLowerCase()] ?? 'badge-gray'}>
              {d}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-secondary font-mono">{theory.parameter_count}p</span>
          {action && (
            <button
              onClick={action.onClick}
              className={action.variant === 'success' ? 'btn-success text-xs py-1 px-2' : 'btn-primary text-xs py-1 px-2'}
            >
              {action.label}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
