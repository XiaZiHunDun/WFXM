export const DEFAULT_WINDOW_SECONDS = 60
export const DEFAULT_COUNT_THRESHOLD = 3
const MAX_LAST_N_ACTIONS = 100

export interface AuditEventSummary {
  readonly event_id: string
  readonly tool_name: string
  readonly actor: string
  readonly ts: number
  readonly decision: 'allow' | 'checklist' | 'cooldown'
}

export interface AuditLogReader {
  readRecent(windowMs: number): Promise<ReadonlyArray<AuditEventSummary>>
}

export interface FatigueSignal {
  readonly count: number
  readonly window_seconds: number
  readonly last_n_actions: ReadonlyArray<AuditEventSummary>
  readonly degraded?: true
}

export async function computeFatigueSignal(
  reader: AuditLogReader,
  windowSeconds: number = DEFAULT_WINDOW_SECONDS,
): Promise<FatigueSignal> {
  try {
    const events = await reader.readRecent(windowSeconds * 1000)
    const lastN = events.slice(-MAX_LAST_N_ACTIONS)
    return {
      count: events.length,
      window_seconds: windowSeconds,
      last_n_actions: lastN,
    }
  } catch {
    return {
      count: 0,
      window_seconds: windowSeconds,
      last_n_actions: [],
      degraded: true,
    }
  }
}