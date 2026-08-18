/**
 * Client baholari sahifasi.
 *
 * Nima ko'rsatiladi:
 *   • yuqorida — o'rtacha baho (yulduzlar bilan), javoblar soni,
 *     javob berish darajasi va (admin/manager uchun) reytingi tayyor xodimlar
 *   • chapda   — 1..5 yulduz taqsimoti
 *   • o'ngda   — client fikrlari ro'yxati: yulduz, hal bo'lish belgisi,
 *     qoidabuzarlik chiplari, izoh, sana, hudud
 *
 * Hudud endi XODIMDA emas, so'rovnoma yuborilgan GURUHDA — shuning
 * uchun hudud filtri backendning `region` parametriga uzatiladi.
 *
 * Qoidabuzarlik yorliqlari `GET /surveys/red-flags` dan olinadi va
 * hech qachon frontendda saqlanmaydi: serverda yangi mezon qo'shilsa
 * u shu zahoti ko'rinadi, deploy kutilmaydi.
 *
 * Rol qoidalari (backend ham xuddi shunday majburlaydi):
 *   • admin / manager — barcha xodim + izohlar, xodim filtri bor
 *   • sales           — faqat o'ziniki, filtr yo'q, sarlavha "Mening client baholarim"
 *   • `access.sales_client_rating` = score_only → izohlar null (xotirjam eslatma)
 *   • `access.sales_client_rating` = hidden     → 403 (tushuntiruvchi holat)
 *
 * `ready=false` — javoblar kam, o'rtacha ATAYIN berilmaydi. `null` nol emas.
 */

import {
  EyeOff,
  Flag,
  Info,
  MessageSquare,
  SearchX,
  Star,
  TrendingUp,
  Users,
} from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useAgentLeaderboard, useFilterOptions } from '@/modules/analytics/api'
import { useAuth } from '@/modules/auth/store'
import { useRegionChoices } from '@/modules/regions/api'
import {
  isForbidden,
  ratingProgress,
  useRedFlagLabels,
  useSurveyFeedback,
  type Resolution,
  type SurveyFeedbackItem,
} from '@/modules/surveys/api'
import { Page, PageHeader } from '@/shared/layout/Page'
import {
  rangeDays,
  rangeToQuery,
  resolvePreset,
  useDateFormat,
  type DateRange,
} from '@/shared/lib/date'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Avatar, MiniBar } from '@/shared/ui/dataviz'
import { DateRangePicker } from '@/shared/ui/DateRangePicker'
import { Modal } from '@/shared/ui/Modal'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Segmented,
  Select,
  Skeleton,
} from '@/shared/ui/primitives'
import { SearchInput } from '@/shared/ui/SearchInput'

type Tone = 'good' | 'warn' | 'bad'
type ListFilter = 'all' | 'comments' | 'low' | 'flagged'

const RESOLUTION_TONE: Record<Resolution, Tone> = {
  yes: 'good',
  partial: 'warn',
  no: 'bad',
}

/**
 * Qoidabuzarlik turi → rang.
 *
 * Ranglar kalitdan hisoblanadi, ro'yxatga bog'lanmaydi — serverda yangi
 * mezon paydo bo'lsa u ham darhol o'z rangini oladi. Palitra ataylab
 * faqat "ogohlantiruvchi" tuslardan: qoidabuzarlik hech qachon
 * xotirjam yashil bo'lib ko'rinmasligi kerak.
 */
const FLAG_COLORS = [
  '#ef4444', '#f97316', '#f59e0b', '#e11d48',
  '#db2777', '#c026d3', '#7c3aed', '#b45309',
]

function flagColor(key: string): string {
  let hash = 0
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0
  }
  return FLAG_COLORS[hash % FLAG_COLORS.length]
}

function redFlagsOf(item: SurveyFeedbackItem): string[] {
  return item.red_flags ?? []
}

/** Yulduz → semantik rang. Ko'z raqamni o'qimasdan ham tushunadi. */
function csatTone(csat: number): Tone {
  if (csat >= 4) return 'good'
  if (csat === 3) return 'warn'
  return 'bad'
}

export function SurveysPage() {
  const { t } = useTranslation()
  const { user, can } = useAuth()
  const fmt = useDateFormat()

  const isSales = user?.role === 'sales'
  // score_only rejimida bu ruxsat berilmaydi — izohlar null bo'lib keladi
  const commentsVisible = !isSales || can('surveys:read:own:comments')

  const [range, setRange] = useState<DateRange>(() => resolvePreset('last90'))
  const [agentId, setAgentId] = useState('')
  const [region, setRegion] = useState('')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ListFilter>('all')
  const [opened, setOpened] = useState<SurveyFeedbackItem | null>(null)

  const needle = search.trim()

  const days = Math.min(365, rangeDays(range))
  const feedback = useSurveyFeedback({
    ...rangeToQuery(range),
    days,
    limit: 200,
    agent_id: isSales ? undefined : agentId || undefined,
    // Hudud guruhdan keladi — filtrni backend bajaradi, jadval emas
    region: region || undefined,
    // Qidiruv ham backendda: o'rtacha va taqsimot topilganlarga mos bo'lsin
    search: needle || undefined,
  })

  // Qoidabuzarlik yorliqlari serverdan — bu yerda ro'yxat saqlanmaydi
  const flagLabel = useRedFlagLabels()

  // Xodim filtri — `/analytics/filters` barcha rollarga ochiq va
  // sanadan qat'i nazar to'liq ro'yxatni qaytaradi
  const options = useFilterOptions()
  // Avatar rangi + "reytingi tayyor xodimlar" hisobi shu yerdan
  const leaderboard = useAgentLeaderboard(rangeToQuery(range))

  const agentById = useMemo(
    () => new Map((leaderboard.data ?? []).map((row) => [row.agent_id, row])),
    [leaderboard.data],
  )

  const data = feedback.data
  /* `?? []` har renderda YANGI massiv yaratadi — pastdagi `useMemo`
     lar shu sababli hech qachon keshdan foydalanmasdi. Bir joyda
     memolash ikkalasini ham tuzatadi. */
  const items = useMemo(() => data?.items ?? [], [data?.items])
  /* Chegara javobning o'zidan — kodga yozilmaydi, admin uni
     Sozlamalardan o'zgartira oladi */
  const progress = ratingProgress(data)

  const visible = useMemo(() => {
    if (filter === 'comments') return items.filter((i) => i.comment)
    if (filter === 'low') return items.filter((i) => i.csat <= 3)
    if (filter === 'flagged') return items.filter((i) => redFlagsOf(i).length > 0)
    return items
  }, [items, filter])

  const flaggedCount = useMemo(
    () => items.filter((i) => redFlagsOf(i).length > 0).length,
    [items],
  )

  /* Hudud ro'yxati — admin boshqaradigan `GET /regions`.
     Tanlash uchun faqat faol hududlar, lekin tanlangan hudud
     faolsizlantirilgan bo'lsa ham ro'yxatda qoladi (aks holda
     filtr jimgina o'zidan tushib ketardi). */
  const { names: regionOptions } = useRegionChoices(region || null)

  // Izohsiz bo'lishi ikki xil: sozlama yopgan yoki client yozmagan
  const commentsWithheld = Boolean(
    isSales && !commentsVisible && data?.count,
  )

  const readyAgents = useMemo(() => {
    const rows = leaderboard.data ?? []
    return {
      ready: rows.filter((r) => r.client_rating_ready).length,
      total: rows.length,
    }
  }, [leaderboard.data])

  const title = isSales ? t('surveys.myTitle') : t('nav.surveys')

  /* Bo'sh ro'yxatning sababi ikki xil: davrda javob yo'q yoki
     qidiruvga mos kelmadi. Ikkalasi bir xil matn bilan chiqsa
     foydalanuvchi nima qilishni bilmaydi. */
  const emptyMessage = needle
    ? t('surveys.searchEmpty', { query: needle })
    : t('surveys.emptyRange')

  /** Qidiruv bor, javob keldi, natija nol — alohida holat */
  const noMatches = Boolean(needle) && !feedback.isLoading && !data?.count

  /* ── Sozlama bo'limni butunlay yopgan (403) ─────────────── */
  if (isForbidden(feedback.error)) {
    return (
      <Page>
        <PageHeader title={title} />
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="icon-tile size-12">
              <EyeOff className="size-5" />
            </div>
            <p className="text-sm font-medium">{t('surveys.forbidden')}</p>
            <p className="max-w-md text-xs leading-relaxed text-muted">
              {t('surveys.forbiddenHint')}
            </p>
          </CardBody>
        </Card>
      </Page>
    )
  }

  /* ── Boshqa xatolik — "ma'lumot yo'q" deb aldamaymiz ────── */
  if (feedback.isError) {
    return (
      <Page>
        <PageHeader title={title} />
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-16 text-center">
            <p className="text-sm font-medium">{t('common.error')}</p>
            <Button variant="secondary" size="sm" onClick={() => void feedback.refetch()}>
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
        title={title}
        subtitle={
          needle
            ? t('surveys.subtitleSearch', { count: data?.count ?? 0, query: needle })
            : t('surveys.subtitle', { count: data?.count ?? 0, days })
        }
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            {/* Qidiruv — savdo xodimi ismi va hudud nomi bo'yicha.
                Boshqa filtrlar bilan bitta qatorda: hammasi bir guruh. */}
            <SearchInput
              className="w-full sm:w-56 [&_input]:h-9 [&_input]:text-xs"
              placeholder={t('surveys.searchPlaceholder')}
              value={search}
              onChange={setSearch}
            />

            {!isSales && options.data?.agents.length ? (
              <Select
                compact
                className="w-52"
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                aria-label={t('filters.agent')}
              >
                <option value="">{t('surveys.allAgents')}</option>
                {options.data.agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
              </Select>
            ) : null}

            {/* Hudud — so'rovnoma yuborilgan guruhning hududi.
                Bitta variant qolsa ko'rsatilmaydi: «Hammasi» bilan
                o'sha bitta hudud bir xil natija beradi. Savdo xodimi
                uchun bu asosiy holat — filtr faqat u ROSTDAN bir
                nechta hududda ishlaganda paydo bo'ladi. */}
            {regionOptions.length > 1 && (
              <Select
                compact
                className="w-44"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                aria-label={t('filters.region')}
              >
                <option value="">{t('surveys.allRegions')}</option>
                {regionOptions.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </Select>
            )}

            <DateRangePicker value={range} onChange={setRange} />
          </div>
        }
      />

      {/* Qidiruv hech narsa topmadi — nol bilan to'lgan plitkalar
          o'rniga bitta aniq javob. Nol «ma'lumot yo'q» degani emas,
          «bu so'rov bo'yicha yo'q» degani. */}
      {noMatches ? (
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-16 text-center">
            <span className="icon-tile size-12 text-muted">
              <SearchX className="size-5" />
            </span>
            <p className="text-sm font-medium">
              {t('surveys.searchEmpty', { query: needle })}
            </p>
            <p className="max-w-md text-xs leading-relaxed text-muted">
              {t('surveys.searchEmptyHint')}
            </p>
            <Button variant="secondary" size="sm" onClick={() => setSearch('')}>
              {t('surveys.searchClear')}
            </Button>
          </CardBody>
        </Card>
      ) : (
        <>
      {/* ── Yig'ma ko'rsatkichlar ───────────────────────────── */}
      <div
        className={cn(
          'grid gap-3 2xl:gap-4',
          isSales ? 'grid-cols-1 sm:grid-cols-3' : 'grid-cols-2 lg:grid-cols-4',
        )}
      >
        <SummaryTile
          icon={Star}
          label={t('surveys.average')}
          loading={feedback.isLoading}
          tone="warn"
        >
          {data?.ready && data.average != null ? (
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <span className="tnum text-2xl font-semibold leading-none">
                {data.average.toFixed(2)}
              </span>
              <Stars value={data.average} />
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              {/* Javob KELGAN bo'lsa raqam ko'rsatiladi — «—» «ishlamadi»
                  degan taassurot qoldiradi, «1 / 5» esa aniq holat */}
              {progress.count > 0 && progress.min != null ? (
                <span className="tnum text-2xl font-semibold leading-none">
                  {progress.count}
                  <span className="text-base font-medium text-muted">
                    {' / '}
                    {progress.min}
                  </span>
                </span>
              ) : (
                <span className="text-2xl font-semibold leading-none text-muted">—</span>
              )}
              <Badge tone="warn">
                {progress.min != null
                  ? t('surveys.collecting', {
                      count: progress.count,
                      min: progress.min,
                    })
                  : t('surveys.collectingCount', { count: progress.count })}
              </Badge>
            </div>
          )}
          {!feedback.isLoading && !data?.ready && (
            <p className="mt-2 text-2xs leading-relaxed text-muted">
              {progress.remaining != null && progress.remaining > 0
                ? t('surveys.notReadyRemaining', {
                    count: progress.remaining,
                    min: progress.min,
                  })
                : t('surveys.notReadyHint')}
            </p>
          )}
        </SummaryTile>

        <SummaryTile
          icon={MessageSquare}
          label={t('surveys.responses')}
          loading={feedback.isLoading}
        >
          <span className="tnum text-2xl font-semibold leading-none">
            {formatNumber(data?.count ?? 0)}
          </span>
          {commentsVisible && (
            <p className="mt-2 text-2xs text-muted">
              {t('surveys.withComments', {
                count: items.filter((i) => i.comment).length,
              })}
            </p>
          )}
        </SummaryTile>

        <SummaryTile
          icon={TrendingUp}
          label={t('surveys.responseRate')}
          loading={feedback.isLoading}
          tone="good"
        >
          <span className="tnum text-2xl font-semibold leading-none">
            {data?.response_rate != null ? `${data.response_rate}%` : '—'}
          </span>
          <p className="mt-2 text-2xs text-muted">{t('surveys.responseRateHint')}</p>
        </SummaryTile>

        {!isSales && (
          <SummaryTile
            icon={Users}
            label={t('surveys.readyAgents')}
            loading={leaderboard.isLoading}
          >
            <span className="tnum text-2xl font-semibold leading-none">
              {readyAgents.ready}
              <span className="text-base font-medium text-muted">
                {' / '}
                {readyAgents.total}
              </span>
            </span>
            <p className="mt-2 text-2xs text-muted">
              {progress.min != null
                ? t('surveys.readyAgentsHint', { min: progress.min })
                : t('surveys.readyAgentsHintUnknown')}
            </p>
          </SummaryTile>
        )}
      </div>

      {/* ── Taqsimot + fikrlar ──────────────────────────────── */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,340px)_minmax(0,1fr)] 2xl:gap-4">
        {/* Yulduzlar taqsimoti */}
        <Card>
          <CardHeader title={t('surveys.distribution')} hint={t('surveys.anonymous')} />
          <CardBody className="pt-4">
            {feedback.isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : !data?.count ? (
              <EmptyState message={emptyMessage} />
            ) : (
              <div className="space-y-3">
                {[5, 4, 3, 2, 1].map((star) => {
                  const count = data.distribution[String(star)] ?? 0
                  const pct = data.count ? (count / data.count) * 100 : 0
                  return (
                    <div key={star} className="flex items-center gap-3">
                      <span className="tnum flex w-9 shrink-0 items-center gap-0.5 text-2xs font-medium text-muted">
                        {star}
                        <Star className="size-3 fill-warn text-warn" />
                      </span>
                      <MiniBar value={pct} tone={csatTone(star)} width={0} />
                      <span className="tnum w-14 shrink-0 text-right text-2xs text-muted">
                        {count}
                        <span className="ml-1 opacity-60">{Math.round(pct)}%</span>
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </CardBody>
        </Card>

        {/* Client fikrlari */}
        <Card>
          <CardHeader
            title={t('surveys.feedbackTitle')}
            hint={t('surveys.feedbackHint')}
            action={
              <Segmented
                value={filter}
                onChange={setFilter}
                items={[
                  { value: 'all' as ListFilter, label: t('surveys.filterAll') },
                  // Izohlar yopilgan bo'lsa bu filtr ma'nosiz — ko'rsatilmaydi
                  ...(commentsVisible
                    ? [
                        {
                          value: 'comments' as ListFilter,
                          label: t('surveys.filterComments'),
                        },
                      ]
                    : []),
                  { value: 'low' as ListFilter, label: t('surveys.filterLow') },
                  // Qoidabuzarlik yo'q bo'lsa bo'sh filtr ko'rsatilmaydi
                  ...(flaggedCount
                    ? [
                        {
                          value: 'flagged' as ListFilter,
                          label: t('surveys.filterFlagged'),
                        },
                      ]
                    : []),
                ]}
              />
            }
          />
          <CardBody className="pt-4">
            {/* Izohlar administrator tomonidan yopilgan — xatolik emas */}
            {commentsWithheld && (
              <div className="mb-4 flex items-start gap-2.5 rounded-2xl bg-surface-2/70 p-3.5">
                <Info className="mt-px size-4 shrink-0 text-muted" />
                <p className="text-xs leading-relaxed text-muted">
                  {t('surveys.commentsHidden')}
                </p>
              </div>
            )}

            {feedback.isLoading ? (
              <div className="grid gap-2 2xl:grid-cols-2 3xl:grid-cols-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-24 w-full" />
                ))}
              </div>
            ) : !visible.length ? (
              <EmptyState message={items.length ? t('surveys.emptyFilter') : emptyMessage} />
            ) : (
              <div className="grid gap-2 2xl:grid-cols-2 3xl:grid-cols-3">
                {visible.map((item) => (
                  <FeedbackCard
                    key={item.id}
                    item={item}
                    date={fmt.date(item.responded_at)}
                    showAgent={!isSales}
                    flagLabel={flagLabel}
                    avatarColor={agentById.get(item.agent_id)?.color}
                    avatarSrc={agentById.get(item.agent_id)?.avatar_url}
                    onOpen={() => setOpened(item)}
                  />
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
        </>
      )}

      {/* To'liq izoh — qoida bo'yicha modalda */}
      <CommentModal
        item={opened}
        onClose={() => setOpened(null)}
        showAgent={!isSales}
        flagLabel={flagLabel}
        date={opened ? fmt.dateTime(opened.responded_at) : ''}
      />
    </Page>
  )
}

/* ── Yig'ma plitka ───────────────────────────────────────── */

const TILE_ICON_TONE: Record<'accent' | Tone, string> = {
  accent: 'text-accent',
  good: 'text-good',
  warn: 'text-warn',
  bad: 'text-bad',
}

function SummaryTile({
  icon: Icon,
  label,
  loading,
  tone = 'accent',
  children,
}: {
  icon: typeof Star
  label: string
  loading?: boolean
  tone?: 'accent' | Tone
  children: ReactNode
}) {
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center gap-2.5">
        <span className={cn('icon-tile size-8', TILE_ICON_TONE[tone])}>
          <Icon className="size-4" />
        </span>
        <span className="label-eyebrow">{label}</span>
      </div>
      {loading ? <Skeleton className="h-8 w-24" /> : children}
    </Card>
  )
}

/* ── Yulduzlar ───────────────────────────────────────────── */

function Stars({ value, size = 'sm' }: { value: number; size?: 'sm' | 'md' }) {
  const full = Math.round(value)
  const px = size === 'md' ? 'size-4' : 'size-3.5'
  return (
    <span className="inline-flex items-center gap-0.5" aria-label={`${value} / 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={cn(px, i <= full ? 'fill-warn text-warn' : 'text-muted/35')}
        />
      ))}
    </span>
  )
}

/* ── Qoidabuzarlik chiplari ──────────────────────────────────
   Yorliqlar serverdan keladi. Yorliq hali yetib kelmagan bo'lsa
   kalitning o'zi ko'rsatiladi — chip yo'qolib qolmaydi. */

function RedFlagChips({
  keys,
  flagLabel,
  max,
}: {
  keys: string[]
  flagLabel: (key: string) => string
  /** Kartochkada joy cheklangan — qolgani "+2" bo'lib yig'iladi */
  max?: number
}) {
  if (!keys.length) return null
  const shown = max ? keys.slice(0, max) : keys
  const rest = keys.length - shown.length

  return (
    <div className="flex flex-wrap items-center gap-1">
      {shown.map((key) => {
        const color = flagColor(key)
        return (
          <span
            key={key}
            title={flagLabel(key)}
            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-medium"
            style={{ background: `${color}24`, color }}
          >
            <span
              aria-hidden
              className="size-1.5 shrink-0 rounded-full"
              style={{ background: color }}
            />
            {flagLabel(key)}
          </span>
        )
      })}
      {rest > 0 && (
        <span className="rounded-full bg-bad/10 px-2 py-0.5 text-2xs font-medium text-bad">
          +{rest}
        </span>
      )}
    </div>
  )
}

/* ── Bitta fikr ──────────────────────────────────────────── */

function FeedbackCard({
  item,
  date,
  showAgent,
  flagLabel,
  avatarColor,
  avatarSrc,
  onOpen,
}: {
  item: SurveyFeedbackItem
  date: string
  showAgent: boolean
  flagLabel: (key: string) => string
  avatarColor?: string
  avatarSrc?: string | null
  onOpen: () => void
}) {
  const { t } = useTranslation()
  const tone = csatTone(item.csat)
  const flags = redFlagsOf(item)

  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        'flex w-full flex-col gap-2.5 rounded-2xl p-3.5 text-left',
        'transition-all duration-250 ease-ios active:scale-[0.99]',
        // Qoidabuzarlikli baho oddiy past bahodan ko'rinishda ham farq qiladi
        flags.length
          ? 'bg-bad/[0.06] ring-1 ring-bad/25 hover:bg-bad/10'
          : 'bg-surface-2/60 hover:bg-surface-2',
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {/* Rang + yulduz: ko'z bir qarashda ushlaydi */}
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-2xs font-semibold',
            tone === 'good' && 'bg-good/10 text-good',
            tone === 'warn' && 'bg-warn/10 text-warn',
            tone === 'bad' && 'bg-bad/10 text-bad',
          )}
        >
          <Star className="size-3 fill-current" />
          <span className="tnum">{item.csat}</span>
        </span>

        {item.resolution && (
          <Badge tone={RESOLUTION_TONE[item.resolution]}>
            {t(`surveys.resolution.${item.resolution}`)}
          </Badge>
        )}

        {flags.length > 0 && (
          <Badge tone="bad" title={t('surveys.redFlagCount', { count: flags.length })}>
            <Flag className="size-3 fill-current" />
            <span className="tnum">{flags.length}</span>
          </Badge>
        )}

        <span className="tnum ml-auto shrink-0 text-2xs text-muted">{date}</span>
      </div>

      <RedFlagChips keys={flags} flagLabel={flagLabel} max={3} />

      {item.comment ? (
        <p className="line-clamp-2 text-xs leading-relaxed text-text">{item.comment}</p>
      ) : (
        <p className="text-xs italic leading-relaxed text-muted/70">
          {t('surveys.noComment')}
        </p>
      )}

      <div className="flex items-center gap-2 text-2xs text-muted">
        {showAgent ? (
          <>
            <Avatar
              name={item.agent_name}
              color={avatarColor}
              src={avatarSrc}
              size="sm"
            />
            <span className="truncate font-medium text-text">{item.agent_name}</span>
            <span className="opacity-50">·</span>
          </>
        ) : null}
        <span className="truncate">{item.region}</span>
      </div>
    </button>
  )
}

/* ── To'liq izoh modali ──────────────────────────────────── */

function CommentModal({
  item,
  date,
  showAgent,
  flagLabel,
  onClose,
}: {
  item: SurveyFeedbackItem | null
  date: string
  showAgent: boolean
  flagLabel: (key: string) => string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const flags = item ? redFlagsOf(item) : []

  return (
    <Modal
      open={Boolean(item)}
      onOpenChange={(next) => !next && onClose()}
      title={t('surveys.commentTitle')}
      description={t('surveys.anonymous')}
      size="sm"
    >
      {item && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2.5">
            <Stars value={item.csat} size="md" />
            <span className="tnum text-sm font-semibold">{item.csat} / 5</span>
            {item.resolution && (
              <Badge tone={RESOLUTION_TONE[item.resolution]}>
                {t(`surveys.resolution.${item.resolution}`)}
              </Badge>
            )}
          </div>

          {/* Tanlangan qoidabuzarliklar — to'liq ro'yxat, qisqartirilmagan */}
          {flags.length > 0 && (
            <div className="rounded-2xl bg-bad/[0.06] p-3.5 ring-1 ring-bad/20">
              <div className="mb-2 flex items-center gap-1.5 text-2xs font-medium text-bad">
                <Flag className="size-3 fill-current" />
                {t('surveys.redFlags')}
              </div>
              <RedFlagChips keys={flags} flagLabel={flagLabel} />
            </div>
          )}

          <p className="whitespace-pre-line text-sm leading-relaxed">
            {item.comment ?? t('surveys.noComment')}
          </p>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-border/60 pt-3.5 text-2xs text-muted">
            {showAgent && (
              <span className="font-medium text-text">{item.agent_name}</span>
            )}
            <span>{item.region}</span>
            <span className="tnum ml-auto">{date}</span>
          </div>
        </div>
      )}
    </Modal>
  )
}
