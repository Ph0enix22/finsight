export const CATEGORIES = [
  'food_delivery',
  'dining_cafe',
  'groceries_qcommerce',
  'transport',
  'rent_housing',
  'utilities_recharge',
  'subscriptions',
  'shopping',
  'education',
  'health',
  'entertainment',
  'transfers_family',
  'transfers_friends',
  'income',
] as const

export type Category = (typeof CATEGORIES)[number]

export const CATEGORY_LABELS: Record<Category, string> = {
  food_delivery: 'Food delivery',
  dining_cafe: 'Dining & cafes',
  groceries_qcommerce: 'Groceries',
  transport: 'Transport',
  rent_housing: 'Rent & housing',
  utilities_recharge: 'Utilities & recharge',
  subscriptions: 'Subscriptions',
  shopping: 'Shopping',
  education: 'Education',
  health: 'Health',
  entertainment: 'Entertainment',
  transfers_family: 'Family transfers',
  transfers_friends: 'Friend transfers',
  income: 'Income',
}

export type Direction = 'DR' | 'CR'

export interface Transaction {
  id: number
  ts: string
  amount_paise: number
  direction: Direction
  category: Category | null
  category_confidence: number | null
  is_user_labelled: boolean
  merchant_id: number | null
  merchant_name: string | null
  raw_text: string
  balance_after_paise: number | null
}

export interface IngestSmsResponse {
  txn_id: number
  amount_paise: number
  direction: Direction
  category: Category
  category_confidence: number
  txn_ids: number[]
}

export interface IngestStatementResponse {
  ingested: number
  skipped: number
}

export interface IngestSmsBatchItem {
  ok: boolean
  raw_text: string
  txn_id: number | null
  amount_paise: number | null
  direction: Direction | null
  category: Category | null
  category_confidence: number | null
}

export interface IngestSmsBatchResponse {
  results: IngestSmsBatchItem[]
}

export interface RecategoriseResponse {
  updated_count: number
  txn_ids: number[]
}

export interface DemoPersonaResponse {
  user_id: number
  persona_key: string
  account_id: number
}

export interface CreateAccountResponse {
  user_id: number
  account_id: number
}

export interface HealthResponse {
  status: string
  as_of_date: string
}

export interface ForecastPoint {
  date: string
  p10: number
  median: number
  p90: number
}

export interface ForecastOut {
  forecast: ForecastPoint[]
  p_run_out: number
  safe_to_spend_per_day_paise: number
}

export interface RecurringSeries {
  merchant_id: number
  merchant_name: string | null
  direction: Direction
  period_days: number
  typical_amount_paise: number
  next_due: string
}

export interface RunwayResponse extends ForecastOut {
  as_of_date: string
  current_balance_paise: number
  next_inflow_date: string
  next_inflow_amount_paise: number
  recurring_series: RecurringSeries[]
  txn_ids: number[]
}

export type ScenarioEvent =
  | { type: 'one_time_purchase'; amount_paise: number; date: string }
  | { type: 'emi'; amount_paise: number; months: number; start_date: string }
  | { type: 'trip'; amount_paise: number; start_date: string; end_date: string }
  | { type: 'goal'; target_amount_paise: number; target_date: string }
  | { type: 'recurring_change'; mode: 'cancel'; merchant_id: number }
  | {
      type: 'recurring_change'
      mode: 'add'
      direction: Direction
      period_days: number
      typical_amount_paise: number
      next_due: string
    }

export interface TwinSimulateRequest {
  account_id: number
  events: ScenarioEvent[]
  goal_target_amount_paise?: number
}

export interface TwinSimulateResponse {
  as_of_date: string
  baseline: ForecastOut
  scenario: ForecastOut
  goal_delay_days: number | null
  txn_ids: number[]
}

export interface GoalCreate {
  user_id: number
  name: string
  target_amount_paise: number
  target_date: string
  saved_so_far_paise?: number
}

export interface Goal {
  id: number
  user_id: number
  name: string
  target_amount_paise: number
  target_date: string
  saved_so_far_paise: number
}
