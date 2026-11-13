import { Receipt } from 'lucide-react'
import { useState } from 'react'

import { BottomSheet } from '@/components/ui/BottomSheet'
import { TxnRow } from '@/components/TxnRow'
import type { Transaction } from '@/lib/types'

interface ReceiptChipProps {
  label: string
  sheetTitle: string
  formula: string
  txns: Transaction[]
}

export function ReceiptChip({ label, sheetTitle, formula, txns }: ReceiptChipProps) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex min-h-8 items-center gap-1.5 rounded-full bg-muted px-3 text-micro font-medium text-foreground hover:bg-border"
      >
        <Receipt size={13} />
        {label}
      </button>
      <BottomSheet open={open} onOpenChange={setOpen} title={sheetTitle}>
        <p className="pb-3 text-small text-muted-foreground">{formula}</p>
        <div className="divide-y divide-border">
          {txns.map((txn) => (
            <TxnRow key={txn.id} txn={txn} showDate />
          ))}
        </div>
      </BottomSheet>
    </>
  )
}
