import {
  Check,
  CheckCircle2,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  SearchX,
  Smartphone,
  Trash2,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { useAgentLeaderboard, type AgentRow } from '@/modules/analytics/api'
import {
  enrollmentOf,
  freedGroupCount,
  useAgents,
  useRestoreAgents,
  type Agent,
  type Enrollment,
} from '@/modules/agents/api'
import { AgentModal } from '@/modules/agents/AgentModal'
import { useAuth } from '@/modules/auth/store'
import { AgentTable } from '@/modules/dashboard/components/AgentTable'
import { useGroupsTree } from '@/modules/groups/api'
import { EnrollmentModal } from '@/modules/groups/EnrollmentNotice'
import { ratingProgress } from '@/modules/surveys/api'
import { DeleteAgentsModal } from '@/modules/agents/DeleteAgentsModal'
import { ImportAllModal } from '@/modules/agents/ImportAllModal'
import { Page, PageHeader } from '@/shared/layout/Page'
import { cn, formatDuration, formatNumber, scoreTone, TONE_CLASS } from '@/shared/lib/utils'
import { Avatar, MiniBar, ScoreRing, TrendDelta } from '@/shared/ui/dataviz'
import {
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  Segmented,
  Skeleton,
} from '@/shared/ui/primitives'
import { SearchInput } from '@/shared/ui/SearchInput'

const DAYS = 30

/** Faollik filtri. Ishdan ketgan xodim izsiz yo'qolmasin — u alohida
 *  tanlov bilan topiladi, sukut bo'yicha esa ro'yxatda turaveradi.
 *
 *  `unenrolled` — botga raqamini yubormaganlar. Ular uchun guruhlar
 *  avtomatik biriktirilmaydi, ya'ni bu odamlar bo'yicha tizim jimgina
 *  ishlamay turadi. Shu sababli ular alohida topiladigan bo'lishi kerak. */
type StatusFilter = 'all' | 'active' | 'inactive' | 'unenrolled' | 'archived'

export function AgentsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { can } = useAuth()

  const [view, setView] = useState<'cards' | 'table'>('cards')
  const [editing, setEditing] = useState<Agent | 'new' | null>(null)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  /** Faolsizlantirish natijasi — guruhlar bo'shagani jimgina o'tmasin */
  const [freed, setFreed] = useState<{ name: string; count: number } | null>(null)
  const [enrollHelp, setEnrollHelp] = useState(false)

  const canManage = can('agents:write')
  /* O'chirish — FAQAT admin. MoyZvonki'dan barcha xodim tortiladi
     (kimning ma'lumoti kerak bo'lishini oldindan bilib bo'lmaydi),
     ortiqchasini keyin tozalash kerak. Bu amal qaytarib bo'lmaydi,
     shuning uchun `agents:write` yetmaydi. */
  const canDelete = can('users:write')
  /** Tanlash rejimi — yoqilganda kartochka bosilsa ochilmaydi, belgilanadi */
  const [picking, setPicking] = useState(false)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [importAll, setImportAll] = useState(false)

  const togglePick = (id: string) =>
    setPicked((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const stopPicking = () => {
    setPicking(false)
    setPicked(new Set())
  }
  const leaderboard = useAgentLeaderboard({ days: DAYS })
  // Faol emaslar ham keladi: filtr yuqorida, ro'yxat esa to'liq
  /* Arxivlanganlar faqat ATAYLAB so'ralganda keladi — ular «ishdan
     bo'shagan» emas, «tizimdan olib tashlangan» */
  const agents = useAgents({
    includeInactive: true,
    includeArchived: status === 'archived',
    search,
  })
  const restore = useRestoreAgents()

  /* Botga ulanish holati.
     Birinchi manba — guruhlar daraxti (`enrolled` aynan shu yerda
     hisoblanadi), lekin u `groups:read` talab qiladi va sotuvchi uni
     ko'rmaydi. Shuning uchun `enabled` bilan himoyalangan; ruxsat
     bo'lmasa xodim yozuvining o'z maydonlariga qaytamiz, ular ham
     bo'lmasa holat UMUMAN ko'rsatilmaydi. */
  const tree = useGroupsTree(can('groups:read'))

  const enrolledById = useMemo(
    () => new Map((tree.data?.agents ?? []).map((row) => [row.agent_id, row.enrolled])),
    [tree.data],
  )

  const enrollmentFor = useMemo(() => {
    return (agent: Agent): Enrollment => {
      const fromTree = enrolledById.get(agent.id)
      if (fromTree !== undefined) return fromTree ? 'enrolled' : 'pending'
      return enrollmentOf(agent)
    }
  }, [enrolledById])

  const needle = search.trim()

  const byStatus = useMemo(() => {
    const rows = agents.data ?? []
    if (status === 'archived') return rows.filter((a) => Boolean(a.archived_at))
    if (status === 'active') return rows.filter((a) => a.is_active)
    if (status === 'inactive') return rows.filter((a) => !a.is_active)
    if (status === 'unenrolled') return rows.filter((a) => enrollmentFor(a) === 'pending')
    return rows
  }, [agents.data, status, enrollmentFor])

  /** Botga ulanmaganlar — ro'yxat ham, sanoq ham shundan */
  const pending = useMemo(
    () =>
      (agents.data ?? []).filter(
        (agent) => agent.is_active && enrollmentFor(agent) === 'pending',
      ),
    [agents.data, enrollmentFor],
  )

  const inactiveCount = useMemo(
    () => (agents.data ?? []).filter((a) => !a.is_active).length,
    [agents.data],
  )

  // Leaderboard ballari + agent kartochkasi ma'lumotini birlashtiramiz
  const merged = useMemo(() => {
    const stats = new Map((leaderboard.data ?? []).map((r) => [r.agent_id, r]))
    return byStatus.map((agent) => ({
      agent,
      stats: stats.get(agent.id) ?? null,
    }))
  }, [byStatus, leaderboard.data])

  /* Jadval ko'rinishi leaderboarddan oziqlanadi — qidiruv unga ham
     ta'sir qilishi kerak, aks holda «▦» da 2 ta, «≡» da 15 ta chiqardi */
  const tableRows = useMemo(() => {
    const allowed = new Set(byStatus.map((a) => a.id))
    return (leaderboard.data ?? []).filter((row) => allowed.has(row.agent_id))
  }, [byStatus, leaderboard.data])

  const loading = agents.isLoading || leaderboard.isLoading
  // Qidiruv natija bermadi — bo'sh sahifa emas, aniq javob kerak
  const nothingFound = !loading && !merged.length && Boolean(needle || status !== 'all')

  const clearFilters = () => {
    setSearch('')
    setStatus('all')
  }

  return (
    <Page>
      <PageHeader
        title={t('nav.agents')}
        subtitle={
          needle
            ? t('agents.subtitleSearch', { count: byStatus.length, query: needle })
            : t('agents.subtitle', { count: agents.data?.length ?? 0, days: DAYS })
        }
        actions={
          <>
            <Segmented
              value={view}
              onChange={setView}
              items={[
                { value: 'cards', label: '▦' },
                { value: 'table', label: '≡' },
              ]}
            />
            {canDelete &&
              (picking ? (
                <Button variant="secondary" size="sm" onClick={stopPicking}>
                  {t('common.cancel')}
                </Button>
              ) : (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setPicking(true)
                    setView('cards')
                  }}
                >
                  <Trash2 className="size-3.5" />
                  {t('agents.delete.pick')}
                </Button>
              ))}
            {canDelete && !picking && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setImportAll(true)}
                title={t('agents.importAll.hint')}
              >
                <RefreshCw className="size-3.5" />
                {t('agents.importAll.action')}
              </Button>
            )}
            {canManage && (
              <>
                <Button onClick={() => setEditing('new')}>
                  <Plus className="size-4" />
                  {t('agents.create')}
                </Button>
              </>
            )}
          </>
        }
      />

      {/* ── Filtrlar ──────────────────────────────────────── */}
      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* Qidiruv — xodim ismi va hudud bo'yicha, filtrni backend bajaradi */}
          <SearchInput
            className="min-w-[240px] flex-1"
            placeholder={t('agents.searchPlaceholder')}
            value={search}
            onChange={setSearch}
          />

          <Segmented
            value={status}
            onChange={setStatus}
            items={[
              { value: 'all' as StatusFilter, label: t('agents.filterAll') },
              { value: 'active' as StatusFilter, label: t('agents.filterActive') },
              {
                value: 'inactive' as StatusFilter,
                label: inactiveCount
                  ? t('agents.filterInactiveCount', { count: inactiveCount })
                  : t('agents.filterInactive'),
              },
              {
                value: 'archived' as StatusFilter,
                label: t('agents.delete.archived'),
              },
              {
                value: 'unenrolled' as StatusFilter,
                label: pending.length
                  ? t('agents.filterUnenrolledCount', { count: pending.length })
                  : t('agents.filterUnenrolled'),
              },
            ]}
          />
        </div>
      </Card>

      {/* ── Botga ulanmagan xodimlar ───────────────────────────
          Bunday xodimning guruhlari avtomatik biriktirilmaydi va
          u bo'yicha hech qayerda xato chiqmaydi — sabab shu yerda
          aytilmasa, tizim jimgina ishlamay turaveradi. */}
      {pending.length > 0 && (
        <div className="animate-scale-in flex flex-wrap items-start gap-2.5 rounded-2xl bg-warn/[0.09] px-4 py-3.5 shadow-soft">
          <span className="icon-tile size-9 shrink-0 bg-warn/15 text-warn">
            <Smartphone className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-warn">
              {t('agents.enrollTitle', { count: pending.length })}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-muted">
              {t('agents.enrollHint')}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {pending.slice(0, 8).map((agent) => (
                <Badge key={agent.id} tone="warn">
                  {agent.full_name}
                </Badge>
              ))}
              {pending.length > 8 && (
                <Badge tone="neutral">
                  {t('agents.enrollMore', { count: pending.length - 8 })}
                </Badge>
              )}
            </div>
          </div>
          <Button
            variant="secondary"
            size="sm"
            className="shrink-0"
            onClick={() => setEnrollHelp(true)}
          >
            {t('agents.enrollHow')}
          </Button>
        </div>
      )}

      {/* Faolsizlantirish natijasi — guruhlar bo'shadi, admin bilsin */}
      {freed && (
        <div className="animate-scale-in flex items-start gap-2.5 rounded-2xl bg-good/10 px-4 py-3 text-xs leading-relaxed text-good shadow-soft">
          <CheckCircle2 className="mt-px size-4 shrink-0" />
          <span className="flex-1">
            {t('agents.deactivatedFreed', { name: freed.name, count: freed.count })}
          </span>
          <button
            type="button"
            onClick={() => setFreed(null)}
            aria-label={t('common.close')}
            className="shrink-0 rounded-md p-0.5 opacity-60 transition-opacity duration-250 ease-ios hover:opacity-100"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-44 w-full" />
          ))}
        </div>
      ) : nothingFound ? (
        <Card>
          <NoMatches query={needle} onClear={clearFilters} />
        </Card>
      ) : !merged.length ? (
        <Card>
          <EmptyState message={t('table.empty')} />
        </Card>
      ) : view === 'table' ? (
        <Card>
          <AgentTable rows={tableRows} onSelect={(id) => navigate(`/agents/${id}`)} />
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 3xl:grid-cols-5">
          {merged.map(({ agent, stats }) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              stats={stats}
              enrollment={enrollmentFor(agent)}
              canManage={canManage && !picking}
              picking={picking}
              picked={picked.has(agent.id)}
              onOpen={() =>
                picking ? togglePick(agent.id) : navigate(`/agents/${agent.id}`)
              }
              onEdit={() => setEditing(agent)}
            />
          ))}
        </div>
      )}

      {/* Tanlov paneli — ekran pastida osilib turadi, chunki ro'yxat
          uzun va admin pastga tushib ketganda ham amal qo'l ostida
          bo'lishi kerak */}
      {picking && picked.size > 0 && (
        <div className="sticky bottom-4 z-10 mx-auto flex w-fit items-center gap-3 rounded-2xl bg-surface px-4 py-3 shadow-pop">
          <span className="text-xs font-medium">
            {t('agents.delete.selected', { count: picked.size })}
          </span>
          {status === 'archived' ? (
            <Button
              variant="secondary"
              size="sm"
              disabled={restore.isPending}
              onClick={() =>
                restore.mutate([...picked], { onSuccess: stopPicking })
              }
            >
              <RotateCcw className="size-3.5" />
              {t('agents.delete.restore')}
            </Button>
          ) : (
            <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
              <Trash2 className="size-3.5" />
              {t('agents.delete.action')}
            </Button>
          )}
        </div>
      )}

      <ImportAllModal open={importAll} onClose={() => setImportAll(false)} />

      <DeleteAgentsModal
        open={confirmDelete}
        agentIds={[...picked]}
        onClose={() => setConfirmDelete(false)}
        onDone={(count) => {
          if (count > 0) stopPicking()
        }}
      />

      {/* Yaratish / tahrirlash — modal oynada */}
      <AgentModal
        target={editing}
        onClose={() => setEditing(null)}
        onSaved={(agent) => {
          const count = freedGroupCount(agent)
          setFreed(count ? { name: agent.full_name, count } : null)
        }}
      />

      {/* Botga ulanish ko'rsatmasi — Guruhlar sahifasi bilan bir xil matn */}
      <EnrollmentModal
        open={enrollHelp}
        names={pending.map((agent) => agent.full_name)}
        onClose={() => setEnrollHelp(false)}
      />
    </Page>
  )
}

/* ── Qidiruv natija bermadi ──────────────────────────────────
   Bo'sh ekran «yuklanmadimi yoki topilmadimi?» degan savol
   qoldiradi — shuning uchun so'ralgan matn aynan takrorlanadi. */

function NoMatches({ query, onClear }: { query: string; onClear: () => void }) {
  const { t } = useTranslation()
  return (
    <CardBody className="flex flex-col items-center gap-3 py-14 text-center">
      <span className="icon-tile size-12 text-muted">
        <SearchX className="size-5" />
      </span>
      <p className="text-sm font-medium">
        {query ? t('agents.searchEmpty', { query }) : t('agents.filterEmpty')}
      </p>
      <p className="max-w-md text-xs leading-relaxed text-muted">
        {t('agents.searchEmptyHint')}
      </p>
      <Button variant="secondary" size="sm" onClick={onClear}>
        {t('agents.searchClear')}
      </Button>
    </CardBody>
  )
}

/* ── Xodim kartochkasi ───────────────────────────────────── */

function AgentCard({
  agent,
  stats,
  enrollment,
  canManage,
  picking,
  picked,
  onOpen,
  onEdit,
}: {
  agent: Agent
  stats: AgentRow | null
  /** `unknown` bo'lsa hech nima ko'rsatilmaydi — maydon backendda yo'q */
  enrollment: Enrollment
  canManage: boolean
  /** Tanlash rejimi — bosilganda ochilmaydi, belgilanadi */
  picking: boolean
  picked: boolean
  onOpen: () => void
  onEdit: () => void
}) {
  const { t } = useTranslation()
  const tone = scoreTone(stats?.ai_score) as 'accent' | 'good' | 'warn' | 'bad'

  /* Client bahosi. Chegaraga yetmagan reyting «—» bilan ko'rsatilsa,
     u «baho kelmadi» bilan bir xil ko'rinadi — aslida esa baho keldi,
     shunchaki o'rtacha hali ochilmadi. */
  const rating = rowProgress(stats)
  const ratingReady = Boolean(stats?.client_rating_ready && stats.client_rating != null)

  return (
    <div
      onClick={onOpen}
      className={cn(
        'card card-hover relative cursor-pointer p-5',
        !agent.is_active && 'opacity-55',
        picking && 'select-none',
        picked && 'ring-2 ring-bad',
      )}
    >
      {picking && (
        <span
          className={cn(
            'absolute right-3 top-3 grid size-5 place-items-center rounded-md',
            'transition-colors duration-250 ease-ios',
            picked ? 'bg-bad text-white' : 'bg-surface-2 text-transparent',
          )}
        >
          <Check className="size-3.5" />
        </span>
      )}

      <div className="flex items-start gap-3">
        <Avatar
          name={agent.full_name}
          color={agent.color}
          src={agent.avatar_url}
          size="lg"
        />

        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">{agent.full_name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {/* Xizmat hududlari — Telegram guruhlari bo'limi bilan bir xil.
                Bo'sh bo'lsa «biriktirilmagan» deb ochiq yoziladi: yashash
                joyini ko'rsatib qo'yish noto'g'ri xulosaga olib borardi. */}
            {agent.regions?.length ? (
              agent.regions.map((name) => <Badge key={name}>{name}</Badge>)
            ) : (
              <Badge tone="warn">{t('agents.noRegion')}</Badge>
            )}
            {!agent.is_active && <Badge tone="bad">{t('agents.inactive')}</Badge>}
            {/* Botga ulanmagan — guruhlari avtomatik biriktirilmaydi */}
            {enrollment === 'pending' && agent.is_active && (
              <Badge tone="warn" title={t('groups.enroll.what')}>
                <Smartphone className="size-3" />
                {t('agents.notEnrolled')}
              </Badge>
            )}
          </div>
        </div>

        <ScoreRing value={stats?.ai_score ?? null} tone={tone} />
      </div>

      {enrollment === 'pending' && agent.is_active && (
        <p className="mt-3 rounded-xl bg-warn/[0.09] px-3 py-2 text-2xs leading-relaxed text-warn">
          {t('agents.notEnrolledHint')}
        </p>
      )}

      {/* Ko'rsatkichlar */}
      <div className="mt-4 grid grid-cols-3 gap-2 border-t border-border/60 pt-3">
        <Stat label={t('table.calls')} value={stats ? formatNumber(stats.calls) : '—'} />
        <Stat
          label={t('kpi.clientRating')}
          value={
            ratingReady
              ? `${stats!.client_rating!.toFixed(1)} / 5`
              : rating.count > 0
                ? rating.min != null
                  ? `${rating.count} / ${rating.min}`
                  : String(rating.count)
                : '—'
          }
          hint={
            !ratingReady && rating.count > 0
              ? t('agents.ratingCollecting')
              : undefined
          }
        />
        <Stat
          label={t('table.duration')}
          value={stats ? formatDuration(stats.avg_duration_sec) : '—'}
        />
      </div>

      {/* Ball chizig'i + trend */}
      <div className="mt-3 flex items-center gap-2.5">
        <MiniBar value={stats?.ai_score ?? null} tone={tone} width={0} />
        <span className={cn('tnum shrink-0 text-xs font-semibold', TONE_CLASS[tone])}>
          {stats?.ai_score?.toFixed(1) ?? '—'}
        </span>
        <TrendDelta value={stats?.rank_delta} />

        {canManage && (
          <Button
            variant="ghost"
            size="icon"
            className="-my-2 -mr-2 size-7 shrink-0"
            title={t('common.edit')}
            onClick={(e) => {
              e.stopPropagation()
              onEdit()
            }}
          >
            <Pencil className="size-3.5" />
          </Button>
        )}
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  /** Raqam nimani anglatishini aytadi (masalan «yig'ilmoqda») */
  hint?: string
}) {
  return (
    <div>
      <div className="text-2xs uppercase tracking-wide text-muted">{label}</div>
      <div className="tnum mt-0.5 text-sm font-semibold">{value}</div>
      {hint && <div className="mt-0.5 text-2xs text-warn">{hint}</div>}
    </div>
  )
}

/* ── Reyting progressi ───────────────────────────────────────
   Chegara (`survey.min_responses`) leaderboard javobiga qo'shilsa
   avtomatik ishlaydi. `AgentRow` turi `modules/analytics` da va bu
   modulga tegishli emas — shuning uchun maydon shu yerda ixtiyoriy
   deb o'qiladi, yo'q bo'lsa maxrajsiz son ko'rsatiladi. */

function rowProgress(stats: AgentRow | null) {
  const extra = stats as (AgentRow & { min_responses?: number | null }) | null
  return ratingProgress(
    stats
      ? { count: stats.client_rating_count, min_responses: extra?.min_responses }
      : null,
  )
}
