import { create } from 'zustand'
import { ensembleApi } from '../api'
import type { EnsembleSummary, Ensemble } from '../types'

interface EnsembleState {
  ensembles: EnsembleSummary[]
  loading: boolean
  selected: Ensemble | null
  fetchEnsembles: () => Promise<void>
  fetchDetail: (id: string) => Promise<void>
  createEnsemble: (name: string, theories: unknown[]) => Promise<Ensemble>
  deleteEnsemble: (id: string) => Promise<void>
  forkEnsemble: (id: string, name: string) => Promise<Ensemble>
  clearSelected: () => void
}

export const useEnsembleStore = create<EnsembleState>((set, get) => ({
  ensembles: [],
  loading: false,
  selected: null,

  fetchEnsembles: async () => {
    set({ loading: true })
    try {
      const data = await ensembleApi.list()
      set({ ensembles: data.ensembles, loading: false })
    } catch { set({ loading: false }) }
  },

  fetchDetail: async (id) => {
    const data = await ensembleApi.get(id)
    set({ selected: data })
  },

  createEnsemble: async (name, theories) => {
    const data = await ensembleApi.create({ name, theories })
    await get().fetchEnsembles()
    return data
  },

  deleteEnsemble: async (id) => {
    await ensembleApi.delete(id)
    set((s) => ({ ensembles: s.ensembles.filter((e) => e.ensemble_id !== id) }))
  },

  forkEnsemble: async (id, name) => {
    const data = await ensembleApi.fork(id, name)
    await get().fetchEnsembles()
    return data
  },

  clearSelected: () => set({ selected: null }),
}))
