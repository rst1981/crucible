const BASE = ''  // proxied via Vite dev server

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// Forge
export const forgeApi = {
  createSession: (intake_text: string) =>
    req<{ session_id: string; state: string }>('POST', '/forge/intake', { intake_text }),
  getSession: (id: string) => req<any>('GET', `/forge/intake/${id}`),
  deleteSession: (id: string) => req<void>('DELETE', `/forge/intake/${id}`),
  getTheories: (id: string) => req<any>('GET', `/forge/intake/${id}/theories`),
  acceptRecommended: (id: string) => req<any>('PUT', `/forge/intake/${id}/theories/accept`),
  setCustomEnsemble: (id: string, theories: unknown[]) =>
    req<any>('PUT', `/forge/intake/${id}/theories/custom`, { theories }),
  generateAssessment: (id: string) => req<any>('POST', `/forge/intake/${id}/assessment`),
}

// Simulations
export const simApi = {
  launch: (session_id: string, run_mode: 'recommended' | 'custom' | 'both' = 'recommended') =>
    req<{ launched: { sim_id: string; ensemble_type: string }[] }>('POST', '/simulations', { session_id, run_mode }),
  get: (sim_id: string) => req<any>('GET', `/simulations/${sim_id}`),
  list: (session_id?: string) =>
    req<any>('GET', `/simulations${session_id ? `?session_id=${session_id}` : ''}`),
  compare: (a: string, b: string) => req<any>('GET', `/simulations/compare/${a}/${b}`),
}

// Theory catalog
export const theoryApi = {
  list: (params?: { domain?: string; q?: string; source?: string }) => {
    const qs = new URLSearchParams()
    if (params?.domain) qs.set('domain', params.domain)
    if (params?.q) qs.set('q', params.q)
    if (params?.source) qs.set('source', params.source)
    const query = qs.toString()
    return req<any>('GET', `/api/theories${query ? `?${query}` : ''}`)
  },
  get: (theory_id: string) => req<any>('GET', `/api/theories/${theory_id}`),
  recommend: (body: { domain: string; description?: string; max_results?: number; use_claude?: boolean }) =>
    req<any>('POST', '/api/theories/recommend', body),
  listPending: (status?: string) =>
    req<any>('GET', `/forge/theories/pending${status ? `?status=${status}` : ''}`),
  getPending: (id: string) => req<any>('GET', `/forge/theories/pending/${id}`),
  approvePending: (id: string) => req<any>('POST', `/forge/theories/pending/${id}/approve`),
  rejectPending: (id: string) => req<any>('POST', `/forge/theories/pending/${id}/reject`),
}

// Ensembles
export const ensembleApi = {
  list: (source?: string) =>
    req<any>('GET', `/api/ensembles${source ? `?source=${source}` : ''}`),
  create: (body: { name: string; theories: unknown[]; source?: string }) =>
    req<any>('POST', '/api/ensembles', body),
  get: (id: string) => req<any>('GET', `/api/ensembles/${id}`),
  delete: (id: string) => req<void>('DELETE', `/api/ensembles/${id}`),
  fork: (id: string, name: string) =>
    req<any>('POST', `/api/ensembles/${id}/fork`, { name }),
}

// SSE helper for streaming forge messages
export function streamForgeMessage(
  session_id: string,
  message: string,
  onChunk: (text: string) => void,
  onDone: (state: string, simspec: unknown, gaps: unknown[]) => void,
  onError: (detail: string) => void,
): () => void {
  const ctrl = new AbortController()
  fetch(`/forge/intake/${session_id}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal: ctrl.signal,
  }).then(async (res) => {
    if (!res.ok) { onError(`HTTP ${res.status}`); return }
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const payload = JSON.parse(line.slice(6))
          if (payload.type === 'chunk') onChunk(payload.text)
          else if (payload.type === 'done') onDone(payload.state, payload.simspec, payload.gaps ?? [])
          else if (payload.type === 'error') onError(payload.detail)
        } catch { /* skip malformed */ }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') onError(String(err))
  })
  return () => ctrl.abort()
}
