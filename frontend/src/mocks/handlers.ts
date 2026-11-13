import { http, HttpResponse } from 'msw'

import { AARAV_ACCOUNT_ID, AARAV_AS_OF_DATE, AARAV_TRANSACTIONS, AARAV_USER_ID } from './fixtures/aarav'
import type { Category, Direction, Transaction } from '@/lib/types'

interface MockAccount {
  userId: number
  personaKey: string
  txns: Transaction[]
  nextTxnId: number
  nextMerchantId: number
  merchantIdByName: Map<string, number>
}

let nextAccountId = 1000
let nextUserId = 1000
const accounts = new Map<number, MockAccount>()

function seedAarav(personaKey: string): void {
  const txns = AARAV_TRANSACTIONS.map((t) => ({ ...t }))
  accounts.set(AARAV_ACCOUNT_ID, {
    userId: AARAV_USER_ID,
    personaKey,
    txns,
    nextTxnId: Math.max(...txns.map((t) => t.id)) + 1,
    nextMerchantId: Math.max(...txns.map((t) => t.merchant_id ?? 0)) + 1,
    merchantIdByName: new Map(
      txns.filter((t) => t.merchant_name).map((t) => [t.merchant_name as string, t.merchant_id as number]),
    ),
  })
}
seedAarav('aarav')

function merchantIdFor(account: MockAccount, name: string): number {
  const existing = account.merchantIdByName.get(name)
  if (existing != null) return existing
  const id = account.nextMerchantId++
  account.merchantIdByName.set(name, id)
  return id
}

interface MockParsed {
  amountPaise: number
  direction: Direction
  merchantName: string
  balanceAfterPaise: number | null
}

function mockParseSms(raw: string): MockParsed | null {
  const amountMatch = raw.match(/(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{1,2})?)/i)
  if (!amountMatch) return null
  const amountPaise = Math.round(parseFloat(amountMatch[1].replace(/,/g, '')) * 100)

  const isDebit = /\b(debited|paid to|sent|withdrawn|spent)\b/i.test(raw)
  const isCredit = /\b(credited|received from|deposited)\b/i.test(raw)
  if (!isDebit && !isCredit) return null
  const direction: Direction = isDebit ? 'DR' : 'CR'

  const vpaMatch = raw.match(/\b([\w.]+)@[\w.-]+\b/)
  const merchantName = vpaMatch ? vpaMatch[1] : 'Unknown merchant'

  const balMatch = raw.match(
    /(?:Avl\.?\s*Bal(?:ance)?|Available\s*balance)[:\s]*(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d{1,2})?)/i,
  )
  const balanceAfterPaise = balMatch ? Math.round(parseFloat(balMatch[1].replace(/,/g, '')) * 100) : null

  return { amountPaise, direction, merchantName, balanceAfterPaise }
}

function guessCategory(merchantName: string): { category: Category; confidence: number } {
  // No real model in mock mode — a stable-but-arbitrary split so both the
  // "confident" and "needs confirmation" onboarding paths are exercisable offline.
  const even = merchantName.length % 2 === 0
  return { category: 'shopping', confidence: even ? 0.92 : 0.45 }
}

function ingestOne(account: MockAccount, rawText: string, ts: string): Transaction | null {
  const parsed = mockParseSms(rawText)
  if (!parsed) return null
  const { category, confidence } = guessCategory(parsed.merchantName)
  const txn: Transaction = {
    id: account.nextTxnId++,
    ts,
    amount_paise: parsed.amountPaise,
    direction: parsed.direction,
    category,
    category_confidence: confidence,
    is_user_labelled: false,
    merchant_id: merchantIdFor(account, parsed.merchantName),
    merchant_name: parsed.merchantName,
    raw_text: rawText,
    balance_after_paise: parsed.balanceAfterPaise,
  }
  account.txns.unshift(txn)
  return txn
}

export const handlers = [
  http.get('/api/health', () => HttpResponse.json({ status: 'ok', as_of_date: AARAV_AS_OF_DATE })),

  http.post('/api/demo/:persona', ({ params }) => {
    const persona = String(params.persona)
    if (!['aarav', 'priya', 'fatima'].includes(persona)) {
      return HttpResponse.json({ detail: `unknown persona ${persona}` }, { status: 404 })
    }
    seedAarav(persona)
    return HttpResponse.json({ user_id: AARAV_USER_ID, persona_key: persona, account_id: AARAV_ACCOUNT_ID })
  }),

  http.post('/api/accounts', () => {
    const accountId = nextAccountId++
    const userId = nextUserId++
    accounts.set(accountId, {
      userId,
      personaKey: 'custom',
      txns: [],
      nextTxnId: 1,
      nextMerchantId: 1,
      merchantIdByName: new Map(),
    })
    return HttpResponse.json({ user_id: userId, account_id: accountId })
  }),

  http.get('/api/transactions', ({ request }) => {
    const url = new URL(request.url)
    const accountId = Number(url.searchParams.get('account_id'))
    const account = accounts.get(accountId)
    if (!account) return HttpResponse.json([], { status: 200 })

    const category = url.searchParams.get('category')
    const merchantId = url.searchParams.get('merchant_id')
    const from = url.searchParams.get('from')
    const to = url.searchParams.get('to')
    const limit = Number(url.searchParams.get('limit') ?? '50')
    const offset = Number(url.searchParams.get('offset') ?? '0')

    let rows = [...account.txns].sort((a, b) => b.ts.localeCompare(a.ts))
    if (category) rows = rows.filter((t) => t.category === category)
    if (merchantId) rows = rows.filter((t) => t.merchant_id === Number(merchantId))
    if (from) rows = rows.filter((t) => t.ts.slice(0, 10) >= from)
    if (to) rows = rows.filter((t) => t.ts.slice(0, 10) <= to)

    return HttpResponse.json(rows.slice(offset, offset + limit))
  }),

  http.patch('/api/transactions/:id', async ({ params, request }) => {
    const id = Number(params.id)
    const body = (await request.json()) as { category: Category }

    for (const account of accounts.values()) {
      const target = account.txns.find((t) => t.id === id)
      if (!target) continue

      target.category = body.category
      target.is_user_labelled = true
      const updatedIds = [target.id]

      for (const other of account.txns) {
        if (other.id === target.id) continue
        if (other.merchant_id === target.merchant_id && !other.is_user_labelled) {
          other.category = body.category
          updatedIds.push(other.id)
        }
      }
      return HttpResponse.json({ updated_count: updatedIds.length, txn_ids: updatedIds })
    }
    return HttpResponse.json({ detail: 'transaction not found' }, { status: 404 })
  }),

  http.post('/api/ingest/sms', async ({ request }) => {
    const body = (await request.json()) as { account_id: number; raw_text: string }
    const account = accounts.get(body.account_id)
    if (!account) return HttpResponse.json({ detail: 'unknown account' }, { status: 404 })

    const txn = ingestOne(account, body.raw_text, new Date().toISOString())
    if (!txn) return HttpResponse.json({ detail: 'Could not parse SMS text' }, { status: 422 })

    return HttpResponse.json({
      txn_id: txn.id,
      amount_paise: txn.amount_paise,
      direction: txn.direction,
      category: txn.category,
      category_confidence: txn.category_confidence,
      txn_ids: [txn.id],
    })
  }),

  http.post('/api/ingest/sms/batch', async ({ request }) => {
    const body = (await request.json()) as { account_id: number; messages: string[] }
    const account = accounts.get(body.account_id)
    if (!account) return HttpResponse.json({ detail: 'unknown account' }, { status: 404 })

    const results = body.messages.map((rawText) => {
      const txn = ingestOne(account, rawText, new Date().toISOString())
      if (!txn) return { ok: false, raw_text: rawText }
      return {
        ok: true,
        raw_text: rawText,
        txn_id: txn.id,
        amount_paise: txn.amount_paise,
        direction: txn.direction,
        category: txn.category,
        category_confidence: txn.category_confidence,
      }
    })
    return HttpResponse.json({ results })
  }),

  http.post('/api/ingest/statement', async ({ request }) => {
    const url = new URL(request.url)
    const accountId = Number(url.searchParams.get('account_id'))
    const account = accounts.get(accountId)
    if (!account) return HttpResponse.json({ detail: 'unknown account' }, { status: 404 })

    const formData = await request.formData()
    const file = formData.get('file') as File | null
    if (!file) return HttpResponse.json({ ingested: 0, skipped: 0 })

    const text = await file.text()
    const lines = text
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
    const rows = lines[0]?.toLowerCase().startsWith('date') ? lines.slice(1) : lines

    let ingested = 0
    let skipped = 0
    for (const line of rows) {
      const parts = line.split(',').map((p) => p.trim())
      if (parts.length < 5) {
        skipped += 1
        continue
      }
      const [, narration, debit, credit, balance] = parts
      const amountRupees = parseFloat(debit || credit || '')
      if (Number.isNaN(amountRupees)) {
        skipped += 1
        continue
      }
      const direction: Direction = debit ? 'DR' : 'CR'
      const vpaMatch = narration.match(/\/([\w.]+)@[\w.-]+\//)
      const merchantName = vpaMatch ? vpaMatch[1] : narration.slice(0, 24)
      const { category, confidence } = guessCategory(merchantName)
      account.txns.unshift({
        id: account.nextTxnId++,
        ts: new Date().toISOString(),
        amount_paise: Math.round(amountRupees * 100),
        direction,
        category,
        category_confidence: confidence,
        is_user_labelled: false,
        merchant_id: merchantIdFor(account, merchantName),
        merchant_name: merchantName,
        raw_text: narration,
        balance_after_paise: balance ? Math.round(parseFloat(balance) * 100) : null,
      })
      ingested += 1
    }
    return HttpResponse.json({ ingested, skipped })
  }),
]
