// KNM FORK ONLY - NEVER SEND UPSTREAM
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Ban, CircleAlert, Download, Loader2, Plus, RotateCcw, Trash2, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { inputCls, SectionCard, StatusPill } from '@/components/dvr-shared'
import api from '@/lib/api'
import { askConfirm, ConfirmDialogHost, NotifyDialogHost, notify } from '@/lib/confirm'

interface Entry { server_id: number; user_id: number; username: string | null; allowed: boolean; daily_cap: number | null }
interface Allowlist { default_cap: number; entries: Entry[] }
interface Req {
  id: number; kind: string; title: string; year: number | null; status: string; label: string
  progress: number; episodes_total: number; episodes_ready: number; created_at: number
  username?: string | null; user_id?: number; server_id?: number; detail?: string | null
}
interface Requests { requests: Req[]; counts: Record<string, number> }
interface FailedNotice { id: number; request_id: number; title: string; username: string | null; created_at: number; detail: string | null }
interface Connection { id: number; label: string; url: string }

const STATUSES = ['queued', 'downloading', 'delayed', 'processing', 'ready', 'failed', 'cancelled']
const TONE: Record<string, 'success' | 'warning' | 'destructive' | 'info'> = {
  ready: 'success', failed: 'destructive', delayed: 'warning', cancelled: 'warning',
  queued: 'info', downloading: 'info', processing: 'info',
}
const errMsg = (e: any, fallback: string) => e?.response?.data?.detail ?? fallback
const when = (t: number) => new Date(t * 1000).toLocaleString()

type DirUser = { server_id: number; server_name: string; user_id: number; username: string; user_level: number | null; on_allowlist: boolean }
type DirServer = { server_id: number; server_name: string; users: DirUser[]; error: string | null }

export default function KnmDownloads() {
  const qc = useQueryClient()
  const [filter, setFilter] = useState('')
  const [defaultCap, setDefaultCap] = useState<string>('')
  const [newServer, setNewServer] = useState('')
  const [newUserId, setNewUserId] = useState('')
  const [userSearch, setUserSearch] = useState('')
  const [newCap, setNewCap] = useState('')
  const [caps, setCaps] = useState<Record<string, string>>({})

  const allowlist = useQuery<Allowlist>({
    queryKey: ['knm-allowlist'],
    queryFn: () => api.get('/knm/admin/allowlist').then((r) => { setDefaultCap(String(r.data.default_cap)); return r.data }),
  })
  const connections = useQuery<Connection[]>({
    queryKey: ['knm-connections'],
    queryFn: () => api.get('/vod/dispatcharr-connections/').then((r) => r.data),
  })
  const dirUsers = useQuery<{ servers: DirServer[] }>({
    queryKey: ['knm-dir-users'],
    queryFn: () => api.get('/knm/admin/users').then((r) => r.data),
  })
  const requests = useQuery<Requests>({
    queryKey: ['knm-requests', filter],
    queryFn: () => api.get('/knm/admin/requests', { params: filter ? { status: filter } : undefined }).then((r) => r.data),
    refetchInterval: 10_000,
  })
  const failed = useQuery<{ notices: FailedNotice[] }>({
    queryKey: ['knm-failed-notices'],
    queryFn: () => api.get('/knm/admin/notices').then((r) => r.data),
    refetchInterval: 10_000,
  })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['knm-allowlist'] })
    qc.invalidateQueries({ queryKey: ['knm-dir-users'] })
    qc.invalidateQueries({ queryKey: ['knm-requests'] })
    qc.invalidateQueries({ queryKey: ['knm-failed-notices'] })
  }

  const saveAllow = useMutation({
    mutationFn: (body: { default_cap?: number; entries?: Entry[] }) => api.put('/knm/admin/allowlist', body).then((r) => r.data),
    onSuccess: refresh,
    onError: (e) => notify(errMsg(e, 'Could not save the allow-list.')),
  })
  const removeEntry = useMutation({
    mutationFn: (e: Entry) => api.delete(`/knm/admin/allowlist/${e.server_id}/${e.user_id}`).then((r) => r.data),
    onSuccess: refresh,
    onError: (e) => notify(errMsg(e, 'Could not remove that user.')),
  })
  const act = useMutation({
    mutationFn: ({ id, what }: { id: number; what: 'retry' | 'cancel' }) => api.post(`/knm/admin/requests/${id}/${what}`).then((r) => r.data),
    onSuccess: refresh,
    onError: (e) => notify(errMsg(e, 'That did not work.')),
  })
  const clearNotices = useMutation({
    mutationFn: () => api.post('/knm/admin/notices/clear').then((r) => r.data),
    onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ['vod-notices'] }) },
    onError: (e) => notify(errMsg(e, 'Could not clear the notices.')),
  })

  const capValue = (raw: string) => (raw.trim() === '' ? null : Math.max(0, parseInt(raw, 10) || 0))
  const dirServers = dirUsers.data?.servers ?? []
  const serverId = parseInt(newServer || String(dirServers[0]?.server_id ?? connections.data?.[0]?.id ?? ''), 10)
  const curServer = dirServers.find((s) => s.server_id === serverId)
  const pickable = (curServer?.users ?? []).filter((u) => !u.on_allowlist
    && u.username.toLowerCase().includes(userSearch.trim().toLowerCase()))
  const levelLabel = (l?: number | null) => (l === 10 ? 'admin' : l == null ? '' : `level ${l}`)
  const addUser = () => {
    const user = pickable.find((u) => u.user_id === parseInt(newUserId, 10))
    if (!serverId || !user) { notify('Pick a server and a user from the list.'); return }
    saveAllow.mutate({ entries: [{ server_id: serverId, user_id: user.user_id, username: user.username, allowed: true, daily_cap: capValue(newCap) }] }, {
      onSuccess: () => { setNewUserId(''); setUserSearch(''); setNewCap(''); qc.invalidateQueries({ queryKey: ['knm-dir-users'] }) },
    })
  }
  const connLabel = (id?: number) => connections.data?.find((c) => c.id === id)?.label ?? `#${id}`
  const entries = allowlist.data?.entries ?? []
  const counts = requests.data?.counts ?? {}
  const failedNotices = failed.data?.notices ?? []

  return (
    <div className="space-y-4 max-w-6xl">
      <div>
        <h1 className="text-xl font-semibold flex items-center gap-2"><Download size={18} /> KNM Downloads</h1>
        <p className="text-sm text-muted-foreground mt-1">Who may request downloads from the KNM Media app, and what they have asked for.</p>
      </div>

      {failedNotices.length > 0 && (
        <div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2 font-semibold text-destructive"><CircleAlert size={15} /> {failedNotices.length} failed download{failedNotices.length === 1 ? '' : 's'} need attention</span>
            <Button size="sm" variant="outline" disabled={clearNotices.isPending} onClick={() => clearNotices.mutate()}>Clear all</Button>
          </div>
          <ul className="mt-2 space-y-1">
            {failedNotices.map((n) => (
              <li key={n.id}><span className="font-medium">{n.title}</span> for {n.username ?? 'unknown'}, {when(n.created_at)}{n.detail ? <span className="text-muted-foreground"> ({n.detail})</span> : null}</li>
            ))}
          </ul>
        </div>
      )}

      <SectionCard title="Allow-list" icon={<Users size={15} />} description="Downloads are off for everyone not listed here. Admins are always allowed.">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <label className="text-sm">Default daily cap</label>
          <input className={inputCls('w-20')} type="number" min={0} value={defaultCap} onChange={(e) => setDefaultCap(e.target.value)} />
          <Button size="sm" disabled={saveAllow.isPending || defaultCap === ''} onClick={() => saveAllow.mutate({ default_cap: Math.max(0, parseInt(defaultCap, 10) || 0) })}>Save</Button>
          <span className="text-xs text-muted-foreground">titles per person per day (UTC), unless the person has their own cap</span>
        </div>
        <div className="overflow-auto border border-border rounded">
          <table className="w-full text-sm">
            <thead><tr className="text-left"><th className="px-2 py-1">User</th><th className="px-2 py-1">Server</th><th className="px-2 py-1">Allowed</th><th className="px-2 py-1">Daily cap</th><th className="px-2 py-1" /></tr></thead>
            <tbody>
              {entries.map((e) => {
                const k = `${e.server_id}-${e.user_id}`
                const capText = caps[k] ?? (e.daily_cap == null ? '' : String(e.daily_cap))
                return (
                  <tr key={k} className="border-t border-border">
                    <td className="px-2 py-1">{e.username || '(no name)'} <span className="text-muted-foreground">id {e.user_id}</span></td>
                    <td className="px-2 py-1">{connLabel(e.server_id)}</td>
                    <td className="px-2 py-1"><input type="checkbox" checked={e.allowed} onChange={(ev) => saveAllow.mutate({ entries: [{ ...e, allowed: ev.target.checked }] })} /></td>
                    <td className="px-2 py-1">
                      <input className={inputCls('w-20')} type="number" min={0} placeholder="default" value={capText}
                        onChange={(ev) => setCaps({ ...caps, [k]: ev.target.value })}
                        onBlur={() => { if (k in caps) { saveAllow.mutate({ entries: [{ ...e, daily_cap: capValue(caps[k]) }] }); const c = { ...caps }; delete c[k]; setCaps(c) } }} />
                    </td>
                    <td className="px-2 py-1 text-right">
                      <Button size="sm" variant="ghost" title="Remove" onClick={() => askConfirm(`Remove ${e.username || e.user_id} from the allow-list?`, () => removeEntry.mutate(e), 'Remove')}><Trash2 size={14} /></Button>
                    </td>
                  </tr>
                )
              })}
              {!entries.length && <tr><td className="px-2 py-3 text-muted-foreground" colSpan={5}>Nobody is on the allow-list yet.</td></tr>}
            </tbody>
          </table>
        </div>
        {curServer?.error && <p className="text-xs text-red-500 mt-3">{curServer.server_name}: {curServer.error}</p>}
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <select className={inputCls()} value={String(serverId || '')} onChange={(e) => { setNewServer(e.target.value); setNewUserId('') }}>
            {(dirServers.length ? dirServers.map((d) => ({ id: d.server_id, label: d.server_name })) : (connections.data ?? [])).map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
          <input className={inputCls('w-32')} placeholder="Search users" value={userSearch} onChange={(e) => setUserSearch(e.target.value)} />
          <select className={inputCls('w-56')} value={newUserId} onChange={(e) => setNewUserId(e.target.value)}>
            <option value="">{dirUsers.isLoading ? 'Loading users...' : 'Select a user'}</option>
            {pickable.map((u) => <option key={u.user_id} value={u.user_id}>{u.username}{levelLabel(u.user_level) ? ` (${levelLabel(u.user_level)})` : ''}</option>)}
          </select>
          <input className={inputCls('w-24')} type="number" min={0} placeholder="Cap" value={newCap} onChange={(e) => setNewCap(e.target.value)} />
          <Button size="sm" disabled={saveAllow.isPending} onClick={addUser}><Plus size={14} /> Add user</Button>
        </div>
      </SectionCard>

      <SectionCard title="Requests" icon={<Download size={15} />} description="Everything people have asked for, newest first.">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <button className={`px-2 py-1 rounded text-xs border ${filter === '' ? 'bg-primary text-primary-foreground' : 'border-border'}`} onClick={() => setFilter('')}>All</button>
          {STATUSES.map((s) => (
            <button key={s} className={`px-2 py-1 rounded text-xs border ${filter === s ? 'bg-primary text-primary-foreground' : 'border-border'}`} onClick={() => setFilter(s)}>
              {s} {counts[s] ? `(${counts[s]})` : ''}
            </button>
          ))}
          {requests.isFetching && <Loader2 size={14} className="animate-spin text-muted-foreground" />}
        </div>
        <div className="overflow-auto border border-border rounded">
          <table className="w-full text-sm">
            <thead><tr className="text-left"><th className="px-2 py-1">Title</th><th className="px-2 py-1">User</th><th className="px-2 py-1">Status</th><th className="px-2 py-1">Progress</th><th className="px-2 py-1">Requested</th><th className="px-2 py-1" /></tr></thead>
            <tbody>
              {(requests.data?.requests ?? []).map((r) => (
                <tr key={r.id} className={`border-t border-border ${r.status === 'failed' ? 'bg-destructive/10' : ''}`}>
                  <td className="px-2 py-1">
                    <div className="font-medium">{r.title}{r.year ? ` (${r.year})` : ''}</div>
                    <div className="text-xs text-muted-foreground">{r.kind}{r.kind === 'show' ? `, ${r.episodes_ready}/${r.episodes_total} episodes` : ''}</div>
                    {r.status === 'failed' && r.detail && <div className="text-xs text-destructive mt-0.5">{r.detail}</div>}
                  </td>
                  <td className="px-2 py-1">{r.username || r.user_id} <span className="text-xs text-muted-foreground">{connLabel(r.server_id)}</span></td>
                  <td className="px-2 py-1"><StatusPill label={r.label} tone={TONE[r.status] ?? 'info'} /></td>
                  <td className="px-2 py-1">{Math.round(r.progress * 100)}%</td>
                  <td className="px-2 py-1 whitespace-nowrap">{when(r.created_at)}</td>
                  <td className="px-2 py-1 text-right whitespace-nowrap">
                    {(r.status === 'failed' || r.status === 'cancelled' || r.status === 'processing') && (
                      <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => act.mutate({ id: r.id, what: 'retry' })}><RotateCcw size={13} /> Retry</Button>
                    )}{' '}
                    {['queued', 'downloading', 'delayed'].includes(r.status) && (
                      <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => askConfirm(`Cancel the download of ${r.title}?`, () => act.mutate({ id: r.id, what: 'cancel' }), 'Cancel download')}><Ban size={13} /> Cancel</Button>
                    )}
                  </td>
                </tr>
              ))}
              {!requests.data?.requests.length && <tr><td className="px-2 py-3 text-muted-foreground" colSpan={6}>No requests{filter ? ` with status ${filter}` : ''}.</td></tr>}
            </tbody>
          </table>
        </div>
      </SectionCard>
      <ConfirmDialogHost />
      <NotifyDialogHost />
    </div>
  )
}
