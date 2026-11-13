import { ClipboardPaste, Loader2, ShieldCheck, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { DarkModeToggle } from '@/components/DarkModeToggle'
import { api } from '@/lib/api'
import { CATEGORIES, CATEGORY_LABELS, type Category, type IngestSmsBatchItem } from '@/lib/types'
import { useSession, type Session } from '@/lib/session'
import { AARAV_SAMPLE_SMS } from '@/lib/sampleSms'
import { splitSmsMessages } from '@/lib/smsSplit'

const PERSONAS = [
  { key: 'aarav', name: 'Aarav', blurb: '19 · hostel B.Tech, ₹9k/mo on the 1st' },
  { key: 'priya', name: 'Priya', blurb: '23 · SDE Bengaluru, ₹68k salary' },
  { key: 'fatima', name: 'Fatima', blurb: '21 · design student, stipend + freelance' },
] as const

const BATCH_SIZE = 5
const LOW_CONFIDENCE_THRESHOLD = 0.6
const MAX_CONFIRMS = 3

interface ConfirmItem {
  txnId: number
  label: string
  category: Category
}

type PendingSession = Session

export function Onboarding() {
  const navigate = useNavigate()
  const { setSession } = useSession()

  const [mode, setMode] = useState<'persona' | 'paste' | 'upload'>('persona')
  const [loadingPersona, setLoadingPersona] = useState<string | null>(null)

  const [pasteText, setPasteText] = useState('')
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const [pendingSession, setPendingSession] = useState<PendingSession | null>(null)
  const [confirms, setConfirms] = useState<ConfirmItem[] | null>(null)
  const [confirmPicks, setConfirmPicks] = useState<Record<number, Category>>({})

  const busy = loadingPersona != null || progress != null || uploadBusy

  function complete(session: Session) {
    setSession(session)
    navigate('/today')
  }

  function offerConfirmOrComplete(session: PendingSession, items: ConfirmItem[]) {
    if (items.length === 0) {
      complete(session)
      return
    }
    setPendingSession(session)
    setConfirms(items)
    setConfirmPicks(Object.fromEntries(items.map((item) => [item.txnId, item.category])))
  }

  async function handlePersona(personaKey: string) {
    setError(null)
    setLoadingPersona(personaKey)
    try {
      const res = await api.loadDemoPersona(personaKey)
      await new Promise((resolve) => setTimeout(resolve, 500))
      complete({ userId: res.user_id, accountId: res.account_id, personaKey: res.persona_key })
    } catch {
      setError('Could not load that persona. Check the backend is running.')
      setLoadingPersona(null)
    }
  }

  async function handleDecodePaste() {
    setError(null)
    const messages = splitSmsMessages(pasteText)
    if (messages.length === 0) {
      setError('Paste at least one SMS first.')
      return
    }
    setProgress({ done: 0, total: messages.length })
    try {
      const account = await api.createAccount()
      const results: IngestSmsBatchItem[] = []
      for (let i = 0; i < messages.length; i += BATCH_SIZE) {
        const batch = messages.slice(i, i + BATCH_SIZE)
        const res = await api.ingestSmsBatch(account.account_id, batch)
        results.push(...res.results)
        setProgress({ done: Math.min(i + BATCH_SIZE, messages.length), total: messages.length })
      }
      const lowConfidence = results
        .filter(
          (r): r is IngestSmsBatchItem & { txn_id: number; category: Category } =>
            r.ok && r.category_confidence != null && r.category_confidence < LOW_CONFIDENCE_THRESHOLD,
        )
        .slice(0, MAX_CONFIRMS)
        .map((r) => ({ txnId: r.txn_id, label: r.raw_text.slice(0, 48), category: r.category }))
      offerConfirmOrComplete(
        { userId: account.user_id, accountId: account.account_id, personaKey: 'custom' },
        lowConfidence,
      )
    } catch {
      setError('Decoding failed partway through. Check the backend is running.')
    } finally {
      setProgress(null)
    }
  }

  async function handleUpload(file: File) {
    setError(null)
    setUploadBusy(true)
    try {
      const account = await api.createAccount()
      const { ingested } = await api.ingestStatement(account.account_id, file)
      const txns = await api.listTransactions({
        accountId: account.account_id,
        limit: Math.min(ingested, 100) || 100,
      })
      const lowConfidence = txns
        .filter((t) => t.category_confidence != null && t.category_confidence < LOW_CONFIDENCE_THRESHOLD)
        .slice(0, MAX_CONFIRMS)
        .map((t) => ({
          txnId: t.id,
          label: t.merchant_name ?? t.raw_text.slice(0, 48),
          category: t.category ?? ('shopping' as Category),
        }))
      offerConfirmOrComplete(
        { userId: account.user_id, accountId: account.account_id, personaKey: 'custom' },
        lowConfidence,
      )
    } catch {
      setError('Could not read that file. Try a CSV or PDF statement export.')
    } finally {
      setUploadBusy(false)
    }
  }

  async function handleConfirmContinue() {
    if (!pendingSession || !confirms) return
    await Promise.all(
      confirms.map((item) => api.recategorise(item.txnId, confirmPicks[item.txnId] ?? item.category)),
    )
    complete(pendingSession)
  }

  if (confirms && pendingSession) {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-[430px] flex-col bg-background px-5 py-8">
        <p className="font-heading text-h1 text-foreground">Quick check</p>
        <p className="mt-1 text-small text-muted-foreground">
          We were not fully sure about {confirms.length} merchant{confirms.length > 1 ? 's' : ''}.
        </p>
        <div className="mt-6 space-y-4">
          {confirms.map((item) => (
            <div key={item.txnId} className="rounded-card bg-card p-4">
              <p className="truncate text-small text-foreground">{item.label}</p>
              <select
                value={confirmPicks[item.txnId] ?? item.category}
                onChange={(e) =>
                  setConfirmPicks((prev) => ({ ...prev, [item.txnId]: e.target.value as Category }))
                }
                className="mt-2 min-h-11 w-full rounded-input border border-border bg-background px-3 text-small text-foreground"
              >
                {CATEGORIES.filter((c) => c !== 'income').map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_LABELS[c]}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
        <Button size="lg" className="mt-8 w-full" onClick={handleConfirmContinue}>
          Looks good — continue
        </Button>
      </div>
    )
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[430px] flex-col bg-background px-5 py-8">
      <div className="flex justify-end">
        <DarkModeToggle />
      </div>

      <div className="mt-2">
        <p className="font-heading text-hero font-bold leading-[1.05] text-foreground">
          Know before
          <br />
          you pay.
        </p>
        <p className="mt-3 text-body text-muted-foreground">Before you tap Pay, ask your twin.</p>
        <div className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-micro text-muted-foreground">
          <ShieldCheck size={13} />
          Synthetic data only
        </div>
      </div>

      <div className="mt-8 space-y-3">
        {PERSONAS.map((persona) => (
          <button
            key={persona.key}
            type="button"
            disabled={busy}
            onClick={() => handlePersona(persona.key)}
            className="flex w-full items-center gap-3 rounded-card bg-card p-4 text-left transition-opacity disabled:opacity-60"
          >
            <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-muted font-heading text-h2 font-semibold text-foreground">
              {persona.name.charAt(0)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-body font-medium text-foreground">{persona.name}</p>
              <p className="text-micro text-muted-foreground">{persona.blurb}</p>
            </div>
            {loadingPersona === persona.key && (
              <Loader2 className="animate-spin text-muted-foreground" size={18} />
            )}
          </button>
        ))}
      </div>

      <div className="mt-6 flex items-center gap-3">
        <div className="h-px flex-1 bg-border" />
        <span className="text-micro text-muted-foreground">or add your own</span>
        <div className="h-px flex-1 bg-border" />
      </div>

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          onClick={() => setMode('paste')}
          className={`flex-1 rounded-input border px-3 py-2 text-small font-medium transition-colors ${
            mode === 'paste' ? 'border-primary text-primary' : 'border-border text-muted-foreground'
          }`}
        >
          <ClipboardPaste size={14} className="mr-1.5 inline-block" />
          Paste SMS
        </button>
        <button
          type="button"
          onClick={() => setMode('upload')}
          className={`flex-1 rounded-input border px-3 py-2 text-small font-medium transition-colors ${
            mode === 'upload' ? 'border-primary text-primary' : 'border-border text-muted-foreground'
          }`}
        >
          <Upload size={14} className="mr-1.5 inline-block" />
          Upload
        </button>
      </div>

      {mode === 'paste' && (
        <div className="mt-4">
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder="Paste one or more bank SMS — separate each with a blank line"
            rows={5}
            disabled={busy}
            className="w-full rounded-input border border-border bg-card p-3 text-small text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => setPasteText(AARAV_SAMPLE_SMS)}
            className="mt-1.5 text-micro text-muted-foreground underline-offset-4 hover:text-foreground hover:underline disabled:opacity-60"
          >
            Use sample messages
          </button>
          <Button size="lg" className="mt-3 w-full" disabled={busy} onClick={handleDecodePaste}>
            {progress ? (
              <>
                <Loader2 className="mr-1.5 animate-spin" size={16} />
                Decoded {progress.done} of {progress.total}…
              </>
            ) : (
              'Decode'
            )}
          </Button>
        </div>
      )}

      {mode === 'upload' && (
        <div className="mt-4">
          <button
            type="button"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
            className="flex w-full flex-col items-center gap-2 rounded-input border-2 border-dashed border-border px-4 py-8 text-center disabled:opacity-60"
          >
            <Upload className="text-muted-foreground" size={22} />
            <span className="text-small text-muted-foreground">
              {uploadBusy ? 'Reading your statement…' : 'Tap to choose a CSV or PDF statement'}
            </span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.pdf"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void handleUpload(file)
            }}
          />
        </div>
      )}

      {error && <p className="mt-3 text-small text-risk">{error}</p>}
    </div>
  )
}
