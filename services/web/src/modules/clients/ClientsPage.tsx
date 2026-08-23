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

import {
  ArrowDownLeft,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Phone,
  Tag,
} from 'lucide-react'
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
import { Page } from '@/shared/layout/Page'
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
  Select,
  Skeleton,
} from '@/shared/ui/primitives'
import { SearchInput } from '@/shared/ui/SearchInput'
import { SortHeader, type SortState } from '@/shared/ui/SortHeader'

/** Sahifadagi qatorlar soni. Tanlov YO'Q — «Qo'ng'iroqlar» bo'limida
 *  ham xuddi shu 50 ta. Ikkita variantli tanlagich panelda joy egallardi,
 *  lekin javob beradigan savoli yo'q edi: 20 ta qator kam, 100 ta esa
 *  hech qachon so'ralmagan. */
const PAGE_SIZE = 50

/** Saralanadigan ustunlar. Raqamlilar avval kattadan kichikka:
 *  «eng ko'p gaplashilgan mijoz» ko'proq so'raladigan savol.
 *
 *  Sarlavha QISQA — uzuni ikki qatorga bo'linib, butun jadval
 *  qatorini balandlashtirardi. To'liq ma'nosi `titleKey` orqali
 *  kursor ostida qoladi, ya'ni hech narsa yo'qolmaydi. */
const COLUMNS: {
  field: ClientSort
  labelKey: string
  /** Qisqartirilgan sarlavhaning to'liq ma'nosi */
  titleKey?: string
  align?: 'left' | 'right'
  firstOrder?: 'asc' | 'desc'
}[] = [
  { field: 'name', labelKey: 'clients.colClient' },
  { field: 'calls', labelKey: 'clients.colCalls', align: 'right', firstOrder: 'desc' },
  {
    field: 'missed',
    labelKey: 'clients.colMissedShort',
    titleKey: 'clients.colMissed',
    align: 'right',
    firstOrder: 'desc',
  },
  { field: 'talk', labelKey: 'clients.colTalk', align: 'right', firstOrder: 'desc' },
  {
    field: 'score',
    labelKey: 'clients.colScoreShort',
    titleKey: 'clients.colScore',
    align: 'right',
    firstOrder: 'desc',
  },
  {
    field: 'last_call',
    labelKey: 'clients.colLastCallShort',
    titleKey: 'clients.colLastCall',
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
  const [search, setSearch] = useState('')
  const [applied, setApplied] = useState('')
  const [scope, setScope] = useState<ClientScope>('clients')

  const query: ClientsQuery = {
    page,
    page_size: PAGE_SIZE,
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
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  /* Har qanday o'zgarish birinchi sahifaga qaytaradi — aks holda
     5-sahifada turib filtrni toraytirgan odam bo'sh jadval ko'rardi
     va uni «ma'lumot yo'q» deb o'qirdi. */
  const reset = <T,>(apply: (value: T) => void) => (value: T) => {
    apply(value)
    setPage(1)
  }

  return (
    <Page>
      {/* Sarlavha bloki IXCHAM: son alohida qatorga tushmaydi, chunki
          u sarlavhaning izohi emas — o'sha ro'yxatning o'lchami.
          Bitta qatorda turgani sahifaning yuqorisidan ~24px bo'sh
          joyni oladi va jadval tezroq boshlanadi. */}
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
        <h1 className="text-xl font-semibold tracking-tight 2xl:text-2xl">
          {t('clients.title')}
        </h1>
        <p className="text-sm text-muted">
          {clients.data ? t('clients.found', { count: total }) : t('clients.subtitle')}
        </p>
      </div>

      {/* Filtrlar BITTA qatorda: davr/hudud/xodim umumiy paneldan,
          qidiruv va «kim ro'yxatga kiradi» esa shu sahifaga xos.
          Ilgari ular ikkita ustma-ust kartada turardi — bir xil
          ko'rinishdagi ikki qator jadvalni ekrandan pastga surardi,
          ammo mazmunan ular bitta savolning qismlari.

          «FILTRLAR» yorlig'i bu yerda YO'Q: qatorning boshida qidiruv
          turadi va yorliq uni chetga surib, hech nima tushuntirmasdi. */}
      <FilterBar
        value={filters}
        onChange={reset(setFilters)}
        range={range}
        onRangeChange={setRange}
        showAgentFilter={!isSales}
        showRegionFilter={!isSales}
        showLabel={false}
        leading={
          /* Qidiruv ENG CHAPDA va qolgan bo'sh joyni oladi: bu
             sahifada eng ko'p ishlatiladigan boshqaruv aynan u */
          <SearchInput
            className="min-w-[220px] flex-1"
            placeholder={t('clients.searchPlaceholder')}
            value={search}
            onChange={reset((next: string) => {
              setSearch(next)
              setApplied(next.trim())
            })}
          />
        }
      >
        {/* Kim ro'yxatga kiradi. Ichki suhbatlar sukut bo'yicha
            chiqarilgan — hamkasb mijoz emas. Bu YASHIRIN filtr
            emas: tanlov ekranda ko'rinib turadi. */}
        <Select
          icon={Tag}
          active={scope !== 'clients'}
          className="w-44"
          value={scope}
          onChange={(e) => reset(setScope)(e.target.value as ClientScope)}
        >
          <option value="clients">{t('clients.scope.clients')}</option>
          <option value="internal">{t('clients.scope.internal')}</option>
          <option value="all">{t('clients.scope.all')}</option>
        </Select>
      </FilterBar>

      <Card>
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
                      title={column.titleKey ? t(column.titleKey) : undefined}
                      align={column.align}
                      firstOrder={column.firstOrder}
                      state={sort}
                      onChange={reset(setSort)}
                      className="whitespace-nowrap"
                    />
                  ))}
                  {/* Xodim ustuni saralanmaydi: u yig'ma qiymat
                      («eng ko'p gaplashgani») va u bo'yicha saralash
                      ma'noli tartib bermaydi */}
                  <th className="whitespace-nowrap px-4 py-3 text-2xs font-medium uppercase tracking-wider text-muted">
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
                  /* Ro'yxatda sana HAR DOIM bor — guruh kamida bitta
                     qo'ng'iroqdan tuziladi. Tekshiruv turi uchun:
                     maydon kartochka bilan UMUMIY va u yerda bo'sh
                     davr bo'lishi mumkin. */
                  const last = row.last_call_at ? new Date(row.last_call_at) : null

                  return (
                    <tr
                      key={row.key}
                      /* Kesim manzilga QO'SHILADI: kartochka ham shu
                         kesimda ochilsin. Ichki raqam sukut kesimida
                         (`clients`) yo'q va `scope` siz havola 404
                         berardi — ro'yxatda ko'rinib turgan qator
                         bosilmas bo'lib qolardi. */
                      onClick={() =>
                        navigate(
                          scope === 'clients'
                            ? `/clients/${row.key}`
                            : `/clients/${row.key}?scope=${scope}`,
                        )
                      }
                      /* Balandlik QAT'IY: qatorlar mazmuniga qarab
                         (nomi bormi, raqamlari uzunmi) turlicha
                         cho'zilib, ro'yxat notekis ko'rinardi. 60px —
                         ikki qatorli katakning tabiiy o'lchami, ya'ni
                         hech narsa siqilmaydi. */
                      className="h-[60px] cursor-pointer border-b border-border/60 transition-colors last:border-0 hover:bg-surface-2/60"
                    >
                      {/* Mijoz: nomi bo'lmasa raqamning o'zi sarlavha
                          bo'ladi — «—» hech narsa bermaydi, raqam esa
                          terib ko'rsa ham, CRM da qidirsa ham ishlaydi */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          {/* Nomsiz mijozda bosh harf yo'q: raqamdan
                              olingani «+» bo'lib chiqardi va bu avatar
                              emas, xato kabi ko'rinardi. O'rniga —
                              neytral telefon belgisi. */}
                          {row.name ? (
                            <Avatar name={row.name} size="sm" />
                          ) : (
                            <span
                              className="grid size-7 shrink-0 place-items-center rounded-full bg-surface-2 text-muted"
                              aria-hidden
                            >
                              <Phone className="size-3.5" />
                            </span>
                          )}
                          <div className="min-w-0">
                            <div className="truncate font-medium">
                              {row.name || row.phone || row.key}
                            </div>
                            {row.name && row.phone && (
                              <div className="tnum truncate text-2xs text-muted">
                                {row.phone}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Jami — kiruvchi/chiquvchi taqsimoti YONIDA.
                          Avval taqsimot so'z bilan ostida turardi va
                          tor ustunda ikki qatorga o'ralib, butun
                          qatorni ikki barobar balandlashtirardi.
                          Strelka o'sha ma'noni bir qatorga sig'diradi,
                          so'zi esa kursor ostida qoladi. */}
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        <span className="inline-flex items-center gap-2">
                          <span className="tnum font-medium">
                            {formatNumber(row.calls_total)}
                          </span>
                          <span className="inline-flex items-center gap-1 text-2xs text-muted">
                            <span
                              className="inline-flex items-center gap-0.5"
                              title={t('clients.inboundHint')}
                            >
                              <ArrowDownLeft className="size-3" aria-hidden />
                              <span className="tnum">{row.inbound}</span>
                            </span>
                            <span aria-hidden>·</span>
                            <span
                              className="inline-flex items-center gap-0.5"
                              title={t('clients.outboundHint')}
                            >
                              <ArrowUpRight className="size-3" aria-hidden />
                              <span className="tnum">{row.outbound}</span>
                            </span>
                          </span>
                        </span>
                      </td>

                      <td
                        className={cn(
                          'tnum whitespace-nowrap px-4 py-3 text-right',
                          row.missed ? 'font-medium text-bad' : 'text-muted',
                        )}
                      >
                        {formatNumber(row.missed)}
                      </td>

                      <td className="tnum whitespace-nowrap px-4 py-3 text-right text-muted">
                        {formatLongDuration(row.talk_seconds)}
                      </td>

                      {/* Ball — faqat baholangan suhbatlar bo'yicha.
                          Bahosi yo'q mijoz «0» emas, «—»: nol yomon
                          ish degan yolg'on ma'no berardi.
                          Chiziqcha ham CHIZILMAYDI: bo'sh bar «nol ball»
                          deb o'qilardi va baholanmagan qatorlar ko'p
                          bo'lgani uchun butun ustunni shovqinga
                          to'ldirardi. */}
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        {row.avg_score != null ? (
                          <span className="inline-flex items-center gap-2">
                            <span
                              className={cn('tnum font-semibold', TONE_CLASS[tone])}
                            >
                              {Math.round(row.avg_score)}
                            </span>
                            <MiniBar value={row.avg_score} tone={tone} width={44} />
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        {last ? (
                          <>
                            <div className="tnum text-sm">{fmt.date(last)}</div>
                            <div className="tnum text-2xs text-muted">
                              {fmt.time(last)}
                            </div>
                          </>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <Avatar
                            name={row.main_agent_name || '—'}
                            color={row.main_agent_color ?? undefined}
                            size="sm"
                          />
                          <span className="min-w-0 truncate text-muted">
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
