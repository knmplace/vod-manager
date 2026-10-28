import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Languages, Loader2, Power, RefreshCw, X } from 'lucide-react'
import api from '@/lib/api'
import { notify } from '@/lib/confirm'
import { buildHlsPreviewSourceUrl, buildPreviewSourceUrl, buildTranscodedPreviewSourceUrl, PlayButton, type XcCredentials } from './VodManager'

type Mismatch = {
  kind: 'movie' | 'episode'
  source_id: number
  item_id: number
  title: string
  year: number | null
  tmdb_id: string | null
  container_extension: string | null
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

type Stats = { eligible: { movies: number; series: number; total: number }; pending_review: number; wanted_languages: string[]; history: { day: string; probes: number; mismatches: number; not_needed: number; outside_wanted: number; wanted_only: number; errors: number }[]; provider_history: { provider: string; type: 'M' | 'S'; probes: number; mismatches: number; not_needed: number; outside_wanted: number; wanted_only: number; errors: number }[] }
type Report = { enabled_languages: string[]; count: number; results: Mismatch[]; stats?: Stats; trickle?: { enabled: boolean; interval_seconds: number; daily_max: number | null; checked_today: number; probes_per_cycle: number; language_window_max: number | null; language_window_seconds: number } }

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
  const settings = useQuery({ queryKey: ['language-trickle-settings'], queryFn: () => api.get('/vod/language-trickle/settings/').then((r) => r.data) })
  const credentials = useQuery<XcCredentials>({ queryKey: ['vod-xc-credentials'], queryFn: () => api.get('/vod/xc-credentials/').then((r) => r.data), retry: false })
  const [form, setForm] = useState({ probes_per_cycle: 15, interval_seconds: 120, daily_limit: '' })
  useEffect(() => {
    if (settings.data) setForm({ probes_per_cycle: settings.data.language_trickle_probes_per_cycle, interval_seconds: settings.data.language_trickle_interval_seconds, daily_limit: settings.data.language_trickle_daily_limit == null ? '' : String(settings.data.language_trickle_daily_limit) })
  }, [settings.data])
  const saveSettings = useMutation({
    mutationFn: () => api.post('/vod/language-trickle/settings/', { probes_per_cycle: Number(form.probes_per_cycle), interval_seconds: Number(form.interval_seconds), daily_limit: form.daily_limit === '' ? null : Number(form.daily_limit) }).then((r) => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['language-trickle-settings'] }); qc.invalidateQueries({ queryKey: ['language-mismatch-report'] }); notify('Language probe pacing saved.') },
    onError: (e: any) => notify(e?.response?.data?.detail ?? 'Could not save language probe pacing.'),
  })
  const toggleEnabled = useMutation({
    mutationFn: (enabled: boolean) => api.post('/vod/language-trickle/enabled/', { enabled }).then((r) => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['language-trickle-settings'] }); qc.invalidateQueries({ queryKey: ['language-mismatch-report'] }); notify('Language mismatch monitoring state saved.') },
    onError: (e: any) => notify(e?.response?.data?.detail ?? 'Could not change language mismatch monitoring state.'),
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
  const runNow = useMutation({
    mutationFn: () => api.post('/vod/language-trickle/run/').then((r) => r.data),
    onSuccess: (result) => {
      notify(result.targets ? `Language check cycle started for ${result.targets} provider source${result.targets === 1 ? '' : 's'}. Results will appear here when complete.` : 'No eligible language sources are waiting to be checked.')
      qc.invalidateQueries({ queryKey: ['language-mismatch-report'] })
    },
    onError: (e: any) => notify(e?.response?.data?.detail ?? 'Could not start the language check cycle.'),
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
          <p className="text-xs text-muted-foreground mt-1">Embedded audio tags are compared with the configured wanted-language policy. Approved single-language results update the source metadata and archive the parent when the observed language is outside that policy. Reject records the decision and prevents automatic re-checking.</p>
          <p className="text-xs text-muted-foreground mt-1">Wanted playback languages: {report.data?.enabled_languages.join(', ') || 'none'}</p>
          {report.data?.trickle && <p className="text-xs text-muted-foreground mt-1">Monitoring is {report.data.trickle.enabled ? 'enabled' : 'disabled'}.</p>}
          {report.data?.trickle && <p className="text-xs text-muted-foreground mt-1">Trickle: {report.data.trickle.probes_per_cycle} probes every {report.data.trickle.interval_seconds}s · {report.data.trickle.checked_today}/{report.data.trickle.daily_max ?? 'no cap'} today · rotates across active providers</p>}
        </div>
        <span className="flex items-center gap-2">
          {report.data?.trickle && <button className={`flex items-center gap-1.5 border rounded px-2 py-1.5 text-xs hover:bg-accent disabled:opacity-50 ${report.data.trickle.enabled ? 'border-amber-500/40 text-amber-400' : 'border-emerald-500/40 text-emerald-400'}`} disabled={toggleEnabled.isPending} onClick={() => toggleEnabled.mutate(!report.data!.trickle!.enabled)}><Power size={12} /> {report.data.trickle.enabled ? 'Disable monitoring' : 'Enable monitoring'}</button>}
          <button className="flex items-center gap-1.5 border border-primary/40 text-primary rounded px-2 py-1.5 text-xs hover:bg-accent disabled:opacity-50" disabled={runNow.isPending} onClick={() => runNow.mutate()}><Languages size={12} className={runNow.isPending ? 'animate-pulse' : ''} /> Run one cycle now</button>
          <button className="flex items-center gap-1.5 border border-border rounded px-2 py-1.5 text-xs hover:bg-accent disabled:opacity-50" disabled={report.isFetching} onClick={() => report.refetch()}><RefreshCw size={12} className={report.isFetching ? 'animate-spin' : ''} /> Refresh</button>
        </span>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <div className="rounded-md border border-border bg-card px-3 py-2"><div className="text-[11px] text-muted-foreground">Eligible sources</div><div className="text-lg font-semibold">{report.data?.stats?.eligible.total.toLocaleString() ?? '—'}</div><div className="text-[11px] text-muted-foreground">Movies {report.data?.stats?.eligible.movies.toLocaleString() ?? '—'} · Series {report.data?.stats?.eligible.series.toLocaleString() ?? '—'}</div></div>
        <div className="rounded-md border border-border bg-card px-3 py-2"><div className="text-[11px] text-muted-foreground">Checked today</div><div className="text-lg font-semibold">{report.data?.trickle?.checked_today.toLocaleString() ?? '—'}</div><div className="text-[11px] text-muted-foreground">{report.data?.trickle?.daily_max == null ? 'No daily cap' : `${report.data.trickle.daily_max.toLocaleString()} daily limit`}</div></div>
        <div className="rounded-md border border-border bg-card px-3 py-2"><div className="text-[11px] text-muted-foreground">Pending review</div><div className="text-lg font-semibold">{report.data?.stats?.pending_review.toLocaleString() ?? '—'}</div><div className="text-[11px] text-muted-foreground">Waiting for a decision</div></div>
        <div className="rounded-md border border-border bg-card px-3 py-2"><div className="text-[11px] text-muted-foreground">Estimated pace</div><div className="text-lg font-semibold">{report.data?.trickle ? `${Math.round(report.data.trickle.probes_per_cycle * 3600 / report.data.trickle.interval_seconds).toLocaleString()}/hr` : '—'}</div><div className="text-[11px] text-muted-foreground">Eligible count drops as sources are checked</div></div>
      </div>

      <div className="rounded-md border border-border bg-card px-3 py-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs">Probes per cycle<input className="block mt-1 w-28 rounded border border-border bg-background px-2 py-1" type="number" min="1" max="100" value={form.probes_per_cycle} onChange={(e) => setForm({ ...form, probes_per_cycle: Number(e.target.value) })} /></label>
          <label className="text-xs">Seconds between cycles<input className="block mt-1 w-32 rounded border border-border bg-background px-2 py-1" type="number" min="60" max="3600" value={form.interval_seconds} onChange={(e) => setForm({ ...form, interval_seconds: Number(e.target.value) })} /></label>
          <label className="text-xs">Daily cap<input className="block mt-1 w-28 rounded border border-border bg-background px-2 py-1" type="number" min="1" placeholder="None" value={form.daily_limit} onChange={(e) => setForm({ ...form, daily_limit: e.target.value })} /></label>
          <button className="border border-primary/40 text-primary rounded px-2 py-1.5 text-xs hover:bg-accent disabled:opacity-50" disabled={saveSettings.isPending} onClick={() => saveSettings.mutate()}>Save pacing</button>
          <span className="text-[11px] text-muted-foreground">Leave Daily cap blank for no cap. Individual source errors are recorded while the sweep continues rotating across active providers.</span>
        </div>
      </div>

      {!!report.data?.stats?.provider_history.length && <><div className="overflow-x-auto border border-border rounded-md"><table className="w-full text-xs"><thead className="bg-card text-muted-foreground"><tr className="text-left"><th className="p-2">Provider</th><th className="p-2">Type</th><th className="p-2">Probes</th><th className="p-2">Not needed</th><th className="p-2">Needed review</th><th className="p-2">Outside wanted</th><th className="p-2">Wanted only</th><th className="p-2">Errors/deferred</th></tr></thead><tbody>{report.data.stats.provider_history.map((h) => <tr className="border-t border-border/60" key={`${h.provider}:${h.type}`}><td className="p-2">{h.provider}</td><td className="p-2 font-semibold">{h.type}</td><td className="p-2">{h.probes.toLocaleString()}</td><td className="p-2">{h.not_needed.toLocaleString()}</td><td className="p-2">{h.mismatches.toLocaleString()}</td><td className="p-2">{h.outside_wanted.toLocaleString()}</td><td className="p-2">{h.wanted_only.toLocaleString()}</td><td className="p-2">{h.errors.toLocaleString()}</td></tr>)}</tbody></table></div><p className="text-[11px] text-muted-foreground">Each row reconciles as: Probes = Not needed + Needed review + Errors/deferred. “Not needed” means the probe completed without finding a mismatch.</p></>}

      <div className="flex flex-wrap items-center gap-2 border border-border rounded-md bg-card px-3 py-2 text-xs">
        <span className="text-muted-foreground">{rows.length} pending mismatch{rows.length === 1 ? '' : 'es'}</span>
        <span className="text-muted-foreground">· {selected.size} selected</span>
        <button className="ml-auto border border-border rounded px-2 py-1 hover:bg-accent" onClick={() => setSelected(new Set(selectable))}>Select all approvable</button>
        <button className="border border-emerald-500/40 text-emerald-400 rounded px-2 py-1 hover:bg-emerald-500/10 disabled:opacity-50" disabled={decide.isPending || !selected.size} onClick={() => runBulk('approved')}>Approve selected</button>
        <button className="border border-amber-500/40 text-amber-400 rounded px-2 py-1 hover:bg-amber-500/10 disabled:opacity-50" disabled={decide.isPending || !selected.size} onClick={() => runBulk('rejected')}>Keep configured selected</button>
        <button className="border border-emerald-500/40 text-emerald-400 rounded px-2 py-1 hover:bg-emerald-500/10 disabled:opacity-50" disabled={decide.isPending || !rows.length} onClick={() => runBulk('approved', true)}>Approve all proposed</button>
        <button className="border border-amber-500/40 text-amber-400 rounded px-2 py-1 hover:bg-amber-500/10 disabled:opacity-50" disabled={decide.isPending || !rows.length} onClick={() => runBulk('rejected', true)}>Keep configured all</button>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1 border border-border/70 rounded-md bg-background/50 px-3 py-2 text-[11px] text-muted-foreground">
        <span><strong className="text-emerald-400">✓ Approve</strong> — apply the proposed observed language; archive the parent when it is outside the wanted-language policy.</span>
        <span><strong className="text-amber-400">× Keep configured / Ignore</strong> — leave the current language and catalog state unchanged; record the decision and do not recheck.</span>
        <span><strong className="text-foreground">Manual review</strong> — multiple or ambiguous audio tags; approval is disabled until the user decides.</span>
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
                <td className="p-2"><div className="font-medium flex items-center gap-1"><span className="mr-1 rounded border border-border px-1 text-[10px]">{row.kind === 'episode' ? 'S' : 'M'}</span>{row.title} {row.year ? `(${row.year})` : ''}<PlayButton url={buildPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, row.container_extension || 'mp4', credentials.data)} transcodedUrl={buildTranscodedPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, credentials.data)} hlsUrl={buildHlsPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, credentials.data)} title={`${row.title}${row.year ? ` (${row.year})` : ''}${row.kind === 'episode' ? ` S${row.season_number}E${row.episode_number}` : ''}`} /></div><div className="text-muted-foreground">{row.kind === 'episode' ? `S${row.season_number}E${row.episode_number} · ${row.episode_name ?? ''}` : 'Movie'}{row.tmdb_id ? ` · TMDB ${row.tmdb_id}` : ''}</div></td>
                <td className="p-2">{row.provider_name}</td>
                <td className="p-2">{languageLabel(row.configured_language)}</td>
                <td className="p-2">{row.observed_languages.map(languageLabel).join(', ')}</td>
                <td className="p-2">{disabled ? 'Manual review required' : <>{languageLabel(row.proposed_language)}{row.proposed_archive && <div className="text-amber-400">Then archive</div>}</>}</td>
                <td className="p-2 text-muted-foreground">{row.language_probed_at ? new Date(row.language_probed_at).toLocaleString() : '—'}</td>
                <td className="p-2"><span className="flex gap-1"><button title="Approve: apply the proposed language and any archive result" disabled={decide.isPending || disabled} className="p-1 rounded border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-40" onClick={() => decide.mutate({ row, decision: 'approved' })}><Check size={13} /></button><button title="Keep configured language and ignore this result; do not re-check" disabled={decide.isPending} className="p-1 rounded border border-amber-500/40 text-amber-400 hover:bg-amber-500/10 disabled:opacity-40" onClick={() => decide.mutate({ row, decision: 'rejected' })}><X size={13} /></button></span></td>
              </tr>
            })}</tbody>
          </table>
        </div>
      )}
    </div>
  )
}
