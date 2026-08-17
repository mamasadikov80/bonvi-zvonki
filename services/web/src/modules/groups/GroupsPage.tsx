/**
 * Telegram guruhlari — DARAXT: sotuvchi → hudud → guruhlar.
 *
 * Nega yassi ro'yxat emas. Har bir mijoz uchun sotuvchi bilan alohida
 * guruh ochilgan: bitta hududda 20 ta mijoz bo'lsa — 20 ta guruh,
 * umumiy hisobda ~1000 ta. Bunday miqyosda «hammasini ko'rsatish»
 * degan ekran hech qanday savolga javob bermaydi va brauzerni ham
 * o'ldiradi. Daraxt esa savolni bosqichlarga bo'ladi va har bir
 * bosqichda sanoq ko'rsatadi.
 *
 * SO'ROVLAR. Sahifa ochilganda BITTA so'rov ketadi — `GET /groups/tree`
 * (yig'ma sanoqlar). Guruh qatorlari faqat tugun ochilganda,
 * 50 tadan sahifalab tortiladi.
 *
 * DARAXTDAN TASHQARIDAGI TO'PLAM: «Xodimi aniqlanmagan». Bot guruhda
 * qaysi sotuvchi borligini topa olmagan — bu haqiqiy nosozlik, chunki
 * bunday guruh hech qachon so'rovnoma olmaydi va hech qayerda xato
 * ham chiqmaydi. Shuning uchun u daraxt TEPASIDA, ochiq turadi.
 *
 * HUDUDSIZ guruhlar esa nosozlik EMAS. Ular har bir sotuvchining
 * ichida alohida tugun bo'lib turadi: guruh xodimga birikkan, lekin
 * hududi yo'q. Bu ikki xil holatning umumiy uyi — hali saralanmagani
 * va ataylab chetda qoldirilgani (mijozsiz ichki guruh). Ikkalasida
 * ham so'rovnoma yuborilmaydi, tugun shu oqibatni yozib turadi.
 */

import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Info,
  MapPin,
  Send,
  Smartphone,
  Users2,
  X,
} from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuth } from '@/modules/auth/store'
import {
  errorMessage,
  fetchAllGroups,
  isConflict,
  isMissingEndpoint,
  nodeKey,
  treeTotals,
  UNASSIGNED_KEY,
  useDeleteGroup,
  useGroupsTree,
  useSendGroupSurvey,
  type GroupsQuery,
  type TelegramGroup,
} from '@/modules/groups/api'
import { BroadcastModal } from '@/modules/groups/BroadcastModal'
import { BulkAssignModal, type BulkMode } from '@/modules/groups/BulkAssignModal'
import { EnrollmentModal } from '@/modules/groups/EnrollmentNotice'
import { GroupList, type Selection } from '@/modules/groups/GroupList'
import { GroupModal } from '@/modules/groups/GroupModal'
import { AgentNode, type TreeCallbacks } from '@/modules/groups/GroupTree'
import { Page, PageHeader } from '@/shared/layout/Page'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Skeleton,
  Switch,
} from '@/shared/ui/primitives'
import { SearchInput } from '@/shared/ui/SearchInput'

/** «Hammasini tanlash» bir marta ko'pi bilan shuncha guruh oladi */
const SELECT_CAP = 500

/**
 * Modal birinchi marta ochilgunicha DOM ga ham, tarmoqqa ham chiqmaydi.
 *
 * Sabab: modallar ichida `useAgents()` va `useRegions()` bor. Ular
 * doim mount qilinsa, sahifa ochilishida hech kim so'ramagan ikkita
 * so'rov ketardi. Bir marta ochilgandan keyin komponent joyida
 * qoladi — Radix yopilish animatsiyasi mount holatini talab qiladi.
 */
function useLazyMount(open: boolean): boolean {
  const [mounted, setMounted] = useState(open)
  if (open && !mounted) setMounted(true)
  return mounted
}

interface Notice {
  tone: 'good' | 'warn' | 'bad'
  text: string
}

export function GroupsPage() {
  const { t } = useTranslation()
  const { can } = useAuth()

  const canWrite = can('groups:write')

  /* ── Holat ─────────────────────────────────────────────── */
  const [includeInactive, setIncludeInactive] = useState(false)
  const [search, setSearch] = useState('')
  const [agentFilter, setAgentFilter] = useState('')

  const [openAgents, setOpenAgents] = useState<Set<string>>(new Set())
  // Bir vaqtda faqat BITTA hudud tuguni ochiq — shu bitta qoida
  // tufayli ekranda 50 tadan ortiq qator hech qachon bo'lmaydi
  const [openRegion, setOpenRegion] = useState<string | null>(null)
  /* To'plam YOPIQ boshlanadi — qoida bitta: qator faqat tugun
     ochilganda tortiladi. Ko'zga tashlanishi bundan zarar ko'rmaydi:
     sanoq, ogohlantirish rangi va izoh daraxtdan TEPADA, ochmasdan
     ham ko'rinib turadi. Ochilganda esa qatorlar keladi. */
  const [unassignedOpen, setUnassignedOpen] = useState(false)

  const [selected, setSelected] = useState<Map<string, TelegramGroup>>(new Map())
  const [busyKey, setBusyKey] = useState<string | null>(null)

  const [editing, setEditing] = useState<TelegramGroup | null>(null)
  const [deleting, setDeleting] = useState<TelegramGroup | null>(null)
  const [bulkMode, setBulkMode] = useState<BulkMode | null>(null)
  const [broadcasting, setBroadcasting] = useState(false)
  const [enrollHelp, setEnrollHelp] = useState(false)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [sendingId, setSendingId] = useState<string | null>(null)

  const tree = useGroupsTree()
  const send = useSendGroupSurvey()

  /* Modallar birinchi ochilgunicha umuman ulanmaydi — ichidagi
     «xodimlar» va «hududlar» so'rovlari sahifa ochilishida ketib
     qolmasin. Birinchi paintda faqat BITTA so'rov bo'lishi kerak. */
  const editModalMounted = useLazyMount(editing !== null)
  const deleteModalMounted = useLazyMount(deleting !== null)
  const bulkModalMounted = useLazyMount(bulkMode !== null)

  const totals = useMemo(() => treeTotals(tree.data), [tree.data])

  const pendingNames = useMemo(
    () =>
      (tree.data?.agents ?? [])
        .filter((agent) => !agent.enrolled)
        .map((agent) => agent.full_name),
    [tree.data],
  )

  const agents = useMemo(() => {
    const rows = tree.data?.agents ?? []
    const needle = agentFilter.trim().toLowerCase()
    const list = needle
      ? rows.filter((agent) => agent.full_name.toLowerCase().includes(needle))
      : rows
    return [...list].sort((a, b) => {
      // Ulanmaganlar tepada: ularning shoxi bo'sh turadi va sabab
      // ko'rinmasa bu jimgina nosozlik
      if (a.enrolled !== b.enrolled) return a.enrolled ? 1 : -1
      return a.full_name.localeCompare(b.full_name)
    })
  }, [tree.data, agentFilter])

  /* ── Tanlov ────────────────────────────────────────────── */

  const selection: Selection = useMemo(
    () => ({
      has: (id) => selected.has(id),
      size: selected.size,
      toggle: (group) =>
        setSelected((prev) => {
          const next = new Map(prev)
          if (next.has(group.id)) next.delete(group.id)
          else next.set(group.id, group)
          return next
        }),
      addMany: (groups) =>
        setSelected((prev) => {
          const next = new Map(prev)
          for (const group of groups) next.set(group.id, group)
          return next
        }),
    }),
    [selected],
  )

  const selectedList = useMemo(() => [...selected.values()], [selected])
  const clearSelection = () => setSelected(new Map())

  /** Tugundagi hamma guruhni tanlaydi — sahifadagini emas */
  const selectAll = async (key: string, query: GroupsQuery, then?: BulkMode) => {
    setBusyKey(key)
    setNotice(null)
    try {
      const { items, truncated } = await fetchAllGroups(
        { ...query, include_inactive: includeInactive },
        SELECT_CAP,
      )
      selection.addMany(items)
      if (truncated) {
        setNotice({ tone: 'warn', text: t('groups.tree.selectCapped', { count: SELECT_CAP }) })
      }
      if (then && items.length) setBulkMode(then)
    } catch (error) {
      setNotice({ tone: 'bad', text: errorMessage(error, t('common.error')) })
    } finally {
      setBusyKey(null)
    }
  }

  /* ── So'rovnoma yuborish ────────────────────────────────── */

  const sendSurvey = (group: TelegramGroup) => {
    setNotice(null)
    setSendingId(group.id)
    send.mutate(group.id, {
      onSuccess: () => setNotice({ tone: 'good', text: t('groups.sent') }),
      onError: (error) =>
        setNotice({
          tone: isConflict(error) ? 'warn' : 'bad',
          text: errorMessage(error, t('common.error')),
        }),
      onSettled: () => setSendingId(null),
    })
  }

  const rowActions = {
    canWrite,
    sendingId,
    onEdit: setEditing,
    onDelete: setDeleting,
    onSend: sendSurvey,
  }

  const treeCallbacks: TreeCallbacks = {
    openAgents,
    onToggleAgent: (agentId) =>
      setOpenAgents((prev) => {
        const next = new Set(prev)
        if (next.has(agentId)) next.delete(agentId)
        else next.add(agentId)
        return next
      }),
    openRegion,
    onToggleRegion: setOpenRegion,
    onSelectAll: (key, query) => void selectAll(key, query),
    onAssignRegion: (key, query) => void selectAll(key, query, 'region'),
    busyKey,
    includeInactive,
    selection,
    actions: rowActions,
  }

  const searching = search.trim().length > 0

  /* ── Daraxt endpointi yo'q ─────────────────────────────── */
  if (tree.isError) {
    return (
      <Page>
        <PageHeader title={t('nav.groups')} />
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-16 text-center">
            <span className="icon-tile size-12 text-warn">
              <AlertTriangle className="size-5" />
            </span>
            <p className="text-sm font-medium">
              {isMissingEndpoint(tree.error)
                ? t('groups.tree.backendMissing')
                : t('common.error')}
            </p>
            <p className="max-w-md text-xs leading-relaxed text-muted">
              {isMissingEndpoint(tree.error)
                ? t('groups.tree.backendMissingHint')
                : errorMessage(tree.error, '')}
            </p>
            <Button variant="secondary" size="sm" onClick={() => void tree.refetch()}>
              {t('common.retry')}
            </Button>
          </CardBody>
        </Card>
      </Page>
    )
  }

  return (
    <Page>
      <PageHeader
        title={t('nav.groups')}
        subtitle={t('groups.tree.subtitle', {
          count: totals.groups,
          agents: tree.data?.agents.length ?? 0,
        })}
        actions={
          canWrite ? (
            <Button onClick={() => setBroadcasting(true)}>
              <Send className="size-4" />
              {t('groups.broadcast')}
            </Button>
          ) : undefined
        }
      />

      {/* ── Yig'ma ko'rsatkichlar ─────────────────────────────
          «Xodimi aniqlanmagan» sanog'i ATAYLAB yo'q. U ikki marta
          ko'rinardi va ko'p vaqt «0» bo'lib turardi — ya'ni joyni
          egallab, hech narsa aytmasdi. Bu holat haqiqatan yuz
          bersa, pastdagi to'liq to'plam (`totals.unassigned > 0`)
          o'zi ochiladi va u yerda darhol tuzatsa bo'ladi. */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:gap-4">
        <Tile icon={Users2} label={t('groups.tileTotal')} loading={tree.isLoading}>
          <Value>{formatNumber(totals.groups)}</Value>
          <Hint>{t('groups.tree.tileTotalHint')}</Hint>
        </Tile>

        <Tile
          icon={MapPin}
          label={t('groups.tree.tileRegionless')}
          loading={tree.isLoading}
        >
          <Value>{formatNumber(totals.regionless)}</Value>
          <Hint>{t('groups.tree.tileRegionlessHint')}</Hint>
        </Tile>

        <Tile
          icon={Smartphone}
          label={t('groups.tree.tileUnenrolled')}
          tone={totals.unenrolled ? 'warn' : 'good'}
          loading={tree.isLoading}
        >
          <Value tone={totals.unenrolled ? 'warn' : 'good'}>
            {formatNumber(totals.unenrolled)}
          </Value>
          {totals.unenrolled ? (
            <button
              type="button"
              onClick={() => setEnrollHelp(true)}
              className="mt-2 text-2xs font-medium text-accent underline-offset-2 hover:underline"
            >
              {t('groups.tree.tileUnenrolledAction')}
            </button>
          ) : (
            <Hint>{t('groups.tree.tileUnenrolledOk')}</Hint>
          )}
        </Tile>
      </div>

      {/* ── Umumiy eslatma (yuborish natijasi va h.k.) ────── */}
      {notice && <PageNotice notice={notice} onDismiss={() => setNotice(null)} />}

      {/* ── Daraxtdan tashqarida: xodimi aniqlanmagan ─────── */}
      {!tree.isLoading && totals.unassigned > 0 && (
        <Card className="overflow-hidden ring-1 ring-warn/25">
          <div className="flex items-center gap-2 bg-warn/[0.07] p-3.5">
            <button
              type="button"
              onClick={() => setUnassignedOpen((open) => !open)}
              aria-expanded={unassignedOpen}
              className="flex min-w-0 flex-1 items-center gap-3 rounded-xl px-1 py-1 text-left"
            >
              <ChevronRight
                className={cn(
                  'size-4 shrink-0 text-warn transition-transform duration-250 ease-ios',
                  unassignedOpen && 'rotate-90',
                )}
              />
              <span className="icon-tile size-9 shrink-0 bg-warn/15 text-warn">
                <AlertTriangle className="size-4" />
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-[0.9375rem] font-semibold text-text">
                    {t('groups.tree.unassignedTitle')}
                  </h3>
                  <Badge tone="warn">{formatNumber(totals.unassigned)}</Badge>
                </div>
                <p className="mt-0.5 text-xs leading-relaxed text-muted">
                  {t('groups.tree.unassignedHint')}
                </p>
              </div>
            </button>

            {canWrite && (
              <Button
                variant="secondary"
                size="sm"
                className="shrink-0"
                disabled={busyKey !== null}
                onClick={() =>
                  void selectAll(
                    nodeKey(UNASSIGNED_KEY, null),
                    { has_agent: false, include_inactive: includeInactive },
                    'agent',
                  )
                }
              >
                {busyKey === nodeKey(UNASSIGNED_KEY, null)
                  ? t('groups.tree.selecting')
                  : t('groups.tree.assignAgentAll', { count: totals.unassigned })}
              </Button>
            )}
          </div>

          {unassignedOpen && (
            <CardBody className="space-y-2 pt-3.5">
              {/* `scan` — serverda `has_agent` filtri yo'q, shuning
                  uchun panel sahifalarni o'zi aylanib chiqadi.
                  Backend filtrni qo'shgach bitta so'rovga qisqaradi. */}
              <GroupList
                scan
                query={{ has_agent: false, include_inactive: includeInactive }}
                emptyMessage={t('groups.tree.nodeEmpty')}
                selection={selection}
                showRegion
                actions={rowActions}
              />
            </CardBody>
          )}
        </Card>
      )}

      {/* ── Daraxt ────────────────────────────────────────── */}
      <Card>
        <CardHeader
          title={t('groups.tree.title')}
          hint={t('groups.tree.hint')}
          action={
            <label className="flex shrink-0 items-center gap-2 text-2xs text-muted">
              {t('groups.showInactive')}
              <Switch
                checked={includeInactive}
                label={t('groups.showInactive')}
                onChange={setIncludeInactive}
              />
            </label>
          }
        />

        <CardBody className="space-y-3 pt-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* Guruh qidiruvi — backendda, kechikish bilan */}
            <SearchInput
              className="min-w-[260px] flex-1"
              placeholder={t('groups.tree.searchGroups')}
              value={search}
              onChange={setSearch}
            />
            {/* Xodim qidiruvi — daraxt tugunlari ustida, lokal */}
            <SearchInput
              className="min-w-[200px]"
              placeholder={t('groups.tree.searchAgents')}
              value={agentFilter}
              onChange={setAgentFilter}
              delay={120}
            />
          </div>

          {searching ? (
            <div className="space-y-2">
              <p className="text-2xs text-muted">
                {t('groups.tree.searchResults', { query: search.trim() })}
              </p>
              <GroupList
                query={{ search, include_inactive: includeInactive }}
                emptyMessage={t('groups.tree.searchEmpty', { query: search.trim() })}
                selection={selection}
                showAgent
                showRegion
                actions={rowActions}
              />
            </div>
          ) : tree.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : !agents.length ? (
            agentFilter.trim() ? (
              <EmptyState
                message={t('groups.tree.noAgentMatch', { query: agentFilter.trim() })}
              />
            ) : (
              <EmptyGroups />
            )
          ) : (
            <div className="space-y-2">
              {agents.map((agent) => (
                <AgentNode key={agent.agent_id} agent={agent} tree={treeCallbacks} />
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      {/* ── Tanlov paneli — ekranning pastida yopishib turadi ── */}
      {canWrite && selected.size > 0 && (
        <div className="sticky bottom-4 z-30 animate-scale-in">
          <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-surface p-3 shadow-pop">
            <span className="px-1 text-sm font-semibold">
              {t('groups.tree.selectedCount', { count: selected.size })}
            </span>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={() => setBulkMode('region')}>
                <MapPin className="size-3.5" />
                {t('groups.bulk.modeRegion')}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setBulkMode('clear')}>
                <X className="size-3.5" />
                {t('groups.bulk.modeClear')}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setBulkMode('agent')}>
                {t('groups.bulk.modeAgent')}
              </Button>
              <Button variant="ghost" size="sm" onClick={clearSelection}>
                {t('groups.tree.clearSelection')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modallar — tahrirlash faqat shu yerda ───────────
          Ular BIRINCHI ochilgunicha ulanmaydi: ichidagi «xodimlar»
          va «hududlar» so'rovlari sahifa ochilishida ketib qolmasin.
          Bir marta ochilgach mount bo'lib qoladi — Radix yopilish
          animatsiyasi uchun komponent joyida turishi kerak. */}
      {editModalMounted && (
        <GroupModal group={editing} onClose={() => setEditing(null)} />
      )}

      {deleteModalMounted && (
        <DeleteGroupModal group={deleting} onClose={() => setDeleting(null)} />
      )}

      {canWrite && bulkModalMounted && (
        <BulkAssignModal
          open={bulkMode !== null}
          groups={selectedList}
          initialMode={bulkMode ?? 'region'}
          onClose={() => setBulkMode(null)}
          onDone={clearSelection}
        />
      )}

      <EnrollmentModal
        open={enrollHelp}
        names={pendingNames}
        onClose={() => setEnrollHelp(false)}
      />

      {canWrite && (
        <BroadcastModal open={broadcasting} onClose={() => setBroadcasting(false)} />
      )}
    </Page>
  )
}

/* ── Bo'sh holat — ko'rsatma beradi, jim turmaydi ────────────
   Telegram Bot API bot qaysi guruhlarda ekanini ro'yxat qilib
   BERA OLMAYDI. Shuning uchun admin bo'sh sahifaga qarab nima
   qilishni bilmay qolmasligi kerak. */

function EmptyGroups() {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center gap-4 py-10 text-center">
      <span className="icon-tile size-12 text-accent">
        <Users2 className="size-5" />
      </span>
      <div>
        <p className="text-sm font-medium">{t('groups.empty')}</p>
        <p className="mt-1 text-xs text-muted">{t('groups.emptyHowTitle')}</p>
      </div>

      <ol className="w-full max-w-xl space-y-2 text-left">
        {[t('groups.emptyStep1'), t('groups.emptyStep2')].map((step, index) => (
          <li
            key={index}
            className="flex items-start gap-3 rounded-2xl bg-surface-2/60 p-3.5"
          >
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent-soft text-2xs font-semibold text-accent">
              {index + 1}
            </span>
            <span className="text-xs leading-relaxed text-text">{step}</span>
          </li>
        ))}
      </ol>

      <p className="flex max-w-xl items-start gap-2 text-2xs leading-relaxed text-muted">
        <Info className="mt-px size-3.5 shrink-0" />
        {t('groups.emptyWhy')}
      </p>
    </div>
  )
}

/* ── Sahifa eslatmasi ────────────────────────────────────── */

function PageNotice({
  notice,
  onDismiss,
}: {
  notice: Notice
  onDismiss: () => void
}) {
  const { t } = useTranslation()
  const Icon = notice.tone === 'good' ? CheckCircle2 : Info
  return (
    <div
      role="status"
      className={cn(
        'animate-scale-in flex items-start gap-2.5 rounded-2xl px-4 py-3 text-xs leading-relaxed shadow-soft',
        notice.tone === 'good' && 'bg-good/10 text-good',
        notice.tone === 'warn' && 'bg-warn/10 text-warn',
        notice.tone === 'bad' && 'bg-bad/10 text-bad',
      )}
    >
      <Icon className="mt-px size-4 shrink-0" />
      <span className="flex-1">{notice.text}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label={t('common.close')}
        className="shrink-0 rounded-md p-0.5 opacity-60 transition-opacity duration-250 ease-ios hover:opacity-100"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}

/* ── O'chirishni tasdiqlash ──────────────────────────────── */

function DeleteGroupModal({
  group,
  onClose,
}: {
  group: TelegramGroup | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const remove = useDeleteGroup()
  const [error, setError] = useState<string | null>(null)

  return (
    <Modal
      open={group !== null}
      onOpenChange={(open) => !open && onClose()}
      title={t('groups.deleteTitle')}
      description={group?.title}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => {
              if (!group) return
              setError(null)
              remove.mutate(group.id, {
                onSuccess: onClose,
                onError: (e) => setError(errorMessage(e, t('common.error'))),
              })
            }}
          >
            {remove.isPending ? t('settings.saving') : t('common.delete')}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-sm leading-relaxed">
          {t('groups.deleteConfirm', { title: group?.title ?? '' })}
        </p>
        <p className="rounded-xl bg-surface-2/60 px-4 py-3 text-2xs leading-relaxed text-muted">
          {t('groups.deleteOnlyLeft')}
        </p>
        {error && (
          <p className="animate-scale-in rounded-xl bg-bad/10 px-4 py-3 text-xs text-bad">
            {error}
          </p>
        )}
      </div>
    </Modal>
  )
}

/* ── Yig'ma plitka ───────────────────────────────────────── */

const TILE_TONE: Record<'accent' | 'good' | 'warn', string> = {
  accent: 'text-accent',
  good: 'text-good',
  warn: 'text-warn',
}

function Tile({
  icon: Icon,
  label,
  tone = 'accent',
  loading,
  children,
}: {
  icon: typeof Users2
  label: string
  tone?: 'accent' | 'good' | 'warn'
  loading?: boolean
  children: ReactNode
}) {
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center gap-2.5">
        <span className={cn('icon-tile size-8', TILE_TONE[tone])}>
          <Icon className="size-4" />
        </span>
        <span className="label-eyebrow">{label}</span>
      </div>
      {loading ? <Skeleton className="h-8 w-24" /> : children}
    </Card>
  )
}

function Value({
  children,
  tone,
}: {
  children: ReactNode
  tone?: 'good' | 'warn'
}) {
  return (
    <span
      className={cn(
        'tnum block text-2xl font-semibold leading-none',
        tone === 'good' && 'text-good',
        tone === 'warn' && 'text-warn',
      )}
    >
      {children}
    </span>
  )
}

function Hint({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-2xs leading-relaxed text-muted">{children}</p>
}
