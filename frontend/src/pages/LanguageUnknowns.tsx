import { useMemo, useState } from 'react'
import { ArrowLeft, Check, Loader2, RefreshCw, RotateCcw, Trash2 } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { notify } from '@/lib/confirm'
import { buildHlsPreviewSourceUrl, buildPreviewSourceUrl, buildTranscodedPreviewSourceUrl, PlayButton, type XcCredentials } from './VodManager'

type UnknownRow = {
  kind: 'movie' | 'episode'
  source_id: number
  title: string
  year: number | null
  provider_name: string
  configured_language: string | null
  observed_languages: string[]
  container_extension: string | null
  language_probed_at: string | null
  season_number?: number
  episode_number?: number
  episode_name?: string | null
}

export default function LanguageUnknowns() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [provider, setProvider] = useState('')
  const [sort, setSort] = useState<'checked' | 'title' | 'provider'>('checked')
  const settings = useQuery<{ language_trickle_enabled: boolean }>({ queryKey: ['language-trickle-settings'], queryFn: () => api.get('/vod/language-trickle/settings/').then((r) => r.data) })
  const report = useQuery<{ results: UnknownRow[] }>({ queryKey: ['language-unknown-report'], queryFn: () => api.get('/vod/language-unknown-report/').then((r) => r.data), refetchInterval: () => settings.data?.language_trickle_enabled ? 30_000 : false })
  const credentials = useQuery<XcCredentials>({ queryKey: ['vod-xc-credentials'], queryFn: () => api.get('/vod/xc-credentials/').then((r) => r.data), retry: false })
  const action = useMutation({
    mutationFn: ({ row, value }: { row: UnknownRow; value: 'approve' | 'retry' | 'delete' }) => api.post(`/vod/language-probe-errors/${row.kind}/${row.source_id}/action/`, { action: value }).then((r) => r.data),
    onSuccess: (result) => { notify(result.action === 'deleted' ? 'Source deleted.' : result.action === 'approved' ? 'Current configured language confirmed; nothing was archived.' : 'Source returned to the probe queue.'); qc.invalidateQueries({ queryKey: ['language-unknown-report'] }); qc.invalidateQueries({ queryKey: ['language-mismatch-report'] }) },
    onError: (e: any) => notify(e?.response?.data?.detail ?? 'Could not update the unknown-language source.'),
  })
  const rows = report.data?.results ?? []
  const visible = useMemo(() => [...rows].filter((row) => !provider || row.provider_name === provider).sort((a, b) => sort === 'title' ? a.title.localeCompare(b.title) : sort === 'provider' ? a.provider_name.localeCompare(b.provider_name) : (b.language_probed_at || '').localeCompare(a.language_probed_at || '')), [rows, provider, sort])
  const key = (row: UnknownRow) => `${row.kind}:${row.source_id}`
  const run = (row: UnknownRow, value: 'approve' | 'retry' | 'delete') => {
    const message = value === 'approve' ? `Confirm the configured language (${row.configured_language || 'Unknown'}) for ${row.title}?\n\nThis marks the source reviewed and makes no archive or language change.` : value === 'retry' ? `Retry the language check for ${row.title}?` : `Delete the ${row.provider_name} source for ${row.title}? This cannot be undone.`
    if (window.confirm(message)) action.mutate({ row, value })
  }
  const bulk = (value: 'approve' | 'retry' | 'delete') => {
    const targets = visible.filter((row) => selected.has(key(row)))
    if (!targets.length) { notify('No unknown-language sources are selected.'); return }
    const message = value === 'approve' ? `Confirm the configured language for ${targets.length} selected source${targets.length === 1 ? '' : 's'}?\n\nSources will be marked reviewed. Nothing will be archived or relabeled.` : value === 'retry' ? `Retry ${targets.length} selected language checks?` : `Delete ${targets.length} selected source${targets.length === 1 ? '' : 's'}? This cannot be undone.`
    if (!window.confirm(message)) return
    targets.reduce((promise, row) => promise.then(() => action.mutateAsync({ row, value })), Promise.resolve()).then(() => setSelected(new Set()))
  }
  if (report.isLoading) return <div className="flex items-center gap-2 text-muted-foreground"><Loader2 size={15} className="animate-spin" /> Loading unknown-language review…</div>
  if (report.isError) return <div className="text-destructive">Could not load unknown-language review.</div>
  return <div className="space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-lg font-semibold">Unknown Language Review</h1><p className="text-xs text-muted-foreground mt-1">These files did not provide a usable embedded language tag. Unknown results never auto-archive and never change the source language.</p></div><span className="flex gap-2"><button className="flex items-center gap-1.5 border border-border rounded px-2 py-1.5 text-xs hover:bg-accent" onClick={() => window.dispatchEvent(new CustomEvent('vodmanager-goto', { detail: 'language-report' }))}><ArrowLeft size={13} /> Mismatch report</button><button className="flex items-center gap-1.5 border border-border rounded px-2 py-1.5 text-xs hover:bg-accent" disabled={report.isFetching} onClick={() => report.refetch()}><RefreshCw size={12} /> Refresh</button></span></div>
    <div className="rounded-md border border-amber-500/30 bg-card px-3 py-2 text-xs text-amber-200">Confirm current language marks a source reviewed after playback review. It does not archive the parent and does not relabel the source. Language correction is planned separately.</div>
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs"><span>{visible.length} shown · {selected.size} selected</span><select className="ml-auto rounded border border-border bg-background px-2 py-1" value={provider} onChange={(e) => setProvider(e.target.value)}><option value="">All providers</option>{[...new Set(rows.map((row) => row.provider_name))].sort().map((name) => <option key={name}>{name}</option>)}</select><select className="rounded border border-border bg-background px-2 py-1" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}><option value="checked">Newest checked</option><option value="title">Title</option><option value="provider">Provider</option></select><button className="border border-border rounded px-2 py-1 hover:bg-accent" onClick={() => setSelected((old) => old.size === visible.length ? new Set() : new Set(visible.map(key)))}>{selected.size === visible.length && visible.length ? 'Clear selection' : 'Select all shown'}</button><button className="border border-emerald-500/40 text-emerald-400 rounded px-2 py-1 hover:bg-emerald-500/10 disabled:opacity-50" disabled={action.isPending || !selected.size} onClick={() => bulk('approve')}>Confirm current selected</button><button className="border border-primary/40 text-primary rounded px-2 py-1 hover:bg-accent disabled:opacity-50" disabled={action.isPending || !selected.size} onClick={() => bulk('retry')}>Retry selected</button><button className="border border-red-500/40 text-red-400 rounded px-2 py-1 hover:bg-red-500/10 disabled:opacity-50" disabled={action.isPending || !selected.size} onClick={() => bulk('delete')}>Delete selected</button></div>
    {visible.length ? <div className="overflow-x-auto border border-border rounded-md"><table className="w-full table-fixed text-xs"><thead className="bg-card"><tr className="text-left"><th className="p-2 w-8"><input type="checkbox" checked={visible.length > 0 && visible.every((row) => selected.has(key(row)))} onChange={(e) => setSelected((old) => { const next = new Set(old); visible.forEach((row) => e.target.checked ? next.add(key(row)) : next.delete(key(row))); return next })} /></th><th className="p-2 w-[38%]">Title / play</th><th className="p-2 w-[17%]">Provider</th><th className="p-2 w-[13%]">Configured</th><th className="p-2 w-[14%]">Observed</th><th className="p-2 w-[18%]">Actions</th></tr></thead><tbody>{visible.map((row) => <tr className="border-t border-border/60 align-top" key={key(row)}><td className="p-2"><input type="checkbox" checked={selected.has(key(row))} onChange={(e) => setSelected((old) => { const next = new Set(old); e.target.checked ? next.add(key(row)) : next.delete(key(row)); return next })} /></td><td className="p-2"><div className="font-medium flex items-center gap-1"><span className="rounded border border-border px-1 text-[10px]">{row.kind === 'episode' ? 'S' : 'M'}</span>{row.title}{row.year ? ` (${row.year})` : ''}<PlayButton url={buildPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, row.container_extension || 'mp4', credentials.data)} transcodedUrl={buildTranscodedPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, credentials.data)} hlsUrl={buildHlsPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, credentials.data)} title={row.title} /></div><div className="text-[11px] text-muted-foreground">{row.kind === 'episode' ? `S${row.season_number}E${row.episode_number} · ${row.episode_name || ''}` : 'Movie'}</div></td><td className="p-2">{row.provider_name}</td><td className="p-2">{row.configured_language || 'Unknown'}</td><td className="p-2 text-amber-300">Unknown</td><td className="p-2"><span className="flex flex-wrap gap-1"><button className="px-1.5 py-1 rounded border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10" disabled={action.isPending} onClick={() => run(row, 'approve')}><Check size={13} /> Confirm current</button><button className="px-1.5 py-1 rounded border border-primary/40 text-primary hover:bg-accent" disabled={action.isPending} onClick={() => run(row, 'retry')}><RotateCcw size={13} /> Retry</button><button className="px-1.5 py-1 rounded border border-red-500/40 text-red-400 hover:bg-red-500/10" disabled={action.isPending} onClick={() => run(row, 'delete')}><Trash2 size={13} /> Delete</button></span></td></tr>)}</tbody></table></div> : <div className="border border-border rounded-md bg-card p-8 text-center text-sm text-muted-foreground">No unknown-language sources need review.</div>}
  </div>
}
