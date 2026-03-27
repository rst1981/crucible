import { create } from 'zustand'
import { theoryApi } from '../api'
import type { TheorySummary, TheoryDetail } from '../types'

interface TheoryState {
  catalog: TheorySummary[]
  loading: boolean
  selected: TheoryDetail | null
  pendingCount: number
  filters: { domain: string; q: string }
  fetchCatalog: (filters?: { domain?: string; q?: string }) => Promise<void>
  fetchDetail: (theory_id: string) => Promise<void>
  clearSelected: () => void
  fetchPendingCount: () => Promise<void>
  setFilters: (filters: { domain?: string; q?: string }) => void
}

export const useTheoryStore = create<TheoryState>((set, get) => ({
  catalog: [],
  loading: false,
  selected: null,
  pendingCount: 0,
  filters: { domain: '', q: '' },

  fetchCatalog: async (filters) => {
    set({ loading: true })
    try {
      const f = filters ?? get().filters
      const data = await theoryApi.list({ domain: f.domain || undefined, q: f.q || undefined })
      set({ catalog: data.theories, loading: false })
    } catch { set({ loading: false }) }
  },

  fetchDetail: async (theory_id) => {
    const data = await theoryApi.get(theory_id)
    set({ selected: data })
  },

  clearSelected: () => set({ selected: null }),

  fetchPendingCount: async () => {
    try {
      const data = await theoryApi.listPending('pending')
      set({ pendingCount: data.count })
    } catch { /* ignore */ }
  },

  setFilters: (filters) => {
    set((s) => ({ filters: { ...s.filters, ...filters } }))
  },
}))
