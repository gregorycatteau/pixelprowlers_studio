export interface AgentSummary {
  slug: string
  name: string
  alias: string
  remaining_eur_today: string
  schema_version: string
  profile_version: string
}

export interface AgentsResponse {
  agents: AgentSummary[]
}

export interface AskBody {
  message: string
  agent?: string
}

export interface AskResponse {
  ok: boolean
  agent: string
  provider: string
  model_uri: string
  output: string
  tokens_in: number
  tokens_out: number
  cost_eur: number
  latency_ms: number
  error?: string
}
