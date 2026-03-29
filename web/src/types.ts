export interface TheorySummary {
  theory_id: string
  name: string
  domains: string[]
  description: string
  reference: string
  parameter_count: number
  source: 'builtin' | 'discovered'
}

export interface ParameterInfo {
  name: string
  type: string
  description: string
  default: unknown
  has_default: boolean
}

export interface TheoryDetail extends TheorySummary {
  parameters: ParameterInfo[]
  reads: string[]
  writes: string[]
  initializes: string[]
}

export interface TheoryRecommendation {
  theory_id: string
  display_name: string
  score: number
  rationale: string
  application_note?: string
  source?: string
  domains?: string[]
  suggested_priority?: number
  parameters?: Record<string, unknown>
}

export interface EnsembleSummary {
  ensemble_id: string
  name: string
  source: 'user' | 'system' | 'recommended'
  theory_ids: string[]
  theory_count: number
  created_at: string
  forked_from: string | null
}

export interface Ensemble extends EnsembleSummary {
  theories: { theory_id: string; priority: number; parameters: Record<string, unknown> }[]
}

export interface PendingTheory {
  pending_id: string
  theory_id: string
  display_name: string
  domains: string[]
  citation: string
  source_url: string
  source_type: string
  abstract_snippet: string
  generated_code: string
  smoke_test: { passed: boolean; error?: string; instantiated?: boolean; update_ran?: boolean }
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  reviewed_at: string | null
  reviewed_by: string | null
  file_path: string | null
}

export interface ActorSpec {
  actor_id: string
  name: string
  description: string
  metadata: { role?: string; description?: string; [key: string]: unknown }
}

export interface SimSpec {
  scenario_id: string
  name: string
  domain: string
  actors: ActorSpec[]
  theories: { theory_id: string; priority: number; parameters: Record<string, unknown> }[]
  metrics: unknown[]
  [key: string]: unknown
}

export interface ForgeSession {
  session_id: string
  state: 'intake' | 'research' | 'dynamic_interview' | 'ensemble_review' | 'complete'
  simspec: SimSpec | null
  gaps: { field_path: string; description: string; priority: number; filled: boolean }[]
  message_count: number
  research_context: {
    library_additions: string[]
    library_gaps: string[]
  }
  recommended_theories: TheoryRecommendation[]
  discovered_theories: TheoryRecommendation[]
  custom_theories: TheoryRecommendation[] | null
  assessment_path: string | null
  findings_path: string | null
  data_gaps: string[]
  proprietary_gaps: string[]
  gap_research_running: boolean
  gap_research_complete: boolean
  closed_gaps: string[]
  remaining_gaps: string[]
}

export interface SimulationRun {
  sim_id: string
  session_id: string
  ensemble_type: 'recommended' | 'custom'
  theory_ids: string[]
  status: 'pending' | 'running' | 'complete' | 'error'
  started_at: number
  completed_at: number | null
  results: {
    ticks: number
    metric_series: Record<string, number[]>
    metric_names: Record<string, string>
    final_env: Record<string, number>
    snapshot_count: number
  } | null
  error: string | null
}
