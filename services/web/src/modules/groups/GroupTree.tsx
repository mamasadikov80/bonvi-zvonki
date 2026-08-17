/**
 * Daraxt: sotuvchi → hudud → guruhlar.
 *
 * Nega daraxt: har bir mijoz uchun alohida guruh ochilgan, ya'ni
 * ~1000 ta guruh. Yassi ro'yxat bunday miqyosda o'qib bo'lmaydigan
 * narsa. Daraxt esa savolni ikki bosqichga bo'ladi: «kimda?» va
 * «qayerda?» — javob esa tugunni ochmasdan, sanoqlardan ko'rinadi.
 *
 * IKKI QOIDA:
 *   1. Yopiq tugun uchun bitta ham guruh tortilmaydi. Sanoqlar
 *      `GET /groups/tree` dan keladi — u bitta yengil so'rov.
 *   2. Bir vaqtda faqat BITTA hudud tuguni ochiq turadi. Shuning
 *      uchun ekranda 50 tadan ortiq guruh qatori hech qachon
 *      bo'lmaydi, admin nechta tugunni bosishidan qat'i nazar.
 *
 * «Hududsiz» tugun — xato emas, NAVBAT. Unda ikki xil guruh yotadi:
 * hali saralanmaganlari va ataylab chetda qoldirilganlari (mijozsiz
 * ichki guruhlar). Ikkalasiga ham so'rovnoma yuborilmaydi — tugun
 * shu oqibatni ochiq yozib turadi.
 */

import { ChevronRight, Info, MapPin, MousePointerClick, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  nodeKey,
  sortRegionNodes,
  type GroupsQuery,
  type TreeAgentNode,
  type TreeRegionNode,
} from '@/modules/groups/api'
import { GroupList, type GroupRowActions, type Selection } from '@/modules/groups/GroupList'
import { EnrollmentNotice } from '@/modules/groups/EnrollmentNotice'
import { cn } from '@/shared/lib/utils'
import { Avatar } from '@/shared/ui/dataviz'
import { Badge, Button } from '@/shared/ui/primitives'

export interface TreeCallbacks {
  openAgents: Set<string>
  onToggleAgent: (agentId: string) => void
  /** `null` — hamma hudud tugunlari yopiq */
  openRegion: string | null
  onToggleRegion: (key: string | null) => void
  /** Tugundagi barcha guruhlarni tanlaydi (sahifadagilarni emas) */
  onSelectAll: (key: string, query: GroupsQuery) => void
  /** Tanlab, darhol «hudud biriktirish» oynasini ochadi */
  onAssignRegion: (key: string, query: GroupsQuery) => void
  /** Tanlanayotgan tugun kaliti — tugma «kutmoqda» holatida turadi */
  busyKey: string | null
  includeInactive: boolean
  selection: Selection
  actions: GroupRowActions
}

/* ── Xodim tuguni ────────────────────────────────────────── */

export function AgentNode({
  agent,
  tree,
}: {
  agent: TreeAgentNode
  tree: TreeCallbacks
}) {
  const { t } = useTranslation()
  const open = tree.openAgents.has(agent.agent_id)

  const regions = sortRegionNodes(agent.regions)
  const regionless = regions.find((node) => node.region === null)
  const named = regions.filter((node) => node.region !== null)
  const responses = regions.reduce((sum, node) => sum + node.response_count, 0)

  const regionlessQuery: GroupsQuery = {
    agent_id: agent.agent_id,
    has_region: false,
    include_inactive: tree.includeInactive,
  }

  return (
    <div
      className={cn(
        'overflow-hidden rounded-2xl bg-surface-2/40',
        'transition-colors duration-250 ease-ios',
        open && 'bg-surface-2/70',
      )}
    >
      <div className="flex items-center gap-2 p-2.5">
        <button
          type="button"
          onClick={() => tree.onToggleAgent(agent.agent_id)}
          aria-expanded={open}
          className={cn(
            'flex min-w-0 flex-1 items-center gap-3 rounded-xl px-1.5 py-1 text-left',
            'transition-colors duration-250 ease-ios hover:bg-surface/60',
          )}
        >
          <ChevronRight
            className={cn(
              'size-4 shrink-0 text-muted transition-transform duration-250 ease-ios',
              open && 'rotate-90',
            )}
          />

          <Avatar
            name={agent.full_name}
            color={agent.color ?? undefined}
            src={agent.avatar_url}
            size="md"
          />

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="truncate text-sm font-semibold">{agent.full_name}</span>
              {!agent.enrolled && (
                <Badge tone="warn">{t('groups.tree.notEnrolled')}</Badge>
              )}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-2xs text-muted">
              <span className="tnum">
                {t('groups.groupCount', { count: agent.group_count })}
              </span>
              <span className="opacity-50">·</span>
              <span className="tnum">
                {t('groups.tree.responseCount', { count: responses })}
              </span>
              {named.length > 0 && (
                <>
                  <span className="opacity-50">·</span>
                  <span className="tnum text-accent">
                    {t('groups.regionCount', { count: named.length })}
                  </span>
                </>
              )}
            </div>
          </div>
        </button>

        {/* Hududsizlar — xodim tugunidan bir bosishda ochiladi */}
        {regionless && regionless.group_count > 0 && (
          <Button
            variant="secondary"
            size="sm"
            className="shrink-0"
            title={t('groups.tree.regionlessHint')}
            onClick={() => {
              if (!open) tree.onToggleAgent(agent.agent_id)
              tree.onToggleRegion(nodeKey(agent.agent_id, null))
            }}
          >
            <MapPin className="size-3.5" />
            {t('groups.tree.regionlessCount', { count: regionless.group_count })}
          </Button>
        )}
      </div>

      {open && (
        <div className="relative space-y-1.5 px-2.5 pb-2.5 pl-8">
          {/* Daraja chizig'i — «bu tugunlar shu xodimniki» degani ko'rinsin.
              Chapdagi 24px — yuqoridagi chevron markazi, ya'ni chiziq
              ochilgan uchburchakdan pastga tushadi. */}
          <span
            aria-hidden
            className="pointer-events-none absolute bottom-4 left-6 top-0 w-px bg-border"
          />

          {!agent.enrolled && <EnrollmentNotice name={agent.full_name} />}

          {/* Avtomatik biriktirish qoidasi. Bot yangi guruhga hududni
              faqat xodimda AYNAN BITTA hudud bo'lsa qo'yadi — bu qoida
              serverda (`GroupService.autobind`), lekin uning oqibatini
              admin aynan shu yerda ko'rishi kerak: aks holda «nega bu
              guruh hududsiz qoldi?» degan savol javobsiz qoladi. */}
          <p className="flex items-start gap-2 rounded-xl bg-surface/70 px-3.5 py-2.5 text-2xs leading-relaxed text-muted">
            <Info className="mt-px size-3.5 shrink-0 text-accent" />
            <span>
              {named.length === 1
                ? t('groups.tree.autoRuleOne', { region: named[0].region })
                : named.length > 1
                  ? t('groups.tree.autoRuleMany', { count: named.length })
                  : t('groups.tree.autoRuleNone')}
            </span>
          </p>

          {!regions.length && (
            <p className="rounded-xl bg-surface/70 px-3.5 py-3 text-2xs text-muted">
              {agent.enrolled
                ? t('groups.tree.agentEmpty')
                : t('groups.tree.agentEmptyNotEnrolled')}
            </p>
          )}

          {named.map((node) => (
            <RegionNode
              key={node.region}
              agentId={agent.agent_id}
              node={node}
              tree={tree}
            />
          ))}

          {regionless && (
            <RegionNode
              agentId={agent.agent_id}
              node={regionless}
              tree={tree}
              quickAction={
                <Button
                  size="sm"
                  className="shrink-0"
                  disabled={tree.busyKey !== null}
                  onClick={() =>
                    tree.onAssignRegion(
                      nodeKey(agent.agent_id, null),
                      regionlessQuery,
                    )
                  }
                >
                  <Sparkles className="size-3.5" />
                  {t('groups.tree.assignRegionAll', { count: regionless.group_count })}
                </Button>
              }
            />
          )}
        </div>
      )}
    </div>
  )
}

/* ── Hudud tuguni ────────────────────────────────────────── */

function RegionNode({
  agentId,
  node,
  tree,
  quickAction,
}: {
  agentId: string
  node: TreeRegionNode
  tree: TreeCallbacks
  quickAction?: React.ReactNode
}) {
  const { t } = useTranslation()

  const key = nodeKey(agentId, node.region)
  const open = tree.openRegion === key
  const regionless = node.region === null

  const query: GroupsQuery = regionless
    ? { agent_id: agentId, has_region: false, include_inactive: tree.includeInactive }
    : {
        agent_id: agentId,
        region: node.region ?? undefined,
        include_inactive: tree.includeInactive,
      }

  return (
    <div
      className={cn(
        'overflow-hidden rounded-xl bg-surface/70',
        regionless && 'bg-warn/[0.06]',
        open && 'shadow-xs',
      )}
    >
      <div className="flex items-center gap-2 p-2">
        <button
          type="button"
          onClick={() => tree.onToggleRegion(open ? null : key)}
          aria-expanded={open}
          className={cn(
            'flex min-w-0 flex-1 items-center gap-2.5 rounded-lg px-1.5 py-1 text-left',
            'transition-colors duration-250 ease-ios hover:bg-surface-2/50',
          )}
        >
          <ChevronRight
            className={cn(
              'size-3.5 shrink-0 text-muted transition-transform duration-250 ease-ios',
              open && 'rotate-90',
            )}
          />
          <span
            className={cn(
              'icon-tile size-7 shrink-0',
              regionless ? 'text-warn' : 'text-accent',
            )}
          >
            <MapPin className="size-3.5" />
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2">
              <span
                className={cn(
                  'truncate text-xs font-medium',
                  regionless && 'text-warn',
                )}
              >
                {node.region ?? t('groups.tree.regionless')}
              </span>
              <span className="tnum text-2xs text-muted">
                {t('groups.groupCount', { count: node.group_count })}
              </span>
              {!regionless && (
                <span className="tnum text-2xs text-muted">
                  · {t('groups.tree.responseCount', { count: node.response_count })}
                </span>
              )}
            </div>
            {regionless && (
              <p className="mt-0.5 text-2xs leading-relaxed text-muted">
                {t('groups.tree.regionlessConsequence')}
              </p>
            )}
          </div>
        </button>

        {quickAction}
      </div>

      {open && (
        <div className="relative space-y-2 px-2 pb-2.5 pl-7">
          {/* Xodim tugunidagi bilan bir xil chiziq, bir daraja ichkarida */}
          <span
            aria-hidden
            className="pointer-events-none absolute bottom-3 left-[21px] top-0 w-px bg-border"
          />

          {/* Tugundagi HAMMASINI tanlash — sahifadagini emas.
              40 ta guruh uchun 40 ta oyna ochilmasligi kerak. */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-2xs text-muted">
              {t('groups.tree.selectHint')}
            </span>
            <Button
              variant="ghost"
              size="sm"
              disabled={tree.busyKey !== null}
              onClick={() => tree.onSelectAll(key, query)}
            >
              <MousePointerClick className="size-3.5" />
              {tree.busyKey === key
                ? t('groups.tree.selecting')
                : t('groups.tree.selectAll', { count: node.group_count })}
            </Button>
          </div>

          <GroupList
            query={query}
            emptyMessage={t('groups.tree.nodeEmpty')}
            selection={tree.selection}
            actions={tree.actions}
          />
        </div>
      )}
    </div>
  )
}
