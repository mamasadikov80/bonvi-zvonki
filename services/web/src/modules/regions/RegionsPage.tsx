/**
 * Hududlar sahifasi — ro'yxatni admin boshqaradi.
 *
 * Nima uchun bor: ilgari hududlar kodda qotib turgan viloyatlar
 * ro'yxati edi. Bonvi esa bitta viloyatni bir nechta alohida hududga
 * bo'ladi («Samarqand shimol», «Samarqand janub»), shuning uchun
 * ro'yxat o'zgaruvchan bo'lishi shart.
 *
 * Sahifaning asosiy javobi — «bu hudud QAYERDA ishlatilmoqda».
 * O'chirish tugmasini bosishdan oldin admin oqibatni ko'rib turishi
 * kerak: nechta xodim, mijoz va guruh shu nomga tayanadi.
 */

import {
  Building2,
  CheckCircle2,
  MapPin,
  MessagesSquare,
  Pencil,
  Plus,
  Trash2,
  Users,
  X,
} from 'lucide-react'
import { useMemo, useState, type ComponentType, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuth } from '@/modules/auth/store'
import {
  errorMessage,
  sortRegions,
  usageTotal,
  useRegions,
  type Region,
} from '@/modules/regions/api'
import { RegionDeleteModal } from '@/modules/regions/RegionDeleteModal'
import { RegionModal } from '@/modules/regions/RegionModal'
import { Page, PageHeader } from '@/shared/layout/Page'
import { cn, formatNumber } from '@/shared/lib/utils'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Segmented,
  Skeleton,
} from '@/shared/ui/primitives'
import { SortHeader, type SortState } from '@/shared/ui/SortHeader'

type StatusFilter = 'all' | 'active' | 'inactive'
type SortField = 'name' | 'status' | 'order' | 'usage'

export function RegionsPage() {
  const { t } = useTranslation()
  const { can } = useAuth()

  const canWrite = can('regions:write')

  // Bu sahifada faolsizlar ham ko'rinadi — admin aynan ularni boshqaradi
  const regions = useRegions(true)

  const [status, setStatus] = useState<StatusFilter>('all')
  const [sort, setSort] = useState<SortState<SortField>>({
    field: 'order',
    order: 'asc',
  })
  const [editing, setEditing] = useState<Region | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Region | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const rows = useMemo(() => sortRegions(regions.data ?? []), [regions.data])

  const stats = useMemo(() => {
    let active = 0
    let unused = 0
    for (const region of rows) {
      if (region.is_active) active += 1
      if (usageTotal(region.usage) === 0) unused += 1
    }
    return { total: rows.length, active, unused }
  }, [rows])

  const filtered = useMemo(() => {
    if (status === 'active') return rows.filter((r) => r.is_active)
    if (status === 'inactive') return rows.filter((r) => !r.is_active)
    return rows
  }, [rows, status])

  const sorted = useMemo(() => {
    const direction = sort.order === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => {
      const left = sortValue(a, sort.field)
      const right = sortValue(b, sort.field)
      if (typeof left === 'string' && typeof right === 'string') {
        return left.localeCompare(right) * direction
      }
      return ((left as number) - (right as number)) * direction
    })
  }, [filtered, sort])

  /* ── Xatolik — "hudud yo'q" deb aldamaymiz ─────────────── */
  if (regions.isError) {
    return (
      <Page>
        <PageHeader title={t('regions.title')} />
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-16 text-center">
            <p className="text-sm font-medium">{t('common.error')}</p>
            <p className="max-w-md text-xs leading-relaxed text-muted">
              {errorMessage(regions.error, '')}
            </p>
            <Button variant="secondary" size="sm" onClick={() => void regions.refetch()}>
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
        title={t('regions.title')}
        subtitle={t('regions.subtitle', {
          count: stats.total,
          active: stats.active,
        })}
        actions={
          canWrite ? (
            <Button onClick={() => setEditing('new')}>
              <Plus className="size-4" />
              {t('regions.add')}
            </Button>
          ) : null
        }
      />

      {/* Amal natijasi — nom kaskad bo'lib tarqalganda ayniqsa muhim */}
      {notice && (
        <div
          role="status"
          className="animate-scale-in flex items-start gap-2.5 rounded-2xl bg-good/10 px-4 py-3 text-xs leading-relaxed text-good"
        >
          <CheckCircle2 className="mt-px size-4 shrink-0" />
          <span className="flex-1">{notice}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            aria-label={t('common.close')}
            className="shrink-0 rounded-md p-0.5 opacity-60 transition-opacity duration-250 ease-ios hover:opacity-100"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}

      {/* ── Yig'ma ko'rsatkichlar ─────────────────────────── */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 2xl:gap-4">
        <SummaryTile
          icon={MapPin}
          label={t('regions.tileTotal')}
          loading={regions.isLoading}
        >
          <span className="tnum text-2xl font-semibold leading-none">
            {formatNumber(stats.total)}
          </span>
        </SummaryTile>

        <SummaryTile
          icon={CheckCircle2}
          label={t('regions.tileActive')}
          tone="good"
          loading={regions.isLoading}
        >
          <span className="tnum text-2xl font-semibold leading-none text-good">
            {formatNumber(stats.active)}
          </span>
          <p className="mt-2 text-2xs text-muted">{t('regions.tileActiveHint')}</p>
        </SummaryTile>

        <SummaryTile
          icon={Trash2}
          label={t('regions.tileUnused')}
          loading={regions.isLoading}
        >
          <span className="tnum text-2xl font-semibold leading-none">
            {formatNumber(stats.unused)}
          </span>
          <p className="mt-2 text-2xs text-muted">{t('regions.tileUnusedHint')}</p>
        </SummaryTile>
      </div>

      {/* ── Ro'yxat ───────────────────────────────────────── */}
      <Card>
        <CardHeader
          title={t('regions.list')}
          hint={canWrite ? t('regions.listHint') : t('regions.readOnly')}
          action={
            <Segmented
              value={status}
              onChange={setStatus}
              items={[
                { value: 'all' as StatusFilter, label: t('regions.filterAll') },
                { value: 'active' as StatusFilter, label: t('regions.filterActive') },
                {
                  value: 'inactive' as StatusFilter,
                  label: t('regions.filterInactive'),
                },
              ]}
            />
          }
        />

        {regions.isLoading ? (
          <CardBody className="space-y-2 pt-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </CardBody>
        ) : !rows.length ? (
          <CardBody className="flex flex-col items-center gap-4 py-14 text-center">
            <span className="icon-tile size-12 text-accent">
              <MapPin className="size-5" />
            </span>
            <div>
              <p className="text-sm font-medium">{t('regions.empty')}</p>
              <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
                {t('regions.emptyHint')}
              </p>
            </div>
            {canWrite && (
              <Button onClick={() => setEditing('new')}>
                <Plus className="size-4" />
                {t('regions.add')}
              </Button>
            )}
          </CardBody>
        ) : !sorted.length ? (
          <CardBody className="pt-4">
            <EmptyState message={t('regions.emptyFilter')} />
          </CardBody>
        ) : (
          <div className="scroll-x mt-3">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted">
                  <SortHeader
                    field="name"
                    label={t('regions.colName')}
                    state={sort}
                    onChange={setSort}
                  />
                  <SortHeader
                    field="status"
                    label={t('regions.colStatus')}
                    state={sort}
                    onChange={setSort}
                  />
                  <SortHeader
                    field="order"
                    label={t('regions.colOrder')}
                    state={sort}
                    onChange={setSort}
                    align="right"
                  />
                  <SortHeader
                    field="usage"
                    label={t('regions.colUsage')}
                    state={sort}
                    onChange={setSort}
                    firstOrder="desc"
                  />
                  <th className="w-px px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {sorted.map((region) => (
                  <tr
                    key={region.id}
                    className={cn(
                      'transition-colors duration-250 ease-ios hover:bg-surface-2/50',
                      !region.is_active && 'opacity-55',
                    )}
                  >
                    {/* Nom + izoh */}
                    <td className="px-4 py-3">
                      <div className="flex min-w-0 items-center gap-2.5">
                        <span
                          className={cn(
                            'icon-tile size-8 shrink-0',
                            region.is_active ? 'text-accent' : 'text-muted',
                          )}
                        >
                          <MapPin className="size-4" />
                        </span>
                        <div className="min-w-0">
                          <div className="truncate font-medium">{region.name}</div>
                          {region.note && (
                            <div className="truncate text-2xs text-muted">
                              {region.note}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Holat */}
                    <td className="px-4 py-3">
                      <Badge tone={region.is_active ? 'good' : 'neutral'}>
                        {region.is_active ? t('regions.active') : t('regions.inactive')}
                      </Badge>
                    </td>

                    {/* Tartib */}
                    <td className="tnum px-4 py-3 text-right text-muted">
                      {region.sort_order}
                    </td>

                    {/* Qayerda ishlatilmoqda — sahifaning asosiy javobi */}
                    <td className="px-4 py-3">
                      <UsageCells region={region} />
                    </td>

                    {/* Amallar */}
                    <td className="px-4 py-3">
                      {canWrite && (
                        <div className="flex shrink-0 items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8"
                            title={t('regions.edit')}
                            onClick={() => setEditing(region)}
                          >
                            <Pencil className="size-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-bad hover:bg-bad/10 hover:text-bad"
                            title={t('regions.deleteTitle')}
                            onClick={() => setDeleting(region)}
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Qo'shish/tahrirlash — QOIDA bo'yicha faqat modalda */}
      <RegionModal
        target={editing}
        onClose={() => setEditing(null)}
        onDone={setNotice}
      />

      <RegionDeleteModal
        region={deleting}
        onClose={() => setDeleting(null)}
        onDone={setNotice}
      />
    </Page>
  )
}

/* ── Saralash qiymati ────────────────────────────────────── */

function sortValue(region: Region, field: SortField): string | number {
  switch (field) {
    case 'name':
      return region.name.toLowerCase()
    case 'status':
      return region.is_active ? 0 : 1
    case 'order':
      return region.sort_order
    case 'usage':
      return usageTotal(region.usage)
  }
}

/* ── Ishlatilish ustuni ──────────────────────────────────────
   Uchta manba alohida ko'rsatiladi: admin «12 ta mijoz» va
   «12 ta xodim» ni farqlay olishi kerak — oqibati boshqa. */

function UsageCells({ region }: { region: Region }) {
  const { t } = useTranslation()
  const usage = region.usage
  const total = usageTotal(usage)

  if (total === 0) {
    return <span className="text-2xs text-muted">{t('regions.unused')}</span>
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <UsageChip
        icon={Users}
        count={usage?.agents ?? 0}
        label={t('regions.usageAgents')}
      />
      <UsageChip
        icon={Building2}
        count={usage?.clients ?? 0}
        label={t('regions.usageClients')}
      />
      <UsageChip
        icon={MessagesSquare}
        count={usage?.groups ?? 0}
        label={t('regions.usageGroups')}
      />
    </div>
  )
}

function UsageChip({
  icon: Icon,
  count,
  label,
}: {
  icon: ComponentType<{ className?: string }>
  count: number
  label: string
}) {
  return (
    <Badge tone={count ? 'accent' : 'neutral'} title={`${count} ${label}`}>
      <Icon className="size-3" />
      <span className="tnum">{count}</span>
      <span className="sr-only">{label}</span>
    </Badge>
  )
}

/* ── Yig'ma plitka ───────────────────────────────────────── */

const TILE_TONE: Record<'accent' | 'good' | 'warn', string> = {
  accent: 'text-accent',
  good: 'text-good',
  warn: 'text-warn',
}

function SummaryTile({
  icon: Icon,
  label,
  tone = 'accent',
  loading,
  children,
}: {
  icon: ComponentType<{ className?: string }>
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
