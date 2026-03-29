import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { forgeApi, simApi, streamForgeMessage, streamGapResearch, theoryApi } from '../../api'
import { useForgeStore } from '../../stores/forgeStore'

type RunMode = 'recommended' | 'discovered' | 'merged' | 'custom' | 'both'
type Theory = { theory_id: string; display_name: string; score: number; rationale: string; application_note?: string; source?: string; domains?: string[] }

export function ForgePage() {
  const { session, messages, streaming, runs,
          setSession, addMessage, updateLastAssistantMessage,
          finalizeLastAssistantMessage, setStreaming, addRun, updateRun, reset } = useForgeStore()
  const [input, setInput] = useState('')
  const [intakeText, setIntakeText] = useState('')
  const [starting, setStarting] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [launching, setLaunching] = useState(false)
  const [generatingAssessment, setGeneratingAssessment] = useState(false)
  const [assessmentDone, setAssessmentDone] = useState(false)
  const [runMode, setRunMode] = useState<RunMode>('recommended')
  const [customTheories, setCustomTheories] = useState<Theory[]>([])
  const [buildingCustom, setBuildingCustom] = useState(false)
  const [libraryTheories, setLibraryTheories] = useState<Theory[]>([])
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [gapResearching, setGapResearching] = useState(false)
  const [gapResearchLog, setGapResearchLog] = useState<string>('')
  const [activeTab, setActiveTab] = useState<'interview' | 'ensemble'>('interview')
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

  // When entering ensemble_review, load library and switch to ensemble tab
  useEffect(() => {
    if (session?.state === 'ensemble_review' || session?.state === 'complete') {
      theoryApi.list().then(r => setLibraryTheories(r.theories ?? [])).catch(() => {})
      setActiveTab('ensemble')
    }
  }, [session?.state])

  // Initialise custom theories from recommended when entering custom mode
  useEffect(() => {
    if (buildingCustom && session?.recommended_theories && customTheories.length === 0) {
      setCustomTheories(session.recommended_theories.map((t: Theory) => ({ ...t })))
    }
  }, [buildingCustom])

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
        async (_state) => {
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
      async (_state) => {
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

  const handleGenerateAssessment = async () => {
    if (!session) return
    setGeneratingAssessment(true)
    try {
      await forgeApi.generateAssessment(session.session_id)
      setAssessmentDone(true)
      const updated = await forgeApi.getSession(session.session_id)
      setSession(updated)
    } catch (e) {
      console.error('Assessment generation failed', e)
    } finally {
      setGeneratingAssessment(false)
    }
  }

  const handleSaveCustom = async () => {
    if (!session) return
    await forgeApi.setCustomEnsemble(session.session_id, customTheories.map((t, i) => ({
      theory_id: t.theory_id, priority: i, parameters: {}
    })))
    const updated = await forgeApi.getSession(session.session_id)
    setSession(updated)
  }

  const handleLaunch = async () => {
    if (!session) return
    setLaunching(true)
    // discovered/merged modes both pre-populate custom_theories and launch as 'custom'
    const apiMode: 'recommended' | 'custom' | 'both' =
      (runMode === 'discovered' || runMode === 'merged') ? 'custom' : runMode as 'recommended' | 'custom' | 'both'
    try {
      const result = await simApi.launch(session.session_id, apiMode)
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

  const inEnsembleReview = session?.state === 'ensemble_review' || session?.state === 'complete'
  const hasEnsemble = inEnsembleReview || (session?.recommended_theories?.length ?? 0) > 0
  const hasCustom = session?.custom_theories != null && session.custom_theories.length > 0

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const res = await fetch('/forge/generate-scenario', { method: 'POST' })
      const data = await res.json()
      if (data.scenario) setIntakeText(data.scenario)
    } catch (e) {
      console.error('Generate failed', e)
    } finally {
      setGenerating(false)
    }
  }

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

          {/* Freeform input */}
          <textarea
            className="input min-h-[120px] resize-none mb-2"
            placeholder="Describe your scenario..."
            value={intakeText}
            onChange={(e) => setIntakeText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && e.metaKey) handleStart() }}
          />
          <div className="flex justify-end mb-3">
            <button
              className="text-xs text-text-secondary hover:text-text-primary transition-colors"
              onClick={handleGenerate}
              disabled={generating}
            >
              {generating ? 'Generating…' : intakeText ? '↺ Regenerate scenario' : '✦ Generate scenario'}
            </button>
          </div>
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

  // ── Tab bar (shown once session exists and ensemble has been reached) ────────
  const TabBar = () => {
    if (!session) return null
    const ensembleReady = hasEnsemble
    return (
      <div className="border-b border-border flex items-center px-4 gap-1 shrink-0">
        <button
          onClick={() => setActiveTab('interview')}
          className={`px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
            activeTab === 'interview'
              ? 'border-accent text-accent'
              : 'border-transparent text-text-secondary hover:text-text-primary'
          }`}
        >
          Interview
        </button>
        <button
          onClick={() => ensembleReady && setActiveTab('ensemble')}
          disabled={!ensembleReady}
          className={`px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
            activeTab === 'ensemble'
              ? 'border-accent text-accent'
              : ensembleReady
                ? 'border-transparent text-text-secondary hover:text-text-primary'
                : 'border-transparent text-text-secondary/30 cursor-not-allowed'
          }`}
        >
          Ensemble
          {(session.recommended_theories?.length ?? 0) > 0 && (
            <span className="ml-1.5 text-text-tertiary">
              {session.recommended_theories.length}
            </span>
          )}
          {!ensembleReady && (
            <span className="ml-1.5 text-text-secondary/30">·</span>
          )}
        </button>
      </div>
    )
  }

  // ── Ensemble Review + Go Page ──────────────────────────────────────────────
  if (inEnsembleReview && activeTab === 'ensemble') {
    const recs: Theory[] = session.recommended_theories ?? []
    const discovered: Theory[] = session.discovered_theories ?? []
    const hasTwoTiers = discovered.length > 0

    // Merged = recs + discovered, deduped by theory_id
    const merged: Theory[] = [
      ...recs,
      ...discovered.filter(d => !recs.find(r => r.theory_id === d.theory_id))
    ]

    const handleQuickSelect = async (theories: Theory[], mode: RunMode) => {
      if (!session) return
      await forgeApi.setCustomEnsemble(session.session_id, theories.map((t, i) => ({
        theory_id: t.theory_id, priority: i, parameters: {}
      })))
      const updated = await forgeApi.getSession(session.session_id)
      setSession(updated)
      setRunMode(mode === 'recommended' ? 'recommended' : 'custom')
    }

    const handleGapResearch = () => {
      if (!session || gapResearching) return
      setGapResearching(true)
      setGapResearchLog('')
      streamGapResearch(
        session.session_id,
        (chunk) => setGapResearchLog(prev => prev + chunk),
        async (updatedSession) => {
          setGapResearching(false)
          const refreshed = await forgeApi.getSession(session.session_id)
          setSession(refreshed)
        },
        (err) => {
          setGapResearching(false)
          setGapResearchLog(prev => prev + `\nError: ${err}`)
        },
      )
    }

    const GapResearchPanel = () => {
      const resolvable = session?.data_gaps ?? []
      const proprietary = session?.proprietary_gaps ?? []
      if (!resolvable.length && !proprietary.length) return null

      const [open, setOpen] = useState(true)
      const closed = session?.closed_gaps ?? []
      const remaining = session?.remaining_gaps ?? []
      const resolvedCount = closed.length
      const totalResolvable = resolvable.length

      return (
        <div className="border border-border rounded-lg bg-surface">
          <button
            className="w-full flex items-center justify-between px-4 py-3 text-left"
            onClick={() => setOpen(o => !o)}
          >
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-text-primary">Data Gaps</span>
              <span className="badge-gray">{resolvable.length + proprietary.length}</span>
              {session?.gap_research_complete && (
                <span className={resolvedCount === totalResolvable ? 'badge-green' : 'badge-yellow'}>
                  {resolvedCount}/{totalResolvable} resolved
                </span>
              )}
            </div>
            <span className="text-text-secondary text-xs">{open ? '▲' : '▼'}</span>
          </button>

          {open && (
            <div className="px-4 pb-4 space-y-4 border-t border-border pt-3">

              {/* Proprietary gaps */}
              {proprietary.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-text-secondary uppercase tracking-wide">Proprietary / Unavailable</p>
                  <ul className="space-y-1.5">
                    {proprietary.map((gap, i) => (
                      <li key={i} className="text-xs text-text-secondary flex items-start gap-1.5">
                        <span className="text-text-secondary/40 mt-0.5">⊘</span>
                        <span>{gap}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="text-xs text-text-secondary/50 italic">
                    These require firm-level or confidential data. A source upload feature is planned.
                  </p>
                </div>
              )}

              {/* Resolvable gaps */}
              {resolvable.length > 0 && (
                <div className="space-y-2">
                  {proprietary.length > 0 && (
                    <p className="text-xs font-medium text-text-secondary uppercase tracking-wide">Resolvable via Research</p>
                  )}
                  <ul className="space-y-1">
                    {resolvable.map((gap, i) => {
                      const isClosed = closed.includes(gap)
                      const isRemaining = remaining.includes(gap)
                      return (
                        <li key={i} className="text-xs text-text-secondary flex items-start gap-1.5">
                          <span className={isClosed ? 'text-green-400' : isRemaining ? 'text-text-secondary/50' : ''}>
                            {isClosed ? '✓' : isRemaining ? '○' : '·'}
                          </span>
                          <span className={isClosed ? 'line-through text-text-secondary/50' : ''}>{gap}</span>
                        </li>
                      )
                    })}
                  </ul>

                  {!session?.gap_research_complete && (
                    <p className="text-xs text-text-secondary/60">
                      Launch a targeted research pass to fill these from FRED, OpenAlex, and news sources.
                    </p>
                  )}

                  <button
                    className="btn-primary text-xs py-1 px-3"
                    onClick={handleGapResearch}
                    disabled={gapResearching}
                  >
                    {gapResearching ? 'Researching…' : session?.gap_research_complete ? 'Re-run research' : 'Research gaps'}
                  </button>
                </div>
              )}

              {gapResearchLog && (
                <pre className="text-xs text-text-secondary/70 bg-bg rounded p-2 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-40 overflow-y-auto">
                  {gapResearchLog}
                </pre>
              )}

              {session?.gap_research_complete && (
                <p className={`text-xs font-medium ${resolvedCount === totalResolvable ? 'text-green-400' : 'text-yellow-400'}`}>
                  {resolvedCount}/{totalResolvable} resolvable gaps closed
                </p>
              )}
            </div>
          )}
        </div>
      )
    }

    return (
      <div className="flex flex-col h-full overflow-hidden">
        <TabBar />
        <div className="flex flex-1 overflow-hidden">
        {/* Left: theory cards */}
        <div className="flex-1 flex flex-col min-w-0 overflow-y-auto p-6 space-y-6">

          <GapResearchPanel />

          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-text-primary">Theory Ensemble</h2>
              <p className="text-xs text-text-secondary mt-0.5">
                {recs.length} library · {discovered.length} discovered from research
              </p>
            </div>
            <button className="text-xs text-text-secondary hover:text-danger" onClick={reset}>
              New session
            </button>
          </div>

          {/* Two-tier view */}
          {hasTwoTiers ? (
            <div className="grid grid-cols-2 gap-4">
              {/* Tier 1 */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Tier 1 — Library</p>
                  <span className="badge-gray">{recs.length}</span>
                </div>
                <div className="space-y-2">
                  {recs.map((t, i) => (
                    <TheoryCard key={t.theory_id} theory={t} rank={i + 1} compact />
                  ))}
                </div>
              </div>
              {/* Tier 2 */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Tier 2 — Discovered</p>
                  <span className="badge-green">{discovered.length} new</span>
                </div>
                <div className="space-y-2">
                  {discovered.map((t, i) => (
                    <TheoryCard key={t.theory_id} theory={t} rank={i + 1} compact />
                  ))}
                </div>
              </div>
            </div>
          ) : (
            /* Single-tier fallback */
            <div>
              <p className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-3">Recommended</p>
              <div className="space-y-3">
                {recs.map((t, i) => (
                  <TheoryCard key={t.theory_id} theory={t} rank={i + 1} />
                ))}
              </div>
            </div>
          )}

          {/* Quick-select buttons (two-tier only) */}
          {hasTwoTiers && (
            <div className="border border-border rounded-lg p-4 space-y-3">
              <p className="text-sm font-medium text-text-primary">Select ensemble</p>
              <div className="grid grid-cols-3 gap-2">
                <button
                  className={`text-xs rounded border py-2 px-3 text-left transition-colors ${
                    runMode === 'recommended'
                      ? 'border-accent bg-accent/10 text-accent'
                      : 'border-border text-text-secondary hover:border-accent/50'
                  }`}
                  onClick={() => { setRunMode('recommended'); }}
                >
                  <span className="font-medium block text-text-primary">Accept library</span>
                  <span className="text-text-secondary/70">{recs.length} theories</span>
                </button>
                <button
                  className={`text-xs rounded border py-2 px-3 text-left transition-colors ${
                    runMode === 'discovered'
                      ? 'border-green-500 bg-green-500/10 text-green-400'
                      : 'border-border text-text-secondary hover:border-green-500/50'
                  }`}
                  onClick={() => handleQuickSelect(discovered, 'discovered')}
                >
                  <span className="font-medium block text-text-primary">Use discovered</span>
                  <span className="text-text-secondary/70">{discovered.length} theories</span>
                </button>
                <button
                  className={`text-xs rounded border py-2 px-3 text-left transition-colors ${
                    runMode === 'merged'
                      ? 'border-accent bg-accent/10 text-accent'
                      : 'border-border text-text-secondary hover:border-accent/50'
                  }`}
                  onClick={() => handleQuickSelect(merged, 'merged')}
                >
                  <span className="font-medium block text-text-primary">Merge both</span>
                  <span className="text-text-secondary/70">{merged.length} theories</span>
                </button>
              </div>
            </div>
          )}

          {/* Custom ensemble builder */}
          <div className="border border-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm font-medium text-text-primary">Custom Ensemble</p>
                <p className="text-xs text-text-secondary">
                  {hasCustom
                    ? `${session.custom_theories!.length} theories configured`
                    : 'Build from scratch or start from a quick-select above'}
                </p>
              </div>
              <button
                className="btn-primary text-xs py-1 px-3"
                onClick={() => setBuildingCustom(!buildingCustom)}
              >
                {buildingCustom ? 'Close' : hasCustom ? 'Edit' : 'Build custom'}
              </button>
            </div>

            {buildingCustom && (
              <div className="space-y-3 mt-3 border-t border-border pt-3">
                <p className="text-xs text-text-secondary">Click × to remove · use library to add</p>
                <div className="space-y-2">
                  {customTheories.map((t, i) => (
                    <div key={t.theory_id} className="flex items-center gap-2 bg-bg rounded px-3 py-2 text-xs">
                      <span className="text-text-secondary w-5 shrink-0">{i + 1}</span>
                      <span className="flex-1 font-medium text-text-primary">{t.display_name}</span>
                      <span className="text-text-secondary/60 badge-gray">{t.theory_id}</span>
                      <button
                        className="text-text-secondary hover:text-danger ml-2"
                        onClick={() => setCustomTheories(prev => prev.filter((_, j) => j !== i))}
                      >×</button>
                    </div>
                  ))}
                </div>

                <button
                  className="text-xs text-accent hover:underline"
                  onClick={() => setLibraryOpen(!libraryOpen)}
                >
                  {libraryOpen ? '− Hide library' : '+ Add from library'}
                </button>

                {libraryOpen && (
                  <div className="grid grid-cols-2 gap-2 mt-2 max-h-48 overflow-y-auto">
                    {libraryTheories
                      .filter(lt => !customTheories.find(ct => ct.theory_id === lt.theory_id))
                      .map(lt => (
                        <button
                          key={lt.theory_id}
                          className="text-left text-xs bg-surface border border-border rounded px-2 py-1.5 hover:border-accent"
                          onClick={() => setCustomTheories(prev => [...prev, lt as Theory])}
                        >
                          <span className="font-medium text-text-primary block">{lt.theory_id.replace(/_/g, ' ')}</span>
                          <span className="text-text-secondary">{(lt.domains ?? []).join(', ')}</span>
                        </button>
                      ))}
                  </div>
                )}

                <button className="btn-primary text-xs w-full" onClick={handleSaveCustom}>
                  Save custom ensemble
                </button>
              </div>
            )}
          </div>

          {/* Assessment generation */}
          <div className="border border-border rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-text-primary">Assessment Document</p>
                <p className="text-xs text-text-secondary">
                  {assessmentDone || session.assessment_path
                    ? '✓ Generated — MD + PDF ready'
                    : 'Generate scenario assessment (MD + PDF)'}
                </p>
              </div>
              <button
                className="btn-primary text-xs py-1 px-3"
                onClick={handleGenerateAssessment}
                disabled={generatingAssessment}
              >
                {generatingAssessment ? 'Generating…' : assessmentDone || session.assessment_path ? 'Regenerate' : 'Generate'}
              </button>
            </div>
          </div>
        </div>

        {/* Right: Go panel */}
        <div className="w-80 border-l border-border flex flex-col shrink-0">
          <div className="px-4 py-3 border-b border-border">
            <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wider">Launch</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">

            {/* SimSpec summary */}
            <div className="space-y-2 text-xs">
              <p className="text-text-secondary font-medium">{session.simspec?.name || '—'}</p>
              <div className="space-y-1 text-text-secondary">
                <p>Domain: <span className="text-text-primary">{session.simspec?.domain || '—'}</span></p>
                <div>
                  <p className="mb-1">Actors: <span className="text-text-primary">{session.simspec?.actors?.length ?? 0}</span></p>
                  {(session.simspec?.actors?.length ?? 0) > 0 && (
                    <ul className="space-y-1 mt-1">
                      {session.simspec!.actors.map(a => {
                        const role = a.metadata?.role || a.description || ''
                        const shortRole = role.split(';')[0].split('.')[0].trim().slice(0, 55)
                        return (
                          <li key={a.actor_id} className="text-text-secondary leading-snug">
                            <span className="text-text-primary">{a.name}</span>
                            {shortRole && <span> — {shortRole}</span>}
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
                <p>Horizon: <span className="text-text-primary">{(session.simspec?.timeframe as any)?.total_ticks ?? 0} {(session.simspec?.timeframe as any)?.tick_unit ?? 'months'}</span></p>
              </div>
            </div>

            <div className="border-t border-border pt-3">
              <p className="text-xs font-medium text-text-secondary mb-2">Run mode</p>
              <div className="space-y-2">
                {(hasTwoTiers
                  ? (['recommended', 'custom', 'both'] as RunMode[])
                  : (['recommended', 'custom', 'both'] as RunMode[])
                ).map(mode => {
                  const disabled = (mode === 'custom') && !hasCustom
                  const activeTheories = {
                    recommended: recs,
                    discovered: discovered,
                    merged: merged,
                    custom: session.custom_theories ?? [],
                    both: recs,
                  }[mode] ?? []
                  const label = {
                    recommended: `Library (${recs.length} theories)`,
                    discovered: `Discovered (${discovered.length} theories)`,
                    merged: `Merged (${merged.length} theories)`,
                    custom: hasCustom
                      ? `Custom (${session.custom_theories?.length ?? 0} theories)`
                      : 'Custom — not yet built',
                    both: 'Both (parallel comparison)',
                  }[mode]
                  return (
                    <label key={mode} className={`flex items-start gap-2 text-xs cursor-pointer ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}>
                      <input
                        type="radio"
                        name="run_mode"
                        value={mode}
                        checked={runMode === mode}
                        disabled={disabled}
                        onChange={() => setRunMode(mode)}
                        className="mt-0.5"
                      />
                      <span className="text-text-primary">{label}</span>
                    </label>
                  )
                })}
              </div>
            </div>

            {/* Ensemble summaries */}
            <div className="border-t border-border pt-3 space-y-3">
              {runMode === 'recommended' && <EnsembleSummary label="Library" theories={recs} active />}
              {runMode === 'discovered' && <EnsembleSummary label="Discovered" theories={discovered} active />}
              {runMode === 'merged' && <EnsembleSummary label="Merged" theories={merged} active />}
              {runMode === 'custom' && hasCustom && <EnsembleSummary label="Custom" theories={session.custom_theories ?? []} active />}
              {runMode === 'both' && (
                <>
                  <EnsembleSummary label="Library" theories={recs} active />
                  {hasCustom && <EnsembleSummary label="Custom" theories={session.custom_theories ?? []} active />}
                </>
              )}
            </div>

            {/* Simulation runs status */}
            {runs.length > 0 && (
              <div className="border-t border-border pt-3 space-y-2">
                <p className="text-xs font-medium text-text-secondary">Runs</p>
                {runs.map(run => (
                  <div key={run.sim_id} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-text-secondary">{run.sim_id.slice(0, 8)}</span>
                      <span className="badge-gray">{run.ensemble_type}</span>
                    </div>
                    <span className={
                      run.status === 'complete' ? 'badge-green' :
                      run.status === 'error' ? 'badge-red' : 'badge-yellow'
                    }>{run.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="p-4 border-t border-border">
            <button
              className="btn-success w-full"
              onClick={handleLaunch}
              disabled={launching || (runMode === 'custom' && !hasCustom)}
            >
              {launching ? 'Launching…' : '▶ Go'}
            </button>
          </div>
        </div>
        </div>
      </div>
    )
  }

  // ── Active interview session ───────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TabBar />
      <div className="flex flex-1 overflow-hidden">
      {/* Chat panel */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Status bar */}
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
                {msg.streaming && !msg.content
                  ? <span className="text-text-secondary animate-pulse">●</span>
                  : msg.role === 'assistant'
                    ? <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p:      ({children}) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
                          ul:     ({children}) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
                          ol:     ({children}) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
                          li:     ({children}) => <li className="leading-relaxed">{children}</li>,
                          strong: ({children}) => <strong className="font-semibold text-text-primary">{children}</strong>,
                          em:     ({children}) => <em className="italic text-text-secondary">{children}</em>,
                          h1:     ({children}) => <h1 className="text-base font-semibold text-text-primary mt-3 mb-1">{children}</h1>,
                          h2:     ({children}) => <h2 className="text-sm font-semibold text-text-primary mt-3 mb-1">{children}</h2>,
                          h3:     ({children}) => <h3 className="text-sm font-medium text-text-primary mt-2 mb-1">{children}</h3>,
                          code:   ({children, className}) => className
                            ? <code className="block bg-bg border border-border rounded p-3 text-xs font-mono text-text-secondary my-2 overflow-x-auto whitespace-pre">{children}</code>
                            : <code className="bg-bg px-1.5 py-0.5 rounded text-xs font-mono text-accent/80">{children}</code>,
                          blockquote: ({children}) => <blockquote className="border-l-2 border-accent/40 pl-3 text-text-secondary italic my-2">{children}</blockquote>,
                          hr:     () => <hr className="border-border my-3" />,
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    : msg.content
                }
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

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
            </>
          )}

          {(session.gaps?.filter((g: any) => !g.filled) ?? []).length > 0 && (
            <div>
              <p className="text-text-secondary mb-1">Open gaps</p>
              {session.gaps.filter((g: any) => !g.filled).map((g: any) => (
                <div key={g.field_path} className="text-text-secondary/70 mb-1">
                  · {g.field_path}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      </div>
    </div>
  )
}

// ── Theory card component ─────────────────────────────────────────────────────

function TheoryCard({ theory, rank, compact }: { theory: Theory; rank: number; compact?: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const isNew = theory.source === 'discovered'
  return (
    <div className={`border border-border rounded-lg bg-surface ${compact ? 'p-3' : 'p-4'}`}>
      <div className="flex items-start gap-2">
        <span className={`font-bold text-text-secondary/40 shrink-0 leading-none mt-0.5 ${compact ? 'text-sm w-4' : 'text-lg w-6'}`}>{rank}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className={`font-medium text-text-primary ${compact ? 'text-xs' : 'text-sm'}`}>{theory.display_name}</span>
            {isNew && <span className="badge-green text-xs">New</span>}
            <span className="ml-auto text-xs text-text-secondary font-mono">{theory.score.toFixed(2)}</span>
          </div>
          <p className="text-xs text-text-secondary leading-relaxed line-clamp-3">
            {theory.application_note || theory.rationale}
          </p>
          {!compact && theory.rationale && theory.application_note && (
            <button
              className="text-xs text-accent/70 hover:text-accent mt-1"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? '− less' : '+ rationale'}
            </button>
          )}
          {!compact && expanded && (
            <p className="text-xs text-text-secondary/70 italic mt-1 leading-relaxed border-l border-border pl-2">
              {theory.rationale}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Ensemble summary component ────────────────────────────────────────────────

function EnsembleSummary({ label, theories, active }: { label: string; theories: Theory[]; active: boolean }) {
  return (
    <div className={`rounded border text-xs p-3 ${active ? 'border-accent/40 bg-accent/5' : 'border-border opacity-50'}`}>
      <p className="font-medium text-text-primary mb-1">{label} <span className="text-text-secondary font-normal">({theories.length} theories)</span></p>
      <div className="space-y-0.5">
        {theories.slice(0, 4).map(t => (
          <p key={t.theory_id} className="text-text-secondary truncate">· {t.display_name || t.theory_id}</p>
        ))}
        {theories.length > 4 && (
          <p className="text-text-secondary/60">+{theories.length - 4} more</p>
        )}
      </div>
    </div>
  )
}
