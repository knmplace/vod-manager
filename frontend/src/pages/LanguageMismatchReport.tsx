import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Languages, Loader2, RefreshCw, X } from 'lucide-react'
import api from '@/lib/api'
import { notify } from '@/lib/confirm'

type Mismatch = {
  kind: 'movie' | 'episode'
  source_id: number
  item_id: number
  title: string
  year: number | null
  tmdb_id: string | null
  provider_name: string
  configured_language: string | null
  observed_languages: string[]
  language_probe_confidence: string | null
  language_probed_at: string | null
  season_number?: number
  episode_number?: number
  episode_name?: string | null
  safe_to_apply: boolean
  proposed_language: string | null
  proposed_archive: boolean
}

type Report = { enabled_languages: string[]; count: number; results: Mismatch[]; trickle?: { interval_seconds: number; daily_max: number; checked_today: number; global_concurrency: number; language_window_max: number; language_window_seconds: number; blocked_providers: number } }

const NAMES: Record<string, string> = {
  EN: 'English', HI: 'Hindi', FR: 'French', ES: 'Spanish', DE: 'German', IT: 'Italian',
  PT: 'Portuguese', JA: 'Japanese', ZH: 'Chinese', KO: 'Korean', AR: 'Arabic',
  RU: 'Russian', TA: 'Tamil', TE: 'Telugu', ML: 'Malayalam', TH: 'Thai',
}

function languageLabel(code: string | null | undefined) {
  if (!code) return 'Unknown'
  return `${code} — ${NAMES[code] ?? code}`
}

export default function LanguageMismatchReport() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const report = useQuery<Report>({
    queryKey: ['language-mismatch-report'],
    queryFn: () => api.get('/vod/language-mismatch-report/').then((r) => r.data),
    refetchInterval: 30_000,
  })
  const rows = report.data?.results ?? []
  const key = (r: Mismatch) => `${r.kind}:${r.source_id}`
  const selectable = useMemo(() => rows.filter((r) => r.safe_to_apply).map(key), [rows])
  useEffect(() => {
    setSelected((old) => new Set([...old].filter((id) => rows.some((r) => key(r) === id))))
  }, [rows])

  const decide = useMutation({
    mutationFn: ({ row, decision }: { row: Mismatch; decision: 'approved' | 'rejected' }) =>
      api.post(`/vod/language-mismatch/${row.kind}/${row.source_id}/decision/`, { decision }).then((r) => r.data),
    onSuccess: (result) => {
      notify(result.action === 'language_updated_and_archived' ? 'Language updated and item archived.' : result.action === 'language_updated_and_restored' ? 'Language updated and item restored.' : result.decision === 'rejected' ? 'Mismatch ignored and will not be rechecked.' : 'Language updated; no archive was needed.')
      qc.invalidateQueries({ queryKey: ['language-mismatch-report'] })
      qc.invalidateQueries({ queryKey: ['vod-notices'] })
    },
    onError: (e: any) => notify(e?.response?.data?.detail ?? 'Could not record the language decision.'),
  })

  const runBulk = async (decision: 'approved' | 'rejected', all = false) => {
    const targets = all ? rows : rows.filter((r) => selected.has(key(r)))
    const safeTargets = decision === 'approved' ? targets.filter((r) => r.safe_to_apply) : targets
    if (!safeTargets.length) { notify(decision === 'approved' ? 'No single-language results are selected for approval.' : 'No mismatches are selected.'); return }
    for (const row of safeTargets) await decide.mutateAsync({ row, decision })
    setSelected(new Set())
  }

  if (report.isLoading) return <div className="flex items-center gap-2 text-muted-foreground"><Loader2 size={15} className="animate-spin" /> Loading language mismatch report…</div>
  if (report.isError) return <div className="text-destructive">Could not load the language mismatch report.</div>

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold flex items-center gap-2"><Languages size={18} /> Language Mismatch Report</h1>
          <p className="text-xs text-muted-foreground mt-1">Embedded audio tags are compared with the configured source language. Approved single-language mismatches update the source and archive it when that language is excluded. Reject records the decision and prevents automatic re-checking.</p>
          <p className="text-xs text-muted-foreground mt-1">Wanted playback languages: {report.data?.enabled_languages.join(', ') || 'none'}</p>
          {report.data?.trickle && <p className="text-xs text-muted-foreground mt-1">Trickle: up to {report.data.trickle.global_concurrency} probes every {report.data.trickle.interval_seconds}s · {report.data.trickle.checked_today}/{report.data.trickle.daily_max} today · language cap {report.data.trickle.language_window_max} per {Math.round(report.data.trickle.language_window_seconds / 60)} minutes{report.data.trickle.blocked_providers ? ` · ${report.data.trickle.blocked_providers} provider paused` : ''}</p>}
        </div>
        <button className="flex items-center gap-1.5 border border-border rounded px-2 py-1.5 text-xs hover:bg-accent disabled:opacity-50" disabled={report.isFetching} onClick={() => report.refetch()}><RefreshCw size={12} className={report.isFetching ? 'animate-spin' : ''} /> Refresh</button>
      </div>

      <div className="flex flex-wrap items-center gap-2 border border-border rounded-md bg-card px-3 py-2 text-xs">
        <span className="text-muted-foreground">{rows.length} pending mismatch{rows.length === 1 ? '' : 'es'}</span>
        <span className="text-muted-foreground">· {selected.size} selected</span>
        <button className="ml-auto border border-border rounded px-2 py-1 hover:bg-accent" onClick={() => setSelected(new Set(selectable))}>Select all approvable</button>
        <button className="border border-emerald-500/40 text-emerald-400 rounded px-2 py-1 hover:bg-emerald-500/10 disabled:opacity-50" disabled={decide.isPending || !selected.size} onClick={() => runBulk('approved')}>Approve selected</button>
        <button className="border border-amber-500/40 text-amber-400 rounded px-2 py-1 hover:bg-amber-500/10 disabled:opacity-50" disabled={decide.isPending || !selected.size} onClick={() => runBulk('rejected')}>Reject selected</button>
        <button className="border border-emerald-500/40 text-emerald-400 rounded px-2 py-1 hover:bg-emerald-500/10 disabled:opacity-50" disabled={decide.isPending || !rows.length} onClick={() => runBulk('approved', true)}>Approve all proposed</button>
        <button className="border border-amber-500/40 text-amber-400 rounded px-2 py-1 hover:bg-amber-500/10 disabled:opacity-50" disabled={decide.isPending || !rows.length} onClick={() => runBulk('rejected', true)}>Reject all</button>
      </div>

      {rows.length === 0 ? <div className="border border-border rounded-md bg-card p-8 text-center text-sm text-muted-foreground">No pending language mismatches.</div> : (
        <div className="overflow-x-auto border border-border rounded-md">
          <table className="w-full text-xs">
            <thead className="bg-card text-muted-foreground"><tr className="text-left">
              <th className="p-2 w-8"></th><th className="p-2">Title</th><th className="p-2">Provider</th><th className="p-2">Configured</th><th className="p-2">Observed</th><th className="p-2">Proposed result</th><th className="p-2">Checked</th><th className="p-2">Decision</th>
            </tr></thead>
            <tbody>{rows.map((row) => {
              const id = key(row); const disabled = !row.safe_to_apply
              return <tr key={id} className="border-t border-border/60 align-top">
                <td className="p-2"><input type="checkbox" disabled={disabled} checked={selected.has(id)} onChange={(e) => setSelected((old) => { const n = new Set(old); e.target.checked ? n.add(id) : n.delete(id); return n })} /></td>
                <td className="p-2"><div className="font-medium">{row.title} {row.year ? `(${row.year})` : ''}</div><div className="text-muted-foreground">{row.kind === 'episode' ? `S${row.season_number}E${row.episode_number} · ${row.episode_name ?? ''}` : 'Movie'}{row.tmdb_id ? ` · TMDB ${row.tmdb_id}` : ''}</div></td>
                <td className="p-2">{row.provider_name}</td>
                <td className="p-2">{languageLabel(row.configured_language)}</td>
                <td className="p-2">{row.observed_languages.map(languageLabel).join(', ')}</td>
                <td className="p-2">{disabled ? 'Manual review required' : <>{languageLabel(row.proposed_language)}{row.proposed_archive && <div className="text-amber-400">Then archive</div>}</>}</td>
                <td className="p-2 text-muted-foreground">{row.language_probed_at ? new Date(row.language_probed_at).toLocaleString() : '—'}</td>
                <td className="p-2"><span className="flex gap-1"><button title="Approve proposed language change" disabled={decide.isPending || disabled} className="p-1 rounded border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-40" onClick={() => decide.mutate({ row, decision: 'approved' })}><Check size={13} /></button><button title="Reject and do not re-check" disabled={decide.isPending} className="p-1 rounded border border-amber-500/40 text-amber-400 hover:bg-amber-500/10 disabled:opacity-40" onClick={() => decide.mutate({ row, decision: 'rejected' })}><X size={13} /></button></span></td>
              </tr>
            })}</tbody>
          </table>
        </div>
      )}
    </div>
  )
}
