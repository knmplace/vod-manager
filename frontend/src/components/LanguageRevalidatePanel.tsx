// KNM: 2026-11-05 - one-time re-validation of results from the older language probe; preview first.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Eye, Loader2, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import api from '@/lib/api'
import { askConfirm, notify } from '@/lib/confirm'

type Preview = { requeue: number; verify: number; repair_feeds: number; restore_titles: number; applied_at: string | null }
type Result = { requeued: number; verify_queued: number; repaired_feeds: number; restored_titles: number }

export default function LanguageRevalidatePanel() {
  const qc = useQueryClient()
  const [preview, setPreview] = useState<Preview | null>(null)
  const runPreview = useMutation({
    mutationFn: () => api.get('/vod/language-revalidate/preview/').then((r) => r.data as Preview),
    onSuccess: (data) => setPreview(data),
  })
  const apply = useMutation({
    mutationFn: () => api.post('/vod/language-revalidate/apply/').then((r) => r.data as Result),
    onSuccess: (r) => {
      setPreview(null)
      ;['language-mismatch-report', 'language-autoclean-log'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      notify(`Re-validation started: ${r.requeued.toLocaleString()} queued for a new check, ${r.verify_queued.toLocaleString()} confirmations queued for a re-check, ${r.repaired_feeds.toLocaleString()} feeds hidden, ${r.restored_titles.toLocaleString()} titles restored.`)
    },
  })
  const total = preview ? preview.requeue + preview.verify + preview.repair_feeds + preview.restore_titles : 0
  const confirmApply = () => askConfirm(
    'Re-validate language results? Unknown and unreviewed results are checked again with the current audio check, and your earlier confirmations are re-checked once. Feeds that were confirmed by matching audio tags are left alone. Any feed hidden by this is logged in the auto-clean log and can be reverted.',
    () => apply.mutate(), 'Re-validate')

  return (
    <details className="rounded-md border border-border bg-card px-3 py-3">
      <summary className="cursor-pointer text-xs font-medium">Re-validate language results (one-time)</summary>
      <p className="text-[11px] text-muted-foreground mt-2">For libraries checked before the improved audio check. Puts older results back through the background language check. Safe to run again: anything already checked with the current version is skipped.{preview?.applied_at ? ` First run: ${new Date(preview.applied_at).toLocaleString()}.` : ''}</p>
      <div className="flex flex-wrap items-end gap-3 mt-2">
        <button className="flex items-center gap-1.5 border border-border rounded px-2 py-1.5 text-xs hover:bg-accent disabled:opacity-50" disabled={runPreview.isPending} onClick={() => runPreview.mutate()}>{runPreview.isPending ? <Loader2 size={12} className="animate-spin" /> : <Eye size={12} />} Preview</button>
        {preview && <button className="flex items-center gap-1.5 border border-amber-500/40 text-amber-400 rounded px-2 py-1.5 text-xs hover:bg-accent disabled:opacity-50" disabled={apply.isPending || total === 0} onClick={confirmApply}>{apply.isPending ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />} Re-validate</button>}
      </div>
      {preview && (
        <ul className="text-[11px] text-muted-foreground mt-2">
          <li>Unknown or unreviewed results to check again: {preview.requeue.toLocaleString()}</li>
          <li>Your earlier confirmations to re-check once: {preview.verify.toLocaleString()}</li>
          <li>Feeds marked to hide that are still being served: {preview.repair_feeds.toLocaleString()}</li>
          <li>Hidden titles that do have a wanted-language feed: {preview.restore_titles.toLocaleString()}</li>
          {total === 0 && <li className="text-emerald-400">Nothing left to re-validate.</li>}
        </ul>
      )}
    </details>
  )
}
