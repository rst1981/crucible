import { useState, useRef, useEffect } from 'react'
import { forgeApi, simApi, streamForgeMessage } from '../../api'
import { useForgeStore } from '../../stores/forgeStore'

export function ForgePage() {
  const { session, messages, streaming, runs,
          setSession, addMessage, updateLastAssistantMessage,
          finalizeLastAssistantMessage, setStreaming, addRun, updateRun, reset } = useForgeStore()
  const [input, setInput] = useState('')
  const [intakeText, setIntakeText] = useState('')
  const [starting, setStarting] = useState(false)
  const [launching, setLaunching] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const cancelStreamRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Poll running sims
  useEffect(() => {
    const pending = runs.filter(r => r.status === 'pending' || r.status === 'running')
    if (!pending.length) return
    const interval = setInterval(async () => {
      for (const run of pending) {
        try {
          const updated = await simApi.get(run.sim_id)
          updateRun(updated)
        } catch { /* ignore */ }
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [runs])

  const handleStart = async () => {
    if (!intakeText.trim()) return
    setStarting(true)
    try {
      const { session_id } = await forgeApi.createSession(intakeText)
      const s = await forgeApi.getSession(session_id)
      setSession(s)
      addMessage({ role: 'user', content: intakeText })
      addMessage({ role: 'assistant', content: '', streaming: true })
      setStreaming(true)

      cancelStreamRef.current = streamForgeMessage(
        session_id,
        intakeText,
        (chunk) => updateLastAssistantMessage(chunk),
        async (state) => {
          finalizeLastAssistantMessage()
          setStreaming(false)
          const updated = await forgeApi.getSession(session_id)
          setSession(updated)
        },
        (err) => {
          finalizeLastAssistantMessage()
          setStreaming(false)
          addMessage({ role: 'assistant', content: `Error: ${err}` })
        }
      )
    } finally {
      setStarting(false)
    }
  }

  const handleSend = async () => {
    if (!input.trim() || !session || streaming) return
    const msg = input.trim()
    setInput('')
    addMessage({ role: 'user', content: msg })
    addMessage({ role: 'assistant', content: '', streaming: true })
    setStreaming(true)

    cancelStreamRef.current = streamForgeMessage(
      session.session_id,
      msg,
      (chunk) => updateLastAssistantMessage(chunk),
      async (state) => {
        finalizeLastAssistantMessage()
        setStreaming(false)
        const updated = await forgeApi.getSession(session.session_id)
        setSession(updated)
      },
      (err) => {
        finalizeLastAssistantMessage()
        setStreaming(false)
        addMessage({ role: 'assistant', content: `Error: ${err}` })
      }
    )
  }

  const handleLaunch = async () => {
    if (!session) return
    setLaunching(true)
    try {
      const result = await simApi.launch(session.session_id)
      for (const { sim_id, ensemble_type } of result.launched) {
        addRun({
          sim_id,
          session_id: session.session_id,
          ensemble_type: ensemble_type as 'recommended' | 'custom',
          theory_ids: [],
          status: 'pending',
          started_at: Date.now() / 1000,
          completed_at: null,
          results: null,
          error: null,
        })
      }
    } finally {
      setLaunching(false)
    }
  }

  const stateLabel: Record<string, string> = {
    intake: 'Starting',
    research: 'Researching',
    dynamic_interview: 'Interviewing',
    ensemble_review: 'Ready to launch',
    complete: 'Complete',
  }

  const canLaunch = session?.state === 'ensemble_review' || session?.state === 'complete'

  // ── Pre-session intake form ────────────────────────────────────────────────
  if (!session) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="w-full max-w-xl">
          <h1 className="text-xl font-semibold text-text-primary mb-2">Crucible Forge</h1>
          <p className="text-sm text-text-secondary mb-6 leading-relaxed">
            Describe a scenario in plain language. The scoping agent will research relevant theory,
            pull calibration data, and interview you to build a simulation specification.
          </p>
          <textarea
            className="input min-h-[120px] resize-none mb-3"
            placeholder="Describe your scenario... e.g. 'Model the competitive dynamics in the US generic pharmaceuticals market following proposed FDA biosimilar approval reforms.'"
            value={intakeText}
            onChange={(e) => setIntakeText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && e.metaKey) handleStart() }}
          />
          <button
            className="btn-primary w-full"
            onClick={handleStart}
            disabled={starting || !intakeText.trim()}
          >
            {starting ? 'Starting session...' : 'Begin scoping'}
          </button>
        </div>
      </div>
    )
  }

  // ── Active session ─────────────────────────────────────────────────────────
  return (
    <div className="flex h-full overflow-hidden">
      {/* Chat panel */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Session status bar */}
        <div className="border-b border-border px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xs text-text-secondary font-mono">{session.session_id.slice(0, 8)}</span>
            <span className="badge-indigo">{stateLabel[session.state] ?? session.state}</span>
            {session.research_context?.library_additions?.length > 0 && (
              <span className="badge-green">
                +{session.research_context.library_additions.length} theories discovered
              </span>
            )}
          </div>
          <button className="text-xs text-text-secondary hover:text-danger" onClick={reset}>
            New session
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-lg px-4 py-3 text-sm leading-relaxed
                ${msg.role === 'user'
                  ? 'bg-accent/20 text-text-primary'
                  : 'bg-surface border border-border text-text-primary'}`}
              >
                {msg.content || (msg.streaming ? <span className="text-text-secondary animate-pulse">●</span> : null)}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Simulation runs */}
        {runs.length > 0 && (
          <div className="border-t border-border px-4 py-3 space-y-2">
            {runs.map((run) => (
              <div key={run.sim_id} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-text-secondary">{run.sim_id.slice(0, 8)}</span>
                  <span className="badge-gray">{run.ensemble_type}</span>
                </div>
                <div className="flex items-center gap-2">
                  {run.status === 'complete' && run.results && (
                    <span className="text-text-secondary">{run.results.ticks} ticks</span>
                  )}
                  <span className={
                    run.status === 'complete' ? 'badge-green' :
                    run.status === 'error' ? 'badge-red' :
                    'badge-yellow'
                  }>{run.status}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="border-t border-border p-4 flex gap-3">
          <input
            className="input flex-1"
            placeholder="Reply to the agent..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) handleSend() }}
            disabled={streaming}
          />
          {canLaunch && (
            <button
              className="btn-success shrink-0"
              onClick={handleLaunch}
              disabled={launching}
            >
              {launching ? 'Launching...' : '▶ Launch sim'}
            </button>
          )}
          <button
            className="btn-primary shrink-0"
            onClick={handleSend}
            disabled={streaming || !input.trim()}
          >
            Send
          </button>
        </div>
      </div>

      {/* SimSpec side panel */}
      <div className="w-72 border-l border-border flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider">SimSpec</h3>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
          {!session.simspec ? (
            <p className="text-text-secondary">Building spec...</p>
          ) : (
            <>
              <div>
                <p className="text-text-secondary mb-1">Name</p>
                <p className="text-text-primary font-medium">{session.simspec.name || '—'}</p>
              </div>
              <div>
                <p className="text-text-secondary mb-1">Domain</p>
                <p className="text-text-primary">{session.simspec.domain || '—'}</p>
              </div>
              <div>
                <p className="text-text-secondary mb-1">Actors</p>
                <p className="text-text-primary">{(session.simspec.actors as unknown[])?.length ?? 0}</p>
              </div>
              <div>
                <p className="text-text-secondary mb-1">Theories</p>
                <p className="text-text-primary">{(session.simspec.theories as unknown[])?.length ?? 0}</p>
              </div>
              <div>
                <p className="text-text-secondary mb-1">Metrics</p>
                <p className="text-text-primary">{(session.simspec.metrics as unknown[])?.length ?? 0}</p>
              </div>
            </>
          )}

          {session.simspec && (session.simspec.theories as unknown[])?.length > 0 && (
            <div>
              <p className="text-text-secondary mb-1">Theory ensemble</p>
              <div className="space-y-1">
                {(session.simspec.theories as Array<{ theory_id: string; priority: number; parameters: Record<string, unknown> }>).map((t) => (
                  <code key={t.theory_id} className="block font-mono text-accent/80 bg-bg px-2 py-1 rounded">
                    {t.theory_id}
                  </code>
                ))}
              </div>
            </div>
          )}

          {session.research_context?.library_additions?.length > 0 && (
            <div>
              <p className="text-text-secondary mb-1">Auto-discovered</p>
              {session.research_context.library_additions.map((id: string) => (
                <span key={id} className="block badge-green mb-1">{id}</span>
              ))}
            </div>
          )}

          {(session.gaps?.filter(g => !g.filled) ?? []).length > 0 && (
            <div>
              <p className="text-text-secondary mb-1">Open gaps</p>
              {session.gaps.filter(g => !g.filled).map(g => (
                <div key={g.field_path} className="text-text-secondary/70 mb-1">
                  · {g.field_path}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
