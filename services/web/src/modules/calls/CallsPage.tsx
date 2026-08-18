import {
  AlertTriangle,
  ArrowLeftRight,
  ChevronLeft,
  ChevronRight,
  CloudDownload,
  Eye,
  PhoneOff,
  SlidersHorizontal,
  Sparkles,
  Tag,
  User,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { useFilterOptions } from '@/modules/analytics/api'
import { useAuth } from '@/modules/auth/store'
import {
  useCalls,
  type CallsQuery,
  type CallTypeFilter,
  type Direction,
  type SortField,
  type SortOrder,
} from '@/modules/calls/api'
import { CallTypeBadge } from '@/modules/calls/CallTypeBadge'
import { DirectionMark } from '@/modules/calls/DirectionMark'
import { SyncModal } from '@/modules/calls/SyncModal'
import { ScoreModal } from '@/modules/pipeline/ScoreModal'
import { ScoringProgressBar } from '@/modules/pipeline/ScoringProgressBar'
import { Page, PageHeader } from '@/shared/layout/Page'
import { useDateFormat } from '@/shared/lib/date'
import {
  cn,
  formatDuration,
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

const PAGE_SIZE = 50

/** Jadval ustunlari. Raqamli ustunlar avval kattadan kichikka saralanadi —
 *  «eng uzun qo'ng'iroq», «eng past ball» ko'proq so'raladigan savol */
const COLUMNS: {
  field: SortField
  labelKey: string
  align?: 'left' | 'right'
  firstOrder?: SortOrder
}[] = [
  { field: 'date', labelKey: 'table.date', firstOrder: 'desc' },
  { field: 'agent', labelKey: 'table.agent' },
  { field: 'client', labelKey: 'table.client' },
  { field: 'duration', labelKey: 'table.duration', align: 'right', firstOrder: 'desc' },
  { field: 'score', labelKey: 'table.score', align: 'right', firstOrder: 'desc' },
  { field: 'status', labelKey: 'table.status', align: 'right', firstOrder: 'desc' },
]

export function CallsPage() {
  const { t } = useTranslation()
  const { user, can } = useAuth()
  const navigate = useNavigate()

  // MoyZvonki'dan tortib olish — `agents:sync` ruxsati borlarda.
  // Savdo xodimida bu ruxsat yo'q, ya'ni tugma umuman ko'rinmaydi.
  const canSync = can('agents:sync')
  const [syncOpen, setSyncOpen] = useState(false)
  // Baholash ham `agents:sync` ruxsatini talab qiladi — u pul
  // sarflaydigan amallar uchun umumiy kalit
  const [scoreOpen, setScoreOpen] = useState(false)

  // ── Xodim filtri MANZILDA turadi ──────────────────────────
  //
  // Xodim profilidagi «Hammasini ko'rish» `/calls?agent_id=…` ga
  // olib keladi — ya'ni sahifa ochilishidayoq filtr qo'yilgan bo'lishi
  // kerak. Manzilda turgani yana ikki narsani beradi: sahifa
  // yangilanganda filtr yo'qolmaydi va «orqaga» tugmasi uni to'g'ri
  // qaytaradi. Qolgan filtrlar (ball, qidiruv) — sessiya ichidagi
  // narsa, ular manzilga chiqmaydi.
  const [searchParams, setSearchParams] = useSearchParams()
  const agentParam = searchParams.get('agent_id') || undefined

  const [sort, setSort] = useState<SortState<SortField>>({
    field: 'date',
    order: 'desc',
  })
  const [query, setQuery] = useState<CallsQuery>({
    page: 1,
    page_size: PAGE_SIZE,
    sort: 'date',
    order: 'desc',
    agent_id: agentParam,
    /* Sukut bo'yicha FAQAT SAVDO.
       Ma'lumotning 96% i savdo suhbati emas (o'lchandi: 172 tadan
       166 tasi) — filtrsiz ro'yxat «Ichki» belgilari bilan to'lib
       ketadi va menejer asosiy ishni topolmaydi.
       ⚠️ Bu YASHIRIN filtr emas: tanlagichda «Savdo» yozilib turadi,
       ya'ni son nega kichik ekani ko'rinib turadi. */
    call_type: 'sales',
  })
  const [search, setSearch] = useState('')

  // Sahifa qayta mount bo'lmasdan manzil o'zgarishi mumkin (masalan
  // «orqaga»). Shunda ro'yxat ham ergashsin.
  useEffect(() => {
    setQuery((q) =>
      q.agent_id === agentParam ? q : { ...q, agent_id: agentParam, page: 1 },
    )
  }, [agentParam])

  const isSales = user?.role === 'sales'
  const fmt = useDateFormat()
  const calls = useCalls(query)
  const { data: options } = useFilterOptions()

  const total = calls.data?.total ?? 0
  const page = query.page ?? 1
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const patch = (next: Partial<CallsQuery>) =>
    setQuery((q) => ({ ...q, ...next, page: next.page ?? 1 }))

  // Saralash o'zgarsa birinchi sahifaga qaytamiz — aks holda 40-sahifada
  // turib saralasa, foydalanuvchi kutgan natijani ko'rmaydi
  const applySort = (next: SortState<SortField>) => {
    setSort(next)
    patch({ sort: next.field, order: next.order })
  }

  return (
    <Page>
      <PageHeader
        title={isSales ? t('nav.myCalls') : t('nav.calls')}
        subtitle={
          calls.data
            ? t('calls.found', { count: total })
            : t('table.loading')
        }
        actions={
          canSync ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" onClick={() => setSyncOpen(true)}>
                <CloudDownload className="size-4" />
                {t('calls.sync.action')}
              </Button>
              <Button variant="secondary" onClick={() => setScoreOpen(true)}>
                <Sparkles className="size-4" />
                {t('pipeline.action')}
              </Button>
            </div>
          ) : null
        }
      />

      {/* Ommaviy baholash orqa fonda ketadi — jarayon shu yerda
          chapdan o'ngga to'lib boradi. Oyna yopilgan bo'lsa ham
          ko'rinaveradi, chunki ish serverda davom etyapti. */}
      <ScoringProgressBar />

      {canSync && <SyncModal open={syncOpen} onClose={() => setSyncOpen(false)} />}
      {canSync && (
        <ScoreModal open={scoreOpen} onClose={() => setScoreOpen(false)} />
      )}

      {/* ── Filtrlar ──────────────────────────────────────── */}
      <Card className="p-4">
        {/* Sarlavha — filtrlar qatorini qolgan sahifadan ajratadi va
            Boshqaruv paneli / Faollik bo'limlari bilan bir xil ko'rinish
            beradi */}
        <div className="mb-3 flex items-center gap-2 text-muted">
          <SlidersHorizontal className="size-4" />
          <span className="label-eyebrow">{t('filters.title')}</span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {/* Qidiruv — xodim, hudud, client va transkript bo'yicha */}
          <SearchInput
            className="min-w-[240px] flex-1"
            placeholder={t('calls.searchPlaceholder')}
            value={search}
            onChange={(next) => {
              setSearch(next)
              patch({ search: next.trim() || undefined })
            }}
          />

          {/* Xodim */}
          {!isSales && options?.agents?.length ? (
            <Select
              icon={User}
              active={Boolean(query.agent_id)}
              className="w-52"
              value={query.agent_id ?? ''}
              onChange={(e) => {
                const next = e.target.value || undefined
                patch({ agent_id: next })
                // Manzilni ham yangilaymiz — `replace`, chunki filtr
                // almashtirish «orqaga» tarixiga qadam qo'shmasligi kerak
                setSearchParams(
                  (prev) => {
                    const params = new URLSearchParams(prev)
                    if (next) params.set('agent_id', next)
                    else params.delete('agent_id')
                    return params
                  },
                  { replace: true },
                )
              }}
            >
              <option value="">{t('filters.all')}</option>
              {options.agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
            </Select>
          ) : null}

          {/* Yo'nalish */}
          <Select
            icon={ArrowLeftRight}
            active={Boolean(query.direction)}
            className="w-40"
            value={query.direction ?? ''}
            onChange={(e) =>
              patch({ direction: (e.target.value || undefined) as Direction })
            }
          >
            <option value="">{t('calls.direction.all')}</option>
            <option value="inbound">{t('calls.direction.inbound')}</option>
            <option value="outbound">{t('calls.direction.outbound')}</option>
          </Select>

          {/* Javob holati */}
          <Select
            icon={PhoneOff}
            active={Boolean(query.answered)}
            className="w-44"
            value={query.answered ?? ''}
            onChange={(e) =>
              patch({
                answered: (e.target.value || undefined) as CallsQuery['answered'],
              })
            }
          >
            <option value="">{t('calls.answered.all')}</option>
            <option value="yes">{t('calls.answered.yes')}</option>
            <option value="no">{t('calls.answered.no')}</option>
          </Select>

          {/* Tur.
              NEGA SELECT, SEGMENTED EMAS: yetti qiymat segmentli
              tugmachalarga sig'maydi va filtr qatorini buzardi. */}
          <Select
            icon={Tag}
            /* Sukut bo'yicha «savdo» qo'yilgan — bu ham FILTR va u
               faol ko'rinishi kerak, aks holda foydalanuvchi nega
               ro'yxat qisqa ekanini tushunmaydi */
            active={Boolean(query.call_type)}
            className="w-48"
            value={query.call_type ?? ''}
            onChange={(e) =>
              patch({
                call_type: (e.target.value || undefined) as CallTypeFilter | undefined,
              })
            }
          >
            <option value="">{t('calls.type.filterAll')}</option>
            <option value="sales">{t('calls.type.sales')}</option>
            <option value="not_sales">{t('calls.type.filterNotSales')}</option>
            <option value="service">{t('calls.type.service')}</option>
            <option value="internal">{t('calls.type.internal')}</option>
            <option value="personal">{t('calls.type.personal')}</option>
            <option value="unclear">{t('calls.type.unclear')}</option>
            <option value="unknown">{t('calls.type.filterUnknown')}</option>
          </Select>

          {/* Ball oralig'i */}
          <Segmented
            value={
              query.score_max === 55 ? 'low' : query.score_min === 85 ? 'high' : 'all'
            }
            onChange={(value) =>
              patch({
                score_min: value === 'high' ? 85 : undefined,
                score_max: value === 'low' ? 55 : undefined,
              })
            }
            items={[
              { value: 'all', label: t('filters.all') },
              { value: 'low', label: t('calls.lowScore') },
              { value: 'high', label: t('calls.highScore') },
            ]}
          />

          {/* Tekshirish kerak */}
          <button
            onClick={() =>
              patch({ needs_review: query.needs_review ? undefined : true })
            }
            className={cn(
              'inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium transition-all duration-250 ease-ios active:scale-95',
              query.needs_review
                ? 'bg-warn text-white shadow-xs'
                : 'bg-surface-2 text-muted hover:text-text',
            )}
          >
            <Eye className="size-3.5" />
            {t('calls.needsReview')}
          </button>
        </div>
      </Card>

      {/* ── Jadval ────────────────────────────────────────── */}
      <Card>
        {calls.isLoading ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 10 }).map((_, i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </div>
        ) : !calls.data?.items.length ? (
          /* Savdo filtri sukut bo'yicha yoqilgan, ya'ni bo'sh ro'yxat
             «ma'lumot yo'q» degani BO'LMASLIGI mumkin: tasniflanmagan
             qo'ng'iroqlar ham yashiringan bo'ladi. Sababini aytmasak
             admin yangi sinxronlagandan keyin bo'sh ekranni ko'rib,
             sinxronizatsiya ishlamagan deb o'ylaydi.
             Qo'shimcha so'rov QILINMAYDI — matn har holatda to'g'ri. */
          query.call_type === 'sales' ? (
            <EmptyState
              message={t('table.empty')}
              hint={t('calls.type.emptySalesHint')}
              action={{
                label: t('calls.type.filterAll'),
                onClick: () => patch({ call_type: undefined }),
              }}
            />
          ) : (
            <EmptyState message={t('table.empty')} />
          )
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
                      onChange={applySort}
                    />
                  ))}
                  <th className="w-10 px-2 py-3" />
                </tr>
              </thead>
              <tbody>
                {calls.data.items.map((call) => {
                  const tone = scoreTone(call.score) as
                    | 'accent'
                    | 'good'
                    | 'warn'
                    | 'bad'
                  const date = new Date(call.started_at)

                  return (
                    <tr
                      key={call.id}
                      onClick={() => navigate(`/calls/${call.id}`)}
                      className="cursor-pointer border-b border-border/60 transition-colors last:border-0 hover:bg-surface-2/60"
                    >
                      <td className="whitespace-nowrap px-4 py-3">
                        {/* Yo'nalish sana yonida — alohida ustun
                            jadvalni kengaytirardi, belgi esa bir
                            qarashda o'qiladi */}
                        <div className="flex items-center gap-2">
                          <DirectionMark
                            direction={call.direction}
                            answered={call.answered}
                          />
                          <div>
                            <div className="tnum text-sm">{fmt.date(date)}</div>
                            <div className="tnum text-2xs text-muted">
                              {fmt.time(date)}
                            </div>
                          </div>
                        </div>
                      </td>

                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <Avatar
                            name={call.agent_name}
                            color={call.agent_color}
                            size="sm"
                          />
                          <span className="truncate font-medium">
                            {call.agent_name}
                          </span>
                        </div>
                      </td>

                      {/* Mijoz: katalogdagi nom → MoyZvonki bergan nom →
                          raqam. Raqam «—» dan foydaliroq: uni CRM da
                          qidirsa ham, terib ko'rsa ham bo'ladi. */}
                      <td className="px-4 py-3 text-muted">
                        {call.client_name ? (
                          <span className="truncate">{call.client_name}</span>
                        ) : call.client_phone ? (
                          <span className="tnum">{call.client_phone}</span>
                        ) : (
                          '—'
                        )}
                      </td>

                      <td className="tnum px-4 py-3 text-right text-muted">
                        {formatDuration(call.duration_sec)}
                      </td>

                      {/* Ball ustuni. Savdo bo'lmagan qo'ng'iroq
                          BAHOLANMAYDI — bo'sh ball «AI ishlamadi» deb
                          o'qilmasligi uchun o'rniga tur ko'rsatiladi. */}
                      <td className="px-4 py-3">
                        {call.call_type && call.call_type !== 'sales' ? (
                          <div className="flex justify-end">
                            <CallTypeBadge type={call.call_type} compact />
                          </div>
                        ) : (
                          <div className="flex items-center justify-end gap-2">
                            <span className={cn('tnum font-semibold', TONE_CLASS[tone])}>
                              {call.score ?? '—'}
                            </span>
                            <MiniBar value={call.score} tone={tone} width={44} />
                          </div>
                        )}
                      </td>

                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex items-center gap-1.5">
                          {call.red_flag_count > 0 && (
                            <Badge tone="bad">
                              <AlertTriangle className="size-3" />
                              <span className="tnum">{call.red_flag_count}</span>
                            </Badge>
                          )}
                          {call.needs_review && (
                            <Badge tone="warn">{t('calls.review')}</Badge>
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

        {/* Sahifalash */}
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
                onClick={() => setQuery((q) => ({ ...q, page: page - 1 }))}
              >
                <ChevronLeft className="size-3.5" />
                {t('common.prev')}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= pages}
                onClick={() => setQuery((q) => ({ ...q, page: page + 1 }))}
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
