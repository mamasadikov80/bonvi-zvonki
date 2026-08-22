/**
 * Mijozlar ro'yxati.
 *
 * Bu bo'lim boshqa savolga javob beradi: tizimning qolgan qismi
 * XODIM darajasida ishlaydi («kim qanday ishlayapti»), bu yerda esa
 * kesim MIJOZ bo'yicha — kim bilan qancha gaplashilgan, nechtasiga
 * javob berilmagan, oxirgi aloqa qachon bo'lgan.
 *
 * ⚠️ Mijoz alohida yozuv EMAS: u qo'ng'iroqdagi raqam bo'yicha
 * yig'iladi (`clients/application/directory.py`). Shuning uchun
 * «mijoz qo'shish» tugmasi yo'q va bo'lmaydi — ro'yxat MoyZvonki
 * sinxronizatsiyasi bilan o'zi to'ladi.
 */

import { ChevronLeft, ChevronRight, Tag } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import type { AnalyticsQuery } from '@/modules/analytics/api'
import { useAuth } from '@/modules/auth/store'
import {
  useClients,
  type ClientScope,
  type ClientSort,
  type ClientsQuery,
} from '@/modules/clients/api'
import { FilterBar } from '@/modules/dashboard/components/FilterBar'
import { Page, PageHeader } from '@/shared/layout/Page'
import {
  rangeToQuery,
  resolvePreset,
  useDateFormat,
  type DateRange,
} from '@/shared/lib/date'
import {
  cn,
  formatLongDuration,
  formatNumber,
  scoreTone,
  TONE_CLASS,
} from '@/shared/lib/utils'
import { Avatar, MiniBar } from '@/shared/ui/dataviz'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Segmented,
  Select,
  Skeleton,
} from '@/shared/ui/primitives'
import { SearchInput } from '@/shared/ui/SearchInput'
import { SortHeader, type SortState } from '@/shared/ui/SortHeader'

/** Sahifadagi qatorlar soni — foydalanuvchi tanlaydi. */
const PAGE_SIZES = [20, 50] as const

/** Saralanadigan ustunlar. Raqamlilar avval kattadan kichikka:
 *  «eng ko'p gaplashilgan mijoz» ko'proq so'raladigan savol. */
const COLUMNS: {
  field: ClientSort
  labelKey: string
  align?: 'left' | 'right'
  firstOrder?: 'asc' | 'desc'
}[] = [
  { field: 'name', labelKey: 'clients.colClient' },
  { field: 'calls', labelKey: 'clients.colCalls', align: 'right', firstOrder: 'desc' },
  { field: 'missed', labelKey: 'clients.colMissed', align: 'right', firstOrder: 'desc' },
  { field: 'talk', labelKey: 'clients.colTalk', align: 'right', firstOrder: 'desc' },
  { field: 'score', labelKey: 'clients.colScore', align: 'right', firstOrder: 'desc' },
  {
    field: 'last_call',
    labelKey: 'clients.colLastCall',
    align: 'right',
    firstOrder: 'desc',
  },
]

export function ClientsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const fmt = useDateFormat()

  const isSales = user?.role === 'sales'

  /* Davr — tanlagichda nima yozilgan bo'lsa, so'rovda ham o'sha.
     Sukut bo'yicha «Shu yil»: bazadagi hamma qo'ng'iroq shu oynaga
     tushadi, ya'ni ro'yxat to'liq boshlanadi va shu bilan birga
     tanlagich yolg'on gapirmaydi. */
  const [range, setRange] = useState<DateRange>(() => resolvePreset('thisYear'))
  const [filters, setFilters] = useState<AnalyticsQuery>(() =>
    rangeToQuery(resolvePreset('thisYear')),
  )

  const [sort, setSort] = useState<SortState<ClientSort>>({
    field: 'last_call',
    order: 'desc',
  })
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0])
  const [search, setSearch] = useState('')
  const [applied, setApplied] = useState('')
  const [scope, setScope] = useState<ClientScope>('clients')

  const query: ClientsQuery = {
    page,
    page_size: pageSize,
    date_from: filters.date_from,
    date_to: filters.date_to,
    agent_ids: filters.agent_ids,
    regions: filters.regions,
    scope,
    search: applied || undefined,
    sort: sort.field,
    order: sort.order,
  }

  const clients = useClients(query)
  const total = clients.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / pageSize))

  /* Har qanday o'zgarish birinchi sahifaga qaytaradi — aks holda
     5-sahifada turib filtrni toraytirgan odam bo'sh jadval ko'rardi
     va uni «ma'lumot yo'q» deb o'qirdi. */
  const reset = <T,>(apply: (value: T) => void) => (value: T) => {
    apply(value)
    setPage(1)
  }

  return (
    <Page>
      <PageHeader
        title={t('clients.title')}
        subtitle={
          clients.data ? t('clients.found', { count: total }) : t('clients.subtitle')
        }
      />

      <FilterBar
        value={filters}
        onChange={reset(setFilters)}
        range={range}
        onRangeChange={setRange}
        showAgentFilter={!isSales}
        showRegionFilter={!isSales}
      />

      <Card>
        {/* ── Qidiruv va ko'rinish ─────────────────────────────
            Jadvalning ustida turadi: bularning ikkalasi ham
            RO'YXATGA tegishli (nimani va nechtasini ko'rsatish),
            yuqoridagi panel esa DAVR va kesimga. */}
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
          <SearchInput
            className="min-w-[240px] flex-1"
            placeholder={t('clients.searchPlaceholder')}
            value={search}
            onChange={reset((next: string) => {
              setSearch(next)
              setApplied(next.trim())
            })}
          />

          {/* Kim ro'yxatga kiradi. Ichki suhbatlar sukut bo'yicha
              chiqarilgan — hamkasb mijoz emas. Bu YASHIRIN filtr
              emas: tanlov ekranda ko'rinib turadi. */}
          <Select
            icon={Tag}
            active={scope !== 'clients'}
            className="w-48"
            value={scope}
            onChange={(e) => reset(setScope)(e.target.value as ClientScope)}
          >
            <option value="clients">{t('clients.scope.clients')}</option>
            <option value="internal">{t('clients.scope.internal')}</option>
            <option value="all">{t('clients.scope.all')}</option>
          </Select>

          <Segmented
            value={String(pageSize)}
            onChange={(value) => reset(setPageSize)(Number(value))}
            items={PAGE_SIZES.map((size) => ({
              value: String(size),
              label: t('clients.perPage', { count: size }),
            }))}
          />
        </div>

        {clients.isLoading ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 10 }).map((_, i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </div>
        ) : !clients.data?.items.length ? (
          <EmptyState
            message={t('table.empty')}
            hint={applied ? t('clients.emptySearchHint') : t('clients.emptyHint')}
            action={
              applied
                ? {
                    label: t('clients.clearSearch'),
                    onClick: () => {
                      setSearch('')
                      setApplied('')
                      setPage(1)
                    },
                  }
                : undefined
            }
          />
        ) : (
          <div className="scroll-x">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  {COLUMNS.map((column) => (
                    <SortHeader
                      key={column.field}
                      field={column.field}
                      label={t(column.labelKey)}
                      align={column.align}
                      firstOrder={column.firstOrder}
                      state={sort}
                      onChange={reset(setSort)}
                    />
                  ))}
                  {/* Xodim ustuni saralanmaydi: u yig'ma qiymat
                      («eng ko'p gaplashgani») va u bo'yicha saralash
                      ma'noli tartib bermaydi */}
                  <th className="px-4 py-3 text-2xs font-medium uppercase tracking-wider text-muted">
                    {t('clients.colAgent')}
                  </th>
                  <th className="w-10 px-2 py-3" />
                </tr>
              </thead>
              <tbody>
                {clients.data.items.map((row) => {
                  const tone = scoreTone(row.avg_score) as
                    | 'accent'
                    | 'good'
                    | 'warn'
                    | 'bad'
                  const last = new Date(row.last_call_at)

                  return (
                    <tr
                      key={row.key}
                      onClick={() => navigate(`/clients/${row.key}`)}
                      className="cursor-pointer border-b border-border/60 transition-colors last:border-0 hover:bg-surface-2/60"
                    >
                      {/* Mijoz: nomi bo'lmasa raqamning o'zi sarlavha
                          bo'ladi — «—» hech narsa bermaydi, raqam esa
                          terib ko'rsa ham, CRM da qidirsa ham ishlaydi */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <Avatar name={row.name || row.phone || '?'} size="sm" />
                          <div className="min-w-0">
                            <div className="truncate font-medium">
                              {row.name || row.phone || row.key}
                            </div>
                            {row.name && row.phone && (
                              <div className="tnum text-2xs text-muted">
                                {row.phone}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Jami — kiruvchi/chiquvchi taqsimoti ostida.
                          Alohida ustunlar jadvalni kengaytirardi, bu
                          yerda esa ikkala son bir qarashda o'qiladi. */}
                      <td className="px-4 py-3 text-right">
                        <div className="tnum font-medium">
                          {formatNumber(row.calls_total)}
                        </div>
                        <div className="tnum text-2xs text-muted">
                          {t('clients.inOut', {
                            inbound: row.inbound,
                            outbound: row.outbound,
                          })}
                        </div>
                      </td>

                      <td
                        className={cn(
                          'tnum px-4 py-3 text-right',
                          row.missed ? 'font-medium text-bad' : 'text-muted',
                        )}
                      >
                        {formatNumber(row.missed)}
                      </td>

                      <td className="tnum px-4 py-3 text-right text-muted">
                        {formatLongDuration(row.talk_seconds)}
                      </td>

                      {/* Ball — faqat baholangan suhbatlar bo'yicha.
                          Bahosi yo'q mijoz «0» emas, «—»: nol yomon
                          ish degan yolg'on ma'no berardi. */}
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2">
                          <span className={cn('tnum font-semibold', TONE_CLASS[tone])}>
                            {row.avg_score != null ? Math.round(row.avg_score) : '—'}
                          </span>
                          <MiniBar value={row.avg_score} tone={tone} width={44} />
                        </div>
                      </td>

                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        <div className="tnum text-sm">{fmt.date(last)}</div>
                        <div className="tnum text-2xs text-muted">{fmt.time(last)}</div>
                      </td>

                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <Avatar
                            name={row.main_agent_name || '—'}
                            color={row.main_agent_color ?? undefined}
                            size="sm"
                          />
                          <span className="truncate text-muted">
                            {row.main_agent_name || '—'}
                          </span>
                          {/* Nechta BOSHQA xodim gaplashgan. Bu son
                              rahbarning birinchi savoli bo'ladi:
                              mijoz bir necha qo'ldan o'tganmi? */}
                          {row.agent_count > 1 && (
                            <Badge>+{row.agent_count - 1}</Badge>
                          )}
                        </div>
                      </td>

                      <td className="px-2 py-3 text-muted">
                        <ChevronRight className="size-4" />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {pages > 1 && (
          <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-3">
            <span className="text-xs text-muted">
              {t('common.page')} <span className="tnum">{page}</span> {t('common.of')}{' '}
              <span className="tnum">{formatNumber(pages)}</span>
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft className="size-3.5" />
                {t('common.prev')}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                {t('common.next')}
                <ChevronRight className="size-3.5" />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </Page>
  )
}
