import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTheoryStore } from '../../stores/theoryStore'
import { TheoryCard } from '../../components/TheoryCard'
import { TheoryDetailModal } from '../../components/TheoryDetailModal'
import { theoryApi } from '../../api'
import type { TheoryDetail } from '../../types'

const DOMAINS = ['geopolitics', 'conflict', 'market', 'corporate', 'macro', 'social', 'technology', 'ecology']

export function LibraryPage() {
  const { catalog, loading, pendingCount, filters, fetchCatalog, fetchPendingCount, setFilters } = useTheoryStore()
  const [selectedDetail, setSelectedDetail] = useState<TheoryDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  useEffect(() => {
    fetchCatalog()
    fetchPendingCount()
  }, [])

  const handleDomainToggle = (domain: string) => {
    const next = filters.domain === domain ? '' : domain
    const newFilters = { ...filters, domain: next }
    setFilters(newFilters)
    fetchCatalog(newFilters)
  }

  const handleSearch = (q: string) => {
    const newFilters = { ...filters, q }
    setFilters(newFilters)
    fetchCatalog(newFilters)
  }

  const handleCardClick = async (theory_id: string) => {
    setLoadingDetail(true)
    try {
      const detail = await theoryApi.get(theory_id)
      setSelectedDetail(detail)
    } finally {
      setLoadingDetail(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-border px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-base font-semibold text-text-primary">Model Library</h1>
            <p className="text-xs text-text-secondary mt-0.5">{catalog.length} theories registered</p>
          </div>
          <Link
            to="/library/pending"
            className={`flex items-center gap-2 btn-secondary text-xs
              ${pendingCount > 0 ? 'border-warning/50 text-warning' : ''}`}
          >
            Pending review
            {pendingCount > 0 && <span className="badge-yellow">{pendingCount}</span>}
          </Link>
        </div>

        {/* Search */}
        <div className="flex gap-3 mb-3">
          <input
            className="input max-w-sm"
            placeholder="Search theories..."
            value={filters.q}
            onChange={(e) => handleSearch(e.target.value)}
          />
        </div>

        {/* Domain chips */}
        <div className="flex flex-wrap gap-2">
          {DOMAINS.map((d) => (
            <button
              key={d}
              onClick={() => handleDomainToggle(d)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors
                ${filters.domain === d
                  ? 'bg-accent text-white'
                  : 'bg-surface border border-border text-text-secondary hover:text-text-primary hover:border-accent/50'}`}
            >
              {d}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="text-text-secondary text-sm">Loading...</div>
        ) : catalog.length === 0 ? (
          <div className="text-text-secondary text-sm">No theories match your filters.</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {catalog.map((t) => (
              <TheoryCard
                key={t.theory_id}
                theory={t}
                onClick={() => handleCardClick(t.theory_id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Detail modal */}
      {selectedDetail && (
        <TheoryDetailModal
          theory={selectedDetail}
          onClose={() => setSelectedDetail(null)}
        />
      )}
    </div>
  )
}
