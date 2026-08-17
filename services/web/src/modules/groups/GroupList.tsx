/**
 * Daraxt bargi — bitta tugunning guruhlari.
 *
 * Uch joyda bir xil ishlatiladi: hudud tugunida, «xodimi aniqlanmagan»
 * to'plamida va qidiruv natijasida. Shuning uchun u ustidagi tugun
 * haqida hech narsa bilmaydi — unga faqat `query` beriladi.
 *
 * MIQYOS: ro'yxat SAHIFALANADI (50 tadan). Ekranda hech qachon
 * yuzdan ortiq qator bo'lmaydi, chunki sahifada bir vaqtda faqat
 * bitta hudud tuguni ochiq turadi (`GroupsPage` shunday boshqaradi).
 */

import {
  Bot,
  ChevronLeft,
  ChevronRight,
  Hand,
  Link2,
  MapPin,
  Pencil,
  Send,
  Trash2,
  Users2,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  canDelete,
  canSendSurvey,
  errorMessage,
  isManual,
  isMissingEndpoint,
  PAGE_SIZE,
  useGroupPage,
  useScannedGroups,
  type GroupPage,
  type GroupsQuery,
  type TelegramGroup,
} from '@/modules/groups/api'
import { useDateFormat } from '@/shared/lib/date'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Avatar } from '@/shared/ui/dataviz'
import { Badge, Button, Skeleton } from '@/shared/ui/primitives'

/* ── Tanlov (ommaviy amallar uchun) ──────────────────────── */

export interface Selection {
  has: (id: string) => boolean
  toggle: (group: TelegramGroup) => void
  addMany: (groups: TelegramGroup[]) => void
  size: number
}

export interface GroupRowActions {
  canWrite: boolean
  sendingId: string | null
  onEdit: (group: TelegramGroup) => void
  onDelete: (group: TelegramGroup) => void
  onSend: (group: TelegramGroup) => void
}

/* ── Ro'yxat ─────────────────────────────────────────────── */

export function GroupList({
  query,
  enabled = true,
  scan = false,
  emptyMessage,
  selection,
  showAgent = false,
  showRegion = false,
  actions,
}: {
  /** `page` bermang — u shu komponentning ichki holati */
  query: GroupsQuery
  enabled?: boolean
  /**
   * Serverda mos filtr yo'q (`has_agent`) — panel sahifalarni o'zi
   * aylanib chiqadi va ro'yxatni o'zi bo'ladi. Backend filtrni
   * qo'shgach bu yo'l o'z-o'zidan bitta so'rovga qisqaradi.
   */
  scan?: boolean
  emptyMessage: string
  selection: Selection
  showAgent?: boolean
  showRegion?: boolean
  actions: GroupRowActions
}) {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)

  // Filtr o'zgarsa birinchi sahifaga qaytamiz — aks holda «3-sahifa»
  // yangi filtrda bo'sh chiqib, ro'yxat yo'qdek ko'rinardi
  const signature = JSON.stringify(query)
  useEffect(() => {
    setPage(1)
  }, [signature])

  const served = useGroupPage({ ...query, page, page_size: PAGE_SIZE }, enabled && !scan)
  const scanned = useScannedGroups(query, enabled && scan)

  const result = scan ? scanned : served
  // Aylanib chiqilgan ro'yxat panelning o'zida sahifalanadi —
  // DOM da baribir 50 tadan ortiq qator bo'lmaydi
  const data: GroupPage | undefined = scan
    ? scanned.data && {
        items: scanned.data.items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
        total: scanned.data.items.length,
        page,
        page_size: PAGE_SIZE,
        exact: !scanned.data.truncated,
      }
    : served.data

  if (result.isError) {
    return (
      <p className="rounded-xl bg-bad/10 px-3.5 py-3 text-2xs leading-relaxed text-bad">
        {isMissingEndpoint(result.error)
          ? t('groups.tree.backendMissing')
          : errorMessage(result.error, t('common.error'))}
      </p>
    )
  }

  if (result.isLoading || !data) {
    return (
      <div className="space-y-1.5">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    )
  }

  if (!data.items.length) {
    return (
      <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs text-muted">
        {emptyMessage}
      </p>
    )
  }

  const from = (data.page - 1) * data.page_size + 1
  const to = from + data.items.length - 1
  /* Sahifalagich qachon ishonchli:
       • `scan` — DOIM: ro'yxat panelda to'liq turibdi va shu yerda
         bo'linadi (`exact: false` u yerda «chegaraga urildi» degani,
         sahifalash esa yig'ilgani ustida baribir to'g'ri);
       • server rejimi — faqat server filtrni qo'llagan bo'lsa. Aks
         holda `total` butunlay boshqa to'plamniki va sahifalagich
         mavjud bo'lmagan sahifalarga olib borardi. */
  const pages =
    scan || data.exact ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className={cn('space-y-1.5', result.isFetching && 'opacity-60')}>
      {!data.exact && (
        <p className="rounded-xl bg-warn/[0.09] px-3.5 py-2.5 text-2xs leading-relaxed text-warn">
          {t('groups.tree.partialList')}
        </p>
      )}

      {data.items.map((group) => (
        <GroupRow
          key={group.id}
          group={group}
          selected={selection.has(group.id)}
          onSelect={() => selection.toggle(group)}
          showAgent={showAgent}
          showRegion={showRegion}
          actions={actions}
        />
      ))}

      {pages > 1 && (
        <div className="flex items-center justify-between gap-3 px-1 pt-1">
          <span className="tnum text-2xs text-muted">
            {t('groups.tree.range', {
              from: formatNumber(from),
              to: formatNumber(to),
              total: formatNumber(data.total),
            })}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="size-7"
              disabled={page <= 1}
              aria-label={t('groups.tree.prevPage')}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="size-3.5" />
            </Button>
            <span className="tnum px-1 text-2xs text-muted">
              {page} / {pages}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="size-7"
              disabled={page >= pages}
              aria-label={t('groups.tree.nextPage')}
              onClick={() => setPage((p) => Math.min(pages, p + 1))}
            >
              <ChevronRight className="size-3.5" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Bitta guruh qatori ──────────────────────────────────── */

function GroupRow({
  group,
  selected,
  onSelect,
  showAgent,
  showRegion,
  actions,
}: {
  group: TelegramGroup
  selected: boolean
  onSelect: () => void
  showAgent: boolean
  showRegion: boolean
  actions: GroupRowActions
}) {
  const { t } = useTranslation()
  const fmt = useDateFormat()
  const { canWrite, sendingId, onEdit, onDelete, onSend } = actions

  const sendable = canSendSurvey(group)
  const removable = canDelete(group)
  const sending = sendingId === group.id

  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-xl bg-surface p-2.5 shadow-xs',
        'transition-colors duration-250 ease-ios',
        selected && 'bg-accent-soft',
        !group.is_active && 'opacity-55',
      )}
    >
      {canWrite && (
        <label className="flex shrink-0 cursor-pointer items-center pl-0.5">
          <input
            type="checkbox"
            checked={selected}
            onChange={onSelect}
            aria-label={t('groups.tree.selectRow', { title: group.title })}
            className="size-4 cursor-pointer rounded-md accent-[hsl(var(--accent))]"
          />
        </label>
      )}

      <span
        className={cn(
          'icon-tile size-9 shrink-0',
          group.region ? 'text-accent' : 'text-muted',
        )}
      >
        <Users2 className="size-4" />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="truncate text-xs font-medium">{group.title}</span>

          {/* Qo'lda ushlab turilgan qator — avtomatika unga tegmaydi */}
          {isManual(group) && (
            <Badge tone="accent" title={t('groups.tree.manualHint')}>
              <Hand className="size-3" />
              {t('groups.tree.manual')}
            </Badge>
          )}
          {!group.is_active && <Badge tone="neutral">{t('groups.inactive')}</Badge>}
          {(group.bot_status === 'left' || group.bot_status === 'kicked') && (
            <Badge tone="bad">
              <Bot className="size-3" />
              {t(`groups.botStatus.${group.bot_status}`)}
            </Badge>
          )}
        </div>

        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-2xs text-muted">
          <span className="tnum">{group.chat_id}</span>

          {showAgent && (
            <span className="flex items-center gap-1">
              ·
              {group.agent_id && group.agent_name ? (
                <>
                  <Avatar
                    name={group.agent_name}
                    color={group.agent_color ?? undefined}
                    size="sm"
                  />
                  <span className="truncate">{group.agent_name}</span>
                </>
              ) : (
                <span className="text-warn">{t('groups.noAgent')}</span>
              )}
            </span>
          )}

          {showRegion &&
            (group.region ? (
              <span className="flex items-center gap-0.5 text-accent">
                · <MapPin className="size-3" />
                {group.region}
              </span>
            ) : (
              <span>· {t('groups.tree.regionlessShort')}</span>
            ))}

          {/* A'zolar soni — oddiy ma'lumot, hech narsani tasniflamaydi */}
          {group.member_count != null && (
            <span className="tnum">
              · {t('groups.membersShort', { count: group.member_count })}
            </span>
          )}

          <span>
            ·{' '}
            {group.last_survey_at ? fmt.date(group.last_survey_at) : t('groups.never')}
          </span>

          {group.survey_count > 0 && (
            <span className="tnum">
              · {formatNumber(group.survey_count)}
              <span className="opacity-50">/</span>
              {formatNumber(group.response_count)}
            </span>
          )}
        </div>
      </div>

      {canWrite && (
        <div className="flex shrink-0 items-center justify-end gap-1">
          <Button
            variant="ghost"
            size="sm"
            disabled={!sendable || sending}
            title={sendable ? t('groups.sendSurvey') : t('groups.sendBlocked')}
            onClick={() => onSend(group)}
          >
            <Send className="size-3.5" />
            <span className="max-2xl:hidden">
              {sending ? t('groups.sending') : t('groups.sendSurvey')}
            </span>
          </Button>

          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            title={group.region ? t('groups.edit') : t('groups.bind')}
            onClick={() => onEdit(group)}
          >
            {group.region ? <Pencil className="size-3.5" /> : <Link2 className="size-3.5" />}
          </Button>

          {/* O'chirish faqat bot guruhdan chiqarilgan bo'lsa — backend qoidasi */}
          {removable && (
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-bad hover:bg-bad/10 hover:text-bad"
              title={t('groups.delete')}
              onClick={() => onDelete(group)}
            >
              <Trash2 className="size-3.5" />
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
