import type {
  Category,
  CreateAccountResponse,
  DemoPersonaResponse,
  HealthResponse,
  IngestSmsBatchResponse,
  IngestSmsResponse,
  IngestStatementResponse,
  RecategoriseResponse,
  Transaction,
} from '@/lib/types'

export const MOCK_MODE = import.meta.env.VITE_MOCK_API === 'true'

const BASE_URL = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export interface ListTransactionsParams {
  accountId: number
  category?: Category
  merchantId?: number
  from?: string
  to?: string
  limit?: number
  offset?: number
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  loadDemoPersona: (persona: string) =>
    request<DemoPersonaResponse>(`/demo/${persona}`, { method: 'POST' }),

  createAccount: () => request<CreateAccountResponse>('/accounts', { method: 'POST' }),

  listTransactions: ({ accountId, category, merchantId, from, to, limit, offset }: ListTransactionsParams) => {
    const params = new URLSearchParams({ account_id: String(accountId) })
    if (category) params.set('category', category)
    if (merchantId) params.set('merchant_id', String(merchantId))
    if (from) params.set('from', from)
    if (to) params.set('to', to)
    if (limit) params.set('limit', String(limit))
    if (offset) params.set('offset', String(offset))
    return request<Transaction[]>(`/transactions?${params.toString()}`)
  },

  recategorise: (txnId: number, category: Category) =>
    request<RecategoriseResponse>(`/transactions/${txnId}`, {
      method: 'PATCH',
      body: JSON.stringify({ category }),
    }),

  ingestSms: (accountId: number, rawText: string) =>
    request<IngestSmsResponse>('/ingest/sms', {
      method: 'POST',
      body: JSON.stringify({ account_id: accountId, raw_text: rawText }),
    }),

  ingestSmsBatch: (accountId: number, messages: string[]) =>
    request<IngestSmsBatchResponse>('/ingest/sms/batch', {
      method: 'POST',
      body: JSON.stringify({ account_id: accountId, messages }),
    }),

  ingestStatement: (accountId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<IngestStatementResponse>(`/ingest/statement?account_id=${accountId}`, {
      method: 'POST',
      body: form,
    })
  },
}
