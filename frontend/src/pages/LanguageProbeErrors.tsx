import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ArrowUp, ArrowUpDown, Check, Loader2, RefreshCw, RotateCcw, Trash2 } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { notify } from '@/lib/confirm'
import { buildHlsPreviewSourceUrl, buildPreviewSourceUrl, buildTranscodedPreviewSourceUrl, PlayButton, type XcCredentials } from './VodManager'

type ProbeError = {
  kind: 'movie' | 'episode'
  source_id: number
  item_id: number
  title: string
  year: number | null
  provider_name: string
  configured_language: string | null
  category: string | null
  container_extension: string | null
  reason: string
  attempts: number
  quarantined: boolean
  last_failed_at: string | null
}

type Report = { errors?: ProbeError[] }

export default function LanguageProbeErrors() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [showTop, setShowTop] = useState(false)
  const report = useQuery<Report>({
    queryKey: ['language-mismatch-report'],
    queryFn: () => api.get('/vod/language-mismatch-report/').then((r) => r.data),
    refetchInterval: 30_000,
  })
  const credentials = useQuery<XcCredentials>({ queryKey: ['vod-xc-credentials'], queryFn: () => api.get('/vod/xc-credentials/').then((r) => r.data), retry: false })
  const action = useMutation({
    mutationFn: ({ row, value }: { row: ProbeError; value: 'approve' | 'retry' | 'delete' }) => api.post(`/vod/language-probe-errors/${row.kind}/${row.source_id}/action/`, { action: value }).then((r) => r.data),
    onSuccess: (result) => {
      notify(result.action === 'deleted' ? 'Source deleted.' : result.action === 'approved' ? 'Manual review approved; source marked checked.' : 'Source returned to the probe queue.')
      qc.invalidateQueries({ queryKey: ['language-mismatch-report'] })
    },
    onError: (e: any) => notify(e?.response?.data?.detail ?? 'Could not update the probe issue.'),
  })
  const errors = report.data?.errors ?? []
  const deferred = errors.filter((row) => !row.quarantined)
  const quarantined = errors.filter((row) => row.quarantined)
  const rowKey = (row: ProbeError) => `${row.kind}:${row.source_id}`
  const sortedErrors = useMemo(() => [...errors].sort((a, b) => {
    const result = a.provider_name.localeCompare(b.provider_name, undefined, { sensitivity: 'base' }) || a.title.localeCompare(b.title, undefined, { sensitivity: 'base' })
    return sortDirection === 'asc' ? result : -result
  }), [errors, sortDirection])
  const sortedDeferred = sortedErrors.filter((row) => !row.quarantined)
  const sortedQuarantined = sortedErrors.filter((row) => row.quarantined)
  useEffect(() => setSelected((old) => new Set([...old].filter((id) => errors.some((row) => rowKey(row) === id)))), [errors])
  useEffect(() => {
    const onScroll = () => {
      const max = Math.max(0, document.documentElement.scrollHeight - window.innerHeight)
      setShowTop(window.scrollY > Math.max(240, max * 0.3))
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  const play = (row: ProbeError) => <PlayButton url={buildPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, row.container_extension || 'mp4', credentials.data)} transcodedUrl={buildTranscodedPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, credentials.data)} hlsUrl={buildHlsPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, credentials.data)} title={`${row.title}${row.year ? ` (${row.year})` : ''}`} />
  const bulkAction = async (value: 'approve' | 'retry' | 'delete') => {
    const targets = errors.filter((row) => selected.has(rowKey(row)))
    if (!targets.length) { notify('No probe issues are selected.'); return }
    if (value === 'delete' && !window.confirm(`Delete ${targets.length} selected source${targets.length === 1 ? '' : 's'}? This cannot be undone.`)) return
    for (const row of targets) await action.mutateAsync({ row, value })
    setSelected(new Set())
  }
  const rows = (items: ProbeError[], locked: boolean) => items.map((row) => <tr className="border-t border-border/60 align-top" key={`${row.kind}:${row.source_id}`}>
    <td className="p-2"><input type="checkbox" aria-label={`Select ${row.title}`} checked={selected.has(rowKey(row))} onChange={(e) => setSelected((old) => { const next = new Set(old); e.target.checked ? next.add(rowKey(row)) : next.delete(rowKey(row)); return next })} /></td>
    <td className="p-2 text-white"><div className="font-medium flex items-center gap-1"><span className="mr-1 rounded border border-border px-1 text-[10px] text-white">{row.kind === 'episode' ? 'S' : 'M'}</span>{row.title}{row.year ? ` (${row.year})` : ''}{play(row)}</div><div className="text-[11px] text-white">{row.kind === 'episode' ? 'Episode source' : 'Movie source'}</div></td>
    <td className="p-2">{row.provider_name}</td><td className="p-2">{row.configured_language || 'Unknown'}</td><td className="p-2">{row.category || '—'}</td><td className="p-2">{row.attempts}</td><td className="p-2 max-w-md break-words text-amber-300">{row.reason}</td>
    <td className="p-2"><span className="flex gap-1"><button title="Approve after manual playback review" disabled={action.isPending} className="p-1 rounded border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-40" onClick={() => action.mutate({ row, value: 'approve' })}><Check size={13} /></button><button title="Retry this source" disabled={action.isPending} className="p-1 rounded border border-primary/40 text-primary hover:bg-accent disabled:opacity-40" onClick={() => action.mutate({ row, value: 'retry' })}><RotateCcw size={13} /></button><button title="Delete this source" disabled={action.isPending} className="p-1 rounded border border-red-500/40 text-red-400 hover:bg-red-500/10 disabled:opacity-40" onClick={() => window.confirm(`Delete the ${row.provider_name} source for ${row.title}? This cannot be undone.`) && action.mutate({ row, value: 'delete' })}><Trash2 size={13} /></button></span>{locked && <div className="text-[10px] text-red-300 mt-1">Review required</div>}</td>
  </tr>)
  const table = (items: ProbeError[], locked: boolean) => items.length ? <div className="overflow-x-auto border border-border rounded-md"><table className="w-full text-xs text-white"><thead className="bg-card text-white"><tr className="text-left"><th className="p-2 w-8"></th><th className="p-2">Title / play</th><th className="p-2"><button className="inline-flex items-center gap-1 hover:text-white" onClick={() => setSortDirection((old) => old === 'asc' ? 'desc' : 'asc')}>Provider <ArrowUpDown size={12} /></button><ArrowUp size={12} className={`inline ml-1 ${sortDirection === 'desc' ? 'rotate-180' : ''}`} /></th><th className="p-2">Configured</th><th className="p-2">Category</th><th className="p-2">Attempts</th><th className="p-2">Reason</th><th className="p-2">Actions</th></tr></thead><tbody>{rows(items, locked)}</tbody></table></div> : <div className="border border-border rounded-md bg-card p-6 text-center text-sm text-white">Nothing in this section.</div>

  if (report.isLoading) return <div className="flex items-center gap-2 text-white"><Loader2 size={15} className="animate-spin" /> Loading probe issues…</div>
  if (report.isError) return <div className="text-destructive">Could not load language probe issues.</div>
  return <div className="space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-lg font-semibold text-white">Language Probe Issues</h1><p className="text-xs text-white mt-1">Deferred sources stay in rotation after their first provider failure. Two provider failures quarantine a source from automatic probing and normal playback until you decide what to do.</p></div><span className="flex gap-2"><button className="flex items-center gap-1.5 border border-border rounded px-2 py-1.5 text-xs text-white hover:bg-accent" onClick={() => window.dispatchEvent(new CustomEvent('vodmanager-goto', { detail: 'language-report' }))}><ArrowLeft size={13} /> Mismatch report</button><button className="flex items-center gap-1.5 border border-border rounded px-2 py-1.5 text-xs text-white hover:bg-accent disabled:opacity-50" disabled={report.isFetching} onClick={() => report.refetch()}><RefreshCw size={13} className={report.isFetching ? 'animate-spin' : ''} /> Refresh</button></span></div>
    <div className="grid gap-3 md:grid-cols-3"><div className="rounded-md border border-border bg-card px-3 py-2 text-white"><div className="text-[11px] text-white">Deferred</div><div className="text-lg font-semibold">{deferred.length.toLocaleString()}</div><div className="text-[11px] text-white">First provider failure; still rotates</div></div><div className="rounded-md border border-amber-500/30 bg-card px-3 py-2 text-white"><div className="text-[11px] text-white">Quarantined</div><div className="text-lg font-semibold text-amber-300">{quarantined.length.toLocaleString()}</div><div className="text-[11px] text-white">Two failures; review required</div></div><div className="rounded-md border border-border bg-card px-3 py-2 text-white"><div className="text-[11px] text-white">Total issues</div><div className="text-lg font-semibold">{errors.length.toLocaleString()}</div><div className="text-[11px] text-white">Play, approve, retry, or delete</div></div></div>
    <div className="flex flex-wrap items-center gap-2 border border-border rounded-md bg-card px-3 py-2 text-xs text-white"><span>{selected.size} selected</span><button className="ml-auto border border-border rounded px-2 py-1 hover:bg-accent" onClick={() => setSelected((old) => old.size === errors.length ? new Set() : new Set(errors.map((row) => rowKey(row))))}>{selected.size === errors.length && errors.length ? 'Clear selection' : 'Select all on page'}</button><button className="border border-emerald-500/40 text-emerald-400 rounded px-2 py-1 hover:bg-emerald-500/10 disabled:opacity-50" disabled={action.isPending || !selected.size} onClick={() => bulkAction('approve')}>Approve selected</button><button className="border border-primary/40 text-primary rounded px-2 py-1 hover:bg-accent disabled:opacity-50" disabled={action.isPending || !selected.size} onClick={() => bulkAction('retry')}>Retry selected</button><button className="border border-red-500/40 text-red-400 rounded px-2 py-1 hover:bg-red-500/10 disabled:opacity-50" disabled={action.isPending || !selected.size} onClick={() => bulkAction('delete')}>Delete selected</button></div>
    <section className="space-y-2"><div><h2 className="text-sm font-semibold text-white">Deferred sources</h2><p className="text-[11px] text-white">These sources have failed once and remain eligible. Approve after playback review to mark them checked, retry them, or delete them.</p></div>{table(sortedDeferred, false)}</section>
    <section className="space-y-2"><div><h2 className="text-sm font-semibold text-amber-300">Quarantined sources</h2><p className="text-[11px] text-white">These sources failed twice and are excluded from automatic probing and normal playback. Manual review is required.</p></div>{table(sortedQuarantined, true)}</section>
    {showTop && <button aria-label="Return to top" title="Return to top" className="fixed bottom-5 right-5 z-20 rounded-full border border-primary/50 bg-card p-3 text-primary shadow-lg hover:bg-accent" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}><ArrowUp size={17} /></button>}
  </div>
}
