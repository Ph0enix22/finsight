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
