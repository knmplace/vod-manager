import { useEffect, useMemo, useState } from 'react'
import { Archive, ArrowLeft, Check, Loader2, RefreshCw, RotateCcw, Trash2 } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { notify } from '@/lib/confirm'
import { buildHlsPreviewSourceUrl, buildPreviewSourceUrl, buildTranscodedPreviewSourceUrl, PlayButton, type XcCredentials } from './VodManager'

type UnknownRow = { kind: 'movie' | 'episode'; source_id: number; item_id: number; title: string; year: number | null; provider_name: string; configured_language: string | null; observed_languages: string[]; container_extension: string | null; language_probed_at: string | null; season_number?: number; episode_number?: number; episode_name?: string | null }
type UnknownReport = { results: UnknownRow[]; count: number; provider_counts: Record<string, number>; enabled_languages: string[]; primary_language: string }
type ActionValue = 'approve' | 'retry' | 'delete'

export default function LanguageUnknowns() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [selectionAnchor, setSelectionAnchor] = useState<string | null>(null)
  const [provider, setProvider] = useState('')
  const [sort, setSort] = useState<'checked' | 'title' | 'provider'>('checked')
  const [rowLanguages, setRowLanguages] = useState<Record<string, string>>({})
  const [bulkLanguage, setBulkLanguage] = useState('')
  const [batchSize, setBatchSize] = useState(600)
  const settings = useQuery<{ language_trickle_enabled: boolean }>({ queryKey: ['language-trickle-settings'], queryFn: () => api.get('/vod/language-trickle/settings/').then((r) => r.data) })
  const report = useQuery<UnknownReport>({ queryKey: ['language-unknown-report', provider], queryFn: () => api.get('/vod/language-unknown-report/', { params: provider ? { provider } : undefined }).then((r) => r.data), refetchInterval: () => settings.data?.language_trickle_enabled ? 30_000 : false })
  const credentials = useQuery<XcCredentials>({ queryKey: ['vod-xc-credentials'], queryFn: () => api.get('/vod/xc-credentials/').then((r) => r.data), retry: false })
  const action = useMutation({
    mutationFn: ({ row, value, language }: { row: UnknownRow; value: ActionValue; language?: string }) => api.post(`/vod/language-probe-errors/${row.kind}/${row.source_id}/action/`, { action: value, ...(language ? { language } : {}) }).then((r) => r.data),
    onSuccess: (result) => { notify(result.action === 'deleted' ? 'Source deleted.' : result.action === 'approved' ? `${result.language || 'Language'} recorded as confirmed. This source will not be scanned again.` : 'Source returned to the probe queue.'); qc.invalidateQueries({ queryKey: ['language-unknown-report'] }); qc.invalidateQueries({ queryKey: ['language-mismatch-report'] }) },
    onError: (e: any) => notify(e?.response?.data?.detail ?? 'Could not update the unknown-language source.'),
  })
  const bulkApproval = useMutation({
    mutationFn: ({ sources, language }: { sources: { kind: UnknownRow['kind']; source_id: number }[]; language: string; selectedKeys: string[]; selectedCount: number }) =>
      api.post('/vod/language-probe-errors/bulk-approve/', { sources, language }).then((r) => r.data),
    onSuccess: (result, variables) => {
      const remaining = Math.max(0, variables.selectedCount - result.count)
      notify(`${result.count} source${result.count === 1 ? '' : 's'} confirmed as ${result.language}.${remaining ? ` ${remaining} selected source${remaining === 1 ? '' : 's'} remain for the next batch.` : ''}`)
      setSelected((old) => {
        const next = new Set(old)
        variables.selectedKeys.forEach((selectedKey) => next.delete(selectedKey))
        return next
      })
      setSelectionAnchor(null)
      qc.invalidateQueries({ queryKey: ['language-unknown-report'] })
      qc.invalidateQueries({ queryKey: ['language-mismatch-report'] })
    },
    onError: (e: any) => notify(e?.response?.data?.detail ?? 'Could not confirm the selected sources.'),
  })
  const archiveParents = useMutation({
    mutationFn: ({ items }: { items: { kind: UnknownRow['kind']; item_id: number }[]; selectedKeys: string[]; selectedCount: number }) =>
      api.post('/vod/language-probe-errors/bulk-archive/', { items }).then((r) => r.data),
    onSuccess: (result, variables) => {
      const remaining = Math.max(0, variables.selectedCount - result.count)
      notify(`${result.count} parent item${result.count === 1 ? '' : 's'} archived. Source records were kept.${remaining ? ` ${remaining} selected parent item${remaining === 1 ? '' : 's'} remain for the next batch.` : ''}`)
      setSelected((old) => {
        const next = new Set(old)
        variables.selectedKeys.forEach((selectedKey) => next.delete(selectedKey))
        return next
      })
      setSelectionAnchor(null)
      qc.invalidateQueries({ queryKey: ['language-unknown-report'] })
      qc.invalidateQueries({ queryKey: ['language-mismatch-report'] })
      qc.invalidateQueries({ queryKey: ['vod-notices'] })
    },
    onError: (e: any) => notify(e?.response?.data?.detail ?? 'Could not archive the selected parent items.'),
  })
  const rows = report.data?.results ?? []
  const enabledLanguages = report.data?.enabled_languages ?? []
  const primaryLanguage = report.data?.primary_language ?? enabledLanguages[0] ?? ''
  useEffect(() => { if (primaryLanguage && !bulkLanguage) setBulkLanguage(primaryLanguage) }, [primaryLanguage, bulkLanguage])
  const visible = useMemo(() => [...rows].filter((row) => !provider || row.provider_name === provider).sort((a, b) => sort === 'title' ? a.title.localeCompare(b.title) : sort === 'provider' ? a.provider_name.localeCompare(b.provider_name) : (b.language_probed_at || '').localeCompare(a.language_probed_at || '')), [rows, provider, sort])
  const key = (row: UnknownRow) => `${row.kind}:${row.source_id}`
  const selectedVisibleCount = visible.reduce((count, row) => count + (selected.has(key(row)) ? 1 : 0), 0)
  const selectedParentCount = new Set(visible.filter((row) => selected.has(key(row))).map((row) => `${row.kind}:${row.item_id}`)).size
  const pendingCount = provider ? report.data?.provider_counts?.[provider] ?? 0 : report.data?.count ?? rows.length
  const confirmBatchCount = Math.min(selectedVisibleCount, batchSize)
  const languageFor = (row: UnknownRow) => rowLanguages[key(row)] || (row.configured_language && enabledLanguages.includes(row.configured_language) ? row.configured_language : primaryLanguage)

  const toggleRowSelection = (row: UnknownRow, index: number, event: React.ChangeEvent<HTMLInputElement>) => {
    const id = key(row)
    const shiftKey = (event.nativeEvent as Event & { shiftKey?: boolean }).shiftKey === true
    setSelected((old) => {
      const next = new Set(old)
      const anchorIndex = shiftKey && selectionAnchor ? visible.findIndex((candidate) => key(candidate) === selectionAnchor) : -1
      if (anchorIndex >= 0) {
        for (let i = Math.min(anchorIndex, index); i <= Math.max(anchorIndex, index); i += 1) {
          const rangeId = key(visible[i])
          event.target.checked ? next.add(rangeId) : next.delete(rangeId)
        }
      } else if (event.target.checked) next.add(id)
      else next.delete(id)
      return next
    })
    setSelectionAnchor(id)
  }

  const run = (row: UnknownRow, value: ActionValue) => {
    const language = languageFor(row)
    const message = value === 'approve' ? `Record ${language} as the confirmed language for ${row.title}?\n\nThis saves the language choice, marks it validated, and stops future scans for this source. Nothing will be archived.` : value === 'retry' ? `Retry the language check for ${row.title}?` : `Delete the ${row.provider_name} source for ${row.title}? This cannot be undone.`
    if (value !== 'approve' || language) {
      if (window.confirm(message)) action.mutate({ row, value, ...(value === 'approve' ? { language } : {}) })
    } else notify('Enable at least one playback language before confirming a source.')
  }

  const bulk = (value: ActionValue) => {
    const targets = visible.filter((row) => selected.has(key(row)))
    if (!targets.length) { notify('No unknown-language sources are selected.'); return }
    if (value === 'approve' && !bulkLanguage) { notify('Choose an enabled language to confirm.'); return }
    if (value === 'approve') {
      const batch = targets.slice(0, batchSize)
      const remaining = targets.length - batch.length
      const message = `Record ${bulkLanguage} for the next ${batch.length} selected source${batch.length === 1 ? '' : 's'}?${remaining ? `\n\n${remaining} other selected source${remaining === 1 ? '' : 's'} will remain selected for the next batch.` : ''}\n\nThis saves the language choice, marks each source validated, and stops future scans for them. Nothing will be archived.`
      if (!window.confirm(message)) return
      bulkApproval.mutate({
        sources: batch.map(({ kind, source_id }) => ({ kind, source_id })),
        language: bulkLanguage,
        selectedKeys: batch.map(key),
        selectedCount: targets.length,
      })
      return
    }
    const message = value === 'retry' ? `Retry ${targets.length} selected language checks?` : `Delete ${targets.length} selected source${targets.length === 1 ? '' : 's'}? This cannot be undone.`
    if (!window.confirm(message)) return
    targets.reduce((promise, row) => promise.then(() => action.mutateAsync({ row, value })), Promise.resolve()).then(() => { setSelected(new Set()); setSelectionAnchor(null) })
  }

  const archiveSelected = () => {
    const targets = visible.filter((row) => selected.has(key(row)))
    const parents = [...new Map(targets.map((row) => [`${row.kind}:${row.item_id}`, { kind: row.kind, item_id: row.item_id }])).values()]
    if (!parents.length) { notify('No parent items are selected.'); return }
    const batch = parents.slice(0, batchSize)
    const batchParentKeys = new Set(batch.map((item) => `${item.kind}:${item.item_id}`))
    const selectedKeys = targets.filter((row) => batchParentKeys.has(`${row.kind}:${row.item_id}`)).map(key)
    const remaining = parents.length - batch.length
    const message = `Archive the next ${batch.length} selected parent item${batch.length === 1 ? '' : 's'}?${remaining ? `\n\n${remaining} selected parent item${remaining === 1 ? '' : 's'} will remain selected for the next batch.` : ''}\n\nTheir category placements will be removed. Provider sources and content records will be kept. Use Delete only when you intend to permanently remove a provider source.`
    if (window.confirm(message)) archiveParents.mutate({ items: batch, selectedKeys, selectedCount: parents.length })
  }

  const archiveOne = (row: UnknownRow) => {
    const message = `Archive ${row.title}${row.year ? ` (${row.year})` : ''}?\n\nIts category placements will be removed. Provider sources and content records will be kept. Use Delete only when you intend to permanently remove this provider source.`
    if (window.confirm(message)) archiveParents.mutate({ items: [{ kind: row.kind, item_id: row.item_id }], selectedKeys: rows.filter((candidate) => candidate.kind === row.kind && candidate.item_id === row.item_id && selected.has(key(candidate))).map(key), selectedCount: 1 })
  }

  if (report.isLoading) return <div className="flex items-center gap-2 text-muted-foreground"><Loader2 size={15} className="animate-spin" /> Loading unknown-language review…</div>
  if (report.isError) return <div className="text-destructive">Could not load unknown-language review.</div>
  return <div className="space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-lg font-semibold">Unknown Language Review</h1><p className="text-xs text-muted-foreground mt-1">Choose and confirm the language for files with no usable embedded language tag. Confirmed sources are recorded as validated and are not scanned again.</p></div><span className="flex gap-2"><button className="flex items-center gap-1.5 border border-border rounded px-2 py-1.5 text-xs hover:bg-accent" onClick={() => window.dispatchEvent(new CustomEvent('vodmanager-goto', { detail: 'language-report' }))}><ArrowLeft size={13} /> Mismatch report</button><button className="flex items-center gap-1.5 border border-border rounded px-2 py-1.5 text-xs" disabled={report.isFetching} onClick={() => report.refetch()}><RefreshCw size={12} /> Refresh</button></span></div>
    <div className="rounded-md border border-border bg-card px-3 py-2 text-xs text-white">To correct a missing or wrong language, use the “Confirm language / actions” selector on that row and choose the language you verified. {enabledLanguages.length === 1 ? `Confirming records ${enabledLanguages[0]} as its language, marks it validated, and prevents future scans.` : 'The selector offers enabled playback languages; the bulk selector above applies one language to all selected sources.'} Unknown results are never archived by this action.</div>
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs"><div><span>{visible.length.toLocaleString()} shown of {pendingCount.toLocaleString()} pending · {selectedVisibleCount} selected</span><div className="text-muted-foreground">Provider filtering is applied before loading up to 1,000 sources. Shift-click rows to select a range.</div></div><label className="flex items-center gap-2">Confirm/archive batch size<select aria-label="Maximum sources per confirm or archive batch" className="rounded border border-border bg-background px-2 py-1" value={batchSize} disabled={bulkApproval.isPending || archiveParents.isPending} onChange={(e) => setBatchSize(Number(e.target.value))}>{[50, 100, 200, 300, 400, 500, 600].map((size) => <option key={size} value={size}>{size}</option>)}</select></label></div>
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs"><span>{selectedVisibleCount} selected from {visible.length} shown</span><select aria-label="Filter by provider" className="ml-auto rounded border border-border bg-background px-2 py-1" value={provider} disabled={bulkApproval.isPending || archiveParents.isPending} onChange={(e) => { setProvider(e.target.value); setSelected(new Set()); setSelectionAnchor(null) }}><option value="">All providers</option>{Object.entries(report.data?.provider_counts ?? {}).sort(([a], [b]) => a.localeCompare(b)).map(([name, count]) => <option key={name} value={name}>{name} ({count.toLocaleString()})</option>)}</select><select className="rounded border border-border bg-background px-2 py-1" value={sort} disabled={bulkApproval.isPending || archiveParents.isPending} onChange={(e) => setSort(e.target.value as typeof sort)}><option value="checked">Newest checked</option><option value="title">Title</option><option value="provider">Provider</option></select><select aria-label="Language to confirm for selected sources" className="rounded border border-border bg-background px-2 py-1" value={bulkLanguage} disabled={enabledLanguages.length <= 1 || bulkApproval.isPending || archiveParents.isPending} onChange={(e) => setBulkLanguage(e.target.value)}>{enabledLanguages.map((code) => <option key={code} value={code}>{code}</option>)}</select><button className="border border-border rounded px-2 py-1 hover:bg-accent disabled:opacity-50" disabled={bulkApproval.isPending || archiveParents.isPending} onClick={() => { setSelected((old) => selectedVisibleCount === visible.length ? new Set([...old].filter((id) => !visible.some((row) => key(row) === id))) : new Set([...old, ...visible.map(key)])); setSelectionAnchor(null) }}>{selectedVisibleCount === visible.length && visible.length ? 'Clear selection' : 'Select all shown'}</button><button className="border border-emerald-500/40 text-emerald-400 rounded px-2 py-1 disabled:opacity-50" disabled={action.isPending || bulkApproval.isPending || archiveParents.isPending || !selectedVisibleCount || !bulkLanguage} onClick={() => bulk('approve')}>{bulkApproval.isPending ? 'Saving approvals…' : `Confirm next ${confirmBatchCount} as ${bulkLanguage || '—'}`}</button><button className="border border-primary/40 text-primary rounded px-2 py-1 disabled:opacity-50" disabled={action.isPending || bulkApproval.isPending || archiveParents.isPending || !selectedVisibleCount} onClick={() => bulk('retry')}>Retry selected</button><button className="border border-amber-500/40 text-amber-300 rounded px-2 py-1 disabled:opacity-50" disabled={action.isPending || bulkApproval.isPending || archiveParents.isPending || !selectedVisibleCount} onClick={archiveSelected}>{archiveParents.isPending ? 'Archiving…' : `Archive next ${Math.min(selectedParentCount, batchSize)} parents`}</button><button className="border border-red-500/40 text-red-400 rounded px-2 py-1 disabled:opacity-50" disabled={action.isPending || bulkApproval.isPending || archiveParents.isPending || !selectedVisibleCount} onClick={() => bulk('delete')}>Delete selected</button></div>
    {visible.length ? <div className="overflow-x-auto border border-border rounded-md"><table className="w-full table-fixed text-xs"><thead className="bg-card"><tr className="text-left"><th className="p-2 w-8"><input type="checkbox" aria-label="Select all shown unknown-language sources" disabled={bulkApproval.isPending} checked={visible.length > 0 && visible.every((row) => selected.has(key(row)))} onChange={(e) => { setSelected((old) => { const next = new Set(old); visible.forEach((row) => e.target.checked ? next.add(key(row)) : next.delete(key(row))); return next }); setSelectionAnchor(null) }} /></th><th className="p-2 w-[35%]">Title / play</th><th className="p-2 w-[15%]">Provider</th><th className="p-2 w-[12%]">Configured</th><th className="p-2 w-[10%]">Observed</th><th className="p-2 w-[20%]">Confirm language / actions</th></tr></thead><tbody>{visible.map((row, index) => <tr className="border-t border-border/60 align-top" key={key(row)}><td className="p-2"><input type="checkbox" aria-label={`Select ${row.title}`} disabled={bulkApproval.isPending} checked={selected.has(key(row))} onChange={(e) => toggleRowSelection(row, index, e)} /></td><td className="p-2"><div className="font-medium flex items-center gap-1"><span className="rounded border border-border px-1 text-[10px]">{row.kind === 'episode' ? 'S' : 'M'}</span>{row.title}{row.year ? ` (${row.year})` : ''}<PlayButton url={buildPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, row.container_extension || 'mp4', credentials.data)} transcodedUrl={buildTranscodedPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, credentials.data)} hlsUrl={buildHlsPreviewSourceUrl(row.kind === 'episode' ? 'series' : 'movie', row.source_id, credentials.data)} title={row.title} /></div><div className="text-[11px] text-muted-foreground">{row.kind === 'episode' ? `S${row.season_number}E${row.episode_number} · ${row.episode_name || ''}` : 'Movie'}</div></td><td className="p-2">{row.provider_name}</td><td className="p-2">{row.configured_language || 'Unknown'}</td><td className="p-2 text-amber-300">Unknown</td><td className="p-2"><div className="flex flex-wrap gap-1"><select aria-label={`Language to confirm for ${row.title}`} className="rounded border border-border bg-background px-1 py-1" value={languageFor(row)} disabled={enabledLanguages.length <= 1 || bulkApproval.isPending || archiveParents.isPending} onChange={(e) => setRowLanguages((old) => ({ ...old, [key(row)]: e.target.value }))}>{enabledLanguages.map((code) => <option key={code} value={code}>{code}</option>)}</select><button className="px-1.5 py-1 rounded border border-emerald-500/40 text-emerald-400" disabled={action.isPending || bulkApproval.isPending || archiveParents.isPending || !languageFor(row)} onClick={() => run(row, 'approve')}><Check size={13} /> Confirm {languageFor(row) || ''}</button><button className="px-1.5 py-1 rounded border border-primary/40 text-primary" disabled={action.isPending || bulkApproval.isPending || archiveParents.isPending} onClick={() => run(row, 'retry')}><RotateCcw size={13} /> Retry</button><button className="px-1.5 py-1 rounded border border-amber-500/40 text-amber-300" disabled={action.isPending || bulkApproval.isPending || archiveParents.isPending} onClick={() => archiveOne(row)}><Archive size={13} /> Archive</button><button className="px-1.5 py-1 rounded border border-red-500/40 text-red-400" disabled={action.isPending || bulkApproval.isPending || archiveParents.isPending} onClick={() => run(row, 'delete')}><Trash2 size={13} /> Delete</button></div></td></tr>)}</tbody></table></div> : <div className="border border-border rounded-md bg-card p-8 text-center text-sm text-muted-foreground">No unknown-language sources need review.</div>}
  </div>
}
