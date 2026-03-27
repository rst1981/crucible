import { create } from 'zustand'
import type { ForgeSession, SimulationRun } from '../types'

interface Message {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

interface ForgeState {
  session: ForgeSession | null
  messages: Message[]
  runs: SimulationRun[]
  streaming: boolean
  setSession: (session: ForgeSession) => void
  addMessage: (msg: Message) => void
  updateLastAssistantMessage: (chunk: string) => void
  finalizeLastAssistantMessage: () => void
  setStreaming: (v: boolean) => void
  addRun: (run: SimulationRun) => void
  updateRun: (run: SimulationRun) => void
  reset: () => void
}

export const useForgeStore = create<ForgeState>((set) => ({
  session: null,
  messages: [],
  runs: [],
  streaming: false,

  setSession: (session) => set({ session }),

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),

  updateLastAssistantMessage: (chunk) =>
    set((s) => {
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + chunk, streaming: true }
      }
      return { messages: msgs }
    }),

  finalizeLastAssistantMessage: () =>
    set((s) => {
      const msgs = [...s.messages]
      const last = msgs[msgs.length - 1]
      if (last?.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, streaming: false }
      }
      return { messages: msgs }
    }),

  setStreaming: (streaming) => set({ streaming }),

  addRun: (run) => set((s) => ({ runs: [...s.runs, run] })),

  updateRun: (run) =>
    set((s) => ({
      runs: s.runs.map((r) => (r.sim_id === run.sim_id ? run : r)),
    })),

  reset: () => set({ session: null, messages: [], runs: [], streaming: false }),
}))
