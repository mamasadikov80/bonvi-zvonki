/**
 * Savdo nazorati.
 *
 * SAVOL: savdo rasmiy kelishuv bilan — ya'ni yozib olingan
 * qo'ng'iroqdan keyin — bo'lyaptimi, yoki tizimdan tashqarida
 * kelishilyaptimi? Signal oddiy: SAP da savdo bor, bizda esa unga mos
 * suhbat yo'q.
 *
 * ⚠️ BU RO'YXAT AYBLAMAYDI. U tekshirish uchun navbat tayyorlaydi,
 * qaror esa rahbarniki. Shuning uchun:
 *   · shubhali savdo SARIQ, qizil emas — qizil faqat odam «haqiqatan
 *     shubhali» degandan keyin paydo bo'ladi;
 *   · uchala toifa ham ekranda turadi, hech biri yashirilmaydi —
 *     shu jumladan «tekshirib bo'lmadi» (u SAP dagi ma'lumot
 *     sifatining ko'rsatkichi, «toza» degani emas);
 *   · har qatorda DALIL bor: sana, mijoz kodi, telefon va oxirgi
 *     suhbat — rahbar sonni SAP da qo'lda tekshirishi kerak
 *     (shartnoma, 4-bo'lim).
 *
 * ⚠️ DALIL JADVALGA JUMLA BO'LIB YOZILMAYDI. Bir urinib ko'rilgan:
 * «Oldingi savdo 19/08/2026 — orasida 0 ta suhbat» degan matn tor
 * katakda to'rt qatorga o'ralib, qatorni qo'shnilaridan uch barobar
 * baland qildi va jadval o'qib bo'lmas holga keldi. Endi taqsimot
 * shunday:
 *   · JADVAL — faqat holat kodlari (`Shubhali`, `R1`, `R2`), har
 *     katak bir xil balandlikda, hech qayerda o'ralish yo'q;
 *   · KODLARNING MA'NOSI — jadval sarlavhasi ostidagi bitta qator
 *     izohda (`RuleLegend`), hamma qator uchun bir marta;
 *   · TAFSILOT — qator bosilganda ochiladigan XRONOLOGIYA oynasida,
 *     u yerda joy bor (`SaleTimelineModal`).
 *
 * ⚠️ Sana filtri `YYYY-MM-DD` yuboradi, ISO vaqt EMAS: savdoda vaqt
 * yo'q (`sales.occurred_on` — `date`), shuning uchun ilovadagi
 * `rangeToQuery` bu yerda ishlatilmaydi.
 */

import type { TFunction } from 'i18next'
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  Flag,
  RotateCcw,
  Sheet,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Store,
  TriangleAlert,
  Upload,
  User,
  type LucideIcon,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAgents } from '@/modules/agents/api'
import { useAuth } from '@/modules/auth/store'
import {
  fetchAllCompliance,
  REVIEW_STATES,
  SALE_RULES,
  useCompliance,
  useComplianceSummary,
  useSaleBranches,
  type ComplianceQuery,
  type ComplianceRow,
  type SaleReviewFilter,
  type SaleRule,
  type SaleSort,
  type SaleVerdict,
} from '@/modules/sales/api'
import {
  ReviewBadge,
  RuleBadges,
  RuleLegend,
  SkipBadge,
  VerdictBadge,
} from '@/modules/sales/badges'
import { BranchesModal } from '@/modules/sales/BranchesModal'
import { exportCompliance } from '@/modules/sales/export'
import { ImportModal } from '@/modules/sales/ImportModal'
import { useSaleReason } from '@/modules/sales/reason'
import { ReviewModal } from '@/modules/sales/ReviewModal'
import { SaleTimelineModal } from '@/modules/sales/SaleTimelineModal'
import { Page, PageHeader } from '@/shared/layout/Page'
import {
  formatFullDate,
  resolvePreset,
  toInputValue,
  useDateFormat,
  type DateRange,
} from '@/shared/lib/date'
import { cn, formatNumber } from '@/shared/lib/utils'
import { DateRangePicker } from '@/shared/ui/DateRangePicker'
import { MultiSelect, type MultiSelectOption } from '@/shared/ui/MultiSelect'
import {
  Button,
  Card,
  EmptyState,
  Segmented,
  Select,
  Skeleton,
} from '@/shared/ui/primitives'
import { SearchInput } from '@/shared/ui/SearchInput'
import { SortHeader, type SortState } from '@/shared/ui/SortHeader'

const PAGE_SIZES = [20, 50] as const

const VERDICTS: SaleVerdict[] = ['ok', 'suspicious', 'not_checkable']

/** «Diqqat talab qiladi» blokidagi qatorlar soni */
const ATTENTION_SIZE = 5

const orUndefined = (list: string[]): string[] | undefined =>
  list.length ? list : undefined

/** Dollardagi summa — jadvalda ham, blokda ham bir xil yoziladi */
const usd = (value: number | null): string =>
  value != null ? `${formatNumber(Math.round(value))} $` : '—'

export function SalesControlPage() {
  const { t } = useTranslation()
  const { can } = useAuth()
  const fmt = useDateFormat()

  const canReview = can('sales:review')
  const canImport = can('sales:import')

  /* Sukut: oxirgi 30 kun. Uzunroq davr birinchi ochilishda sekin
     bo'lardi (xulosa har so'rovda qaytadan hisoblanadi), qisqarog'i
     esa navbatni bo'sh ko'rsatardi. */
  const [range, setRange] = useState<DateRange>(() => resolvePreset('last30'))

  const [agentIds, setAgentIds] = useState<string[]>([])
  const [branches, setBranches] = useState<string[]>([])
  const [verdict, setVerdict] = useState<SaleVerdict | ''>('')
  const [rule, setRule] = useState<SaleRule | ''>('')
  /* Sukut — KO'RILMAGANLAR: bu tekshiruv navbati va sahifa ochilganda
     birinchi navbatda KUTAYOTGAN ish ko'rinishi kerak (shartnoma,
     5-bo'lim). Qaror qo'yilgan savdo yo'qolmaydi: «Oqlangan»,
     «Haqiqatan shubhali» yoki «Hammasi» bilan qaytib ko'riladi. */
  const [review, setReview] = useState<SaleReviewFilter>('new')

  const [search, setSearch] = useState('')
  const [applied, setApplied] = useState('')
  const [sort, setSort] = useState<SortState<SaleSort>>({
    field: 'date',
    order: 'desc',
  })
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0])

  /** Xronologiya oynasi — qator bosilganda ochiladi */
  const [tracked, setTracked] = useState<ComplianceRow | null>(null)
  /** Qaror oynasi — xronologiyadan chaqiriladi */
  const [picked, setPicked] = useState<ComplianceRow | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [branchesOpen, setBranchesOpen] = useState(false)
  /* «Diqqat talab qiladi» sukut bo'yicha OCHIQ: direktor sahifani
     aynan shu ro'yxat uchun ochadi. Yig'ib qo'yish esa kundalik ish
     qiladigan odam uchun — u pastdagi navbat bilan ishlaydi. */
  const [attentionOpen, setAttentionOpen] = useState(true)

  const since = toInputValue(range.from)
  const until = toInputValue(range.to)

  /* Qamrov — davr va kesim. Toifa/qoida/qaror BU YERDA YO'Q: ular
     ro'yxatni toraytiradi, qamrovni emas. Yuqoridagi uchta son aynan
     shu qamrov bo'yicha hisoblanadi (pastdagi izohga qarang). */
  const scope = useMemo(
    () => ({
      date_from: since,
      date_to: until,
      agent_ids: orUndefined(agentIds),
      branches: orUndefined(branches),
      search: applied || undefined,
    }),
    [since, until, agentIds, branches, applied],
  )

  const query: ComplianceQuery = {
    ...scope,
    verdict: verdict || undefined,
    rule: rule || undefined,
    review,
    page,
    page_size: pageSize,
    sort: sort.field,
    order: sort.order,
  }

  const list = useCompliance(query)
  /**
   * ⚠️ Sonlar QAMROV bo'yicha, ro'yxat filtri bo'yicha emas.
   *
   * Agar `verdict` ham yuborilsa, «Toza» tanlanganda qolgan ikkala
   * son nolga tushardi — ya'ni tanlov o'z asosini o'chirib qo'yardi
   * va ular tugma sifatida ishlamasdi. `rule` va `review` ham
   * qo'shilmaydi: «ko'rilmaganlar» kesimida «toza» va «tekshirib
   * bo'lmadi» sonlari ma'nosiz bo'lardi (ular hech qachon ko'rilmaydi).
   */
  const summary = useComplianceSummary(scope)

  /**
   * ⚠️ DIREKTOR UCHUN — eng katta summali ko'rilmagan shubhalilar.
   *
   * Sabab oddiy: 451 qatorli ro'yxatni hech kim boshdan-oyoq
   * o'qimaydi, rahbar esa eng katta puldan boshlaydi. Filtr EKRANDAGI
   * tanlovga ergashmaydi (`verdict`/`review`/`rule` bu yerda qat'iy):
   * blok «bu davrda nima kutyapti» degan savolga javob beradi va u
   * pastdagi ro'yxat qanday saralanganidan qat'i nazar bir xil
   * bo'lishi kerak.
   *
   * Yangi endpoint YO'Q — o'sha `/sales/compliance`, boshqa saralash
   * va besh qator bilan.
   */
  const attention = useCompliance({
    ...scope,
    verdict: 'suspicious',
    review: 'new',
    page: 1,
    page_size: ATTENTION_SIZE,
    sort: 'amount',
    order: 'desc',
  })

  const total = list.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const windowDays = list.data?.window_days ?? summary.data?.window_days

  /* Jumla — jadvalda EMAS, faqat shu blokda va xronologiya oynasida:
     jadvalda u qatorni uch barobar baland qilib qo'yardi. */
  const reasonOf = useSaleReason(windowDays)

  /* Har qanday o'zgarish birinchi sahifaga qaytaradi — aks holda
     5-sahifada turib filtrni toraytirgan odam bo'sh jadval ko'rardi
     va uni «ma'lumot yo'q» deb o'qirdi. */
  const reset =
    <T,>(apply: (value: T) => void) =>
    (value: T) => {
      apply(value)
      setPage(1)
    }

  const hasFilters =
    agentIds.length > 0 ||
    branches.length > 0 ||
    Boolean(verdict) ||
    Boolean(rule) ||
    review !== 'new' ||
    Boolean(applied)

  const clearFilters = () => {
    setAgentIds([])
    setBranches([])
    setVerdict('')
    setRule('')
    setReview('new')
    setSearch('')
    setApplied('')
    setPage(1)
  }

  /* ── Tanlov ro'yxatlari ─────────────────────────────────── */

  const agents = useAgents(true)
  const agentOptions = useMemo<MultiSelectOption[]>(
    () =>
      (agents.data ?? []).map((agent) => ({
        value: agent.id,
        label: agent.full_name,
        hint: agent.is_active ? agent.region : t('regions.inactive'),
      })),
    [agents.data, t],
  )

  const branchList = useSaleBranches()
  const branchOptions = useMemo<MultiSelectOption[]>(
    () =>
      (branchList.data ?? []).map((row) => ({
        value: row.branch,
        label: row.branch,
        hint: row.agent_name ?? t('sales.noAgent'),
      })),
    [branchList.data, t],
  )

  /* ── Excelga yuklash ────────────────────────────────────── */

  const [exporting, setExporting] = useState(false)
  const [exportFailed, setExportFailed] = useState(false)

  /** Fayl sarlavhasidagi «qaysi filtr bilan olingan» qatori.
   *
   *  Fayl pochta orqali yuborilganda kontekst yo'qoladi va bu ayniqsa
   *  shu hisobotda xavfli: filtri yozilmagan «45 ta shubhali savdo»
   *  butun yilga tegishli deb o'qilishi mumkin. */
  const describeScope = () =>
    [
      agentIds.length ? t('filters.agentCount', { count: agentIds.length }) : null,
      branches.length ? t('sales.branchCount', { count: branches.length }) : null,
      verdict ? t(`sales.verdict.${verdict}`) : null,
      rule ? rule : null,
      review ? t(`sales.review.${review}`) : null,
      applied ? t('sales.export.search', { value: applied }) : null,
    ]
      .filter(Boolean)
      .join(' · ')

  const runExport = async () => {
    if (exporting || !total) return
    setExporting(true)
    setExportFailed(false)
    try {
      /* Ekrandagi SAHIFA emas, butun tanlov. Sabab `export.ts` da:
         bir sahifalik fayl bilan sonni qayta hisoblab bo'lmaydi. */
      const { rows } = await fetchAllCompliance({
        ...query,
        page: undefined,
        page_size: undefined,
      })
      await exportCompliance({
        rows,
        summary: summary.data,
        t,
        since,
        until,
        scope: describeScope(),
        windowDays,
      })
    } catch {
      /* Sabab foydalanuvchiga hech narsa bermaydi — muhimi, tugma
         bosilib hech narsa bo'lmagandek ko'rinmasin */
      setExportFailed(true)
    } finally {
      setExporting(false)
    }
  }

  return (
    <Page>
      <PageHeader
        title={t('sales.title')}
        subtitle={t('sales.subtitle')}
        actions={
          /* ⚠️ TUGMALAR IXCHAM. Uchta to'liq yozuv sarlavha qatoriga
             sig'masdi va uchinchisi qirqilib turardi. Endi ikkilamchi
             ikkitasi tor ekranda faqat belgicha (nomi maslahatnomada
             va ekran o'quvchi uchun `aria-label` da), asosiy amal —
             import — esa har doim yozuvi bilan. */
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              variant="secondary"
              className="px-3 xl:px-4"
              onClick={runExport}
              disabled={!total || exporting}
              title={t('sales.export.hint')}
              aria-label={t('sales.export.button')}
            >
              <Sheet className="size-4" />
              <span className={exporting ? 'inline' : 'hidden xl:inline'}>
                {exporting ? t('sales.export.running') : t('sales.export.button')}
              </span>
            </Button>
            <Button
              variant="secondary"
              className="px-3 xl:px-4"
              onClick={() => setBranchesOpen(true)}
              title={t('sales.branches.title')}
              aria-label={t('sales.branches.button')}
            >
              <Store className="size-4" />
              <span className="hidden xl:inline">{t('sales.branches.button')}</span>
            </Button>
            {canImport && (
              <Button onClick={() => setImportOpen(true)} title={t('sales.import.hint')}>
                <Upload className="size-4" />
                {t('sales.import.button')}
              </Button>
            )}
          </div>
        }
      />

      {exportFailed && (
        <p className="rounded-xl bg-bad/[0.08] px-3.5 py-2.5 text-2xs leading-relaxed text-bad">
          {t('sales.export.failed')}
        </p>
      )}

      {/* ── Uch toifa ────────────────────────────────────────
          Uchalasi ham ko'rinadi va uchalasi ham bosiladi. Sonlar
          davr va kesim bo'yicha — pastdagi filtr ularni
          o'zgartirmaydi, aks holda tanlov o'z asosini yo'q qilardi.

          ⚠️ Kartochka IXCHAM: katta son va bitta yorliq. Avval har
          birida ikki qatorlik izoh turardi va uchalasi ekranning
          uchdan birini yeb qo'yardi — izoh endi maslahatnomada. */}
      <div className="grid gap-3 sm:grid-cols-3">
        {VERDICTS.map((key) => (
          <VerdictTile
            key={key}
            verdict={key}
            value={summary.data?.[key] ?? null}
            loading={summary.isLoading}
            active={verdict === key}
            onClick={() => reset(setVerdict)(verdict === key ? '' : key)}
          />
        ))}
      </div>

      {/* ── Diqqat talab qiladi ──────────────────────────────── */}
      {(attention.data?.items.length ?? 0) > 0 && (
        <Card className="animate-fade-up overflow-hidden">
          <button
            type="button"
            aria-expanded={attentionOpen}
            onClick={() => setAttentionOpen((open) => !open)}
            className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-250 ease-ios hover:bg-surface-2/40"
          >
            <span className="icon-tile size-8 shrink-0 bg-warn/10 text-warn">
              <TriangleAlert className="size-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold">
                {t('sales.attention.title')}
              </span>
              <span className="block truncate text-2xs text-muted">
                {t('sales.attention.hint')}
              </span>
            </span>
            <ChevronDown
              className={cn(
                'size-4 shrink-0 text-muted transition-transform duration-250 ease-ios',
                attentionOpen && 'rotate-180',
              )}
            />
          </button>

          {attentionOpen && (
            <ul className="border-t border-border">
              {attention.data?.items.map((row) => (
                <li key={row.id} className="border-b border-border/60 last:border-0">
                  <button
                    type="button"
                    onClick={() => setTracked(row)}
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors duration-250 ease-ios hover:bg-surface-2/60"
                  >
                    <span className="tnum w-[5.5rem] shrink-0 text-2xs text-muted">
                      {formatFullDate(`${row.occurred_on}T00:00:00`)}
                    </span>
                    <span
                      className="min-w-0 flex-1 truncate text-sm font-medium"
                      title={row.partner_name ?? row.partner_code}
                    >
                      {row.partner_name || row.partner_code}
                    </span>
                    <span className="tnum w-24 shrink-0 text-right text-sm font-semibold">
                      {usd(row.amount_usd)}
                    </span>
                    {/* Sabab jumlasi — aynan shu blokning ma'nosi.
                        Tor ekranda yashiriladi: bir qatorga sig'masa
                        u yerda ham o'ralib ketardi. */}
                    <span
                      className="hidden min-w-0 flex-[2] truncate text-2xs text-muted lg:block"
                      title={reasonOf(row)}
                    >
                      {reasonOf(row)}
                    </span>
                    <ChevronRight className="size-4 shrink-0 text-muted" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {/* ── Filtrlar ─────────────────────────────────────────── */}
      <div className="card animate-fade-up p-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-3">
          <div className="flex items-center gap-2 text-muted">
            <SlidersHorizontal className="size-4" />
            <span className="label-eyebrow">{t('filters.title')}</span>
          </div>

          <DateRangePicker value={range} onChange={reset(setRange)} />

          {agentOptions.length > 1 && (
            <MultiSelect
              icon={User}
              label={t('filters.agents')}
              options={agentOptions}
              value={agentIds}
              onChange={reset(setAgentIds)}
              summary={(count) => t('filters.agentCount', { count })}
            />
          )}

          {branchOptions.length > 1 && (
            <MultiSelect
              icon={Store}
              label={t('sales.branches.filter')}
              options={branchOptions}
              value={branches}
              onChange={reset(setBranches)}
              summary={(count) => t('sales.branchCount', { count })}
            />
          )}

          {/* ⚠️ Yorliqlar QISQA: «Har qanday xulosa» tanlagichga
              sig'masdi va «Har qanday q…» bo'lib qirqilardi. */}
          <Select
            compact
            icon={ShieldAlert}
            active={Boolean(verdict)}
            className="w-36"
            value={verdict}
            onChange={(e) => reset(setVerdict)(e.target.value as SaleVerdict | '')}
          >
            <option value="">{t('sales.filter.anyVerdict')}</option>
            {VERDICTS.map((value) => (
              <option key={value} value={value}>
                {t(`sales.verdict.${value}`)}
              </option>
            ))}
          </Select>

          <Select
            compact
            icon={Flag}
            active={Boolean(rule)}
            className="w-28"
            value={rule}
            onChange={(e) => reset(setRule)(e.target.value as SaleRule | '')}
          >
            <option value="">{t('sales.filter.anyRule')}</option>
            {SALE_RULES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>

          {/* Qaror holati. «Hammasi» ham bor va u ANIQ qiymat
              (`review=all`) yuboradi: parametrni tashlab ketish
              backendda «ko'rilmaganlar» degani bo'lardi va yorliq
              yolg'on gapirardi. */}
          <Select
            compact
            icon={ClipboardCheck}
            active={review !== 'new'}
            className="w-48"
            value={review}
            onChange={(e) => reset(setReview)(e.target.value as SaleReviewFilter)}
          >
            {REVIEW_STATES.map((value) => (
              <option key={value} value={value}>
                {t(`sales.review.${value}`)}
              </option>
            ))}
          </Select>

          {hasFilters && (
            <Button variant="ghost" size="sm" className="ml-auto" onClick={clearFilters}>
              <RotateCcw className="size-3.5" />
              {t('filters.reset')}
            </Button>
          )}
        </div>

        {/* Oyna ochiq yoziladi: savdoda vaqt yo'q, shuning uchun
            qidiruv oynasi = savdo kuni + oldingi N kun. Buni aytmasak
            «kecha gaplashgan edim-ku» degan e'tirozga javob
            bo'lmasdi. Alohida blok emas, filtrlarning ostidagi bitta
            kulrang qator: u har kuni o'qiladigan matn emas. */}
        {windowDays != null && (
          <p className="mt-3 border-t border-border/60 pt-2.5 text-2xs leading-relaxed text-muted">
            {t('sales.windowNote', { count: windowDays })}
          </p>
        )}
      </div>

      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
          <SearchInput
            className="min-w-[220px] flex-1"
            placeholder={t('sales.searchPlaceholder')}
            value={search}
            onChange={reset((next: string) => {
              setSearch(next)
              setApplied(next.trim())
            })}
          />
          <span className="text-2xs text-muted">
            {list.data ? t('sales.found', { count: total }) : ''}
          </span>
          <Segmented
            value={String(pageSize)}
            onChange={(value) => reset(setPageSize)(Number(value))}
            items={PAGE_SIZES.map((size) => ({
              value: String(size),
              label: t('sales.perPage', { count: size }),
            }))}
          />
        </div>

        {/* Kodlarning ma'nosi — bir marta, hamma qator uchun */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border px-4 py-2.5">
          <RuleLegend windowDays={windowDays} />
          <span className="ml-auto inline-flex items-center gap-1.5 text-2xs text-muted">
            <CircleHelp className="size-3.5" />
            {t('sales.rowHint')}
          </span>
        </div>

        {list.isLoading ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 10 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : !list.data?.items.length ? (
          <EmptyState
            message={t('table.empty')}
            hint={
              applied
                ? t('sales.emptySearchHint')
                : review === 'new'
                  ? t('sales.emptyQueueHint')
                  : t('sales.emptyHint')
            }
            action={
              hasFilters
                ? { label: t('filters.reset'), onClick: clearFilters }
                : undefined
            }
          />
        ) : (
          /* ⚠️ `scroll-x` — jadval o'z konteynerida suriladi, SAHIFA
             emas. `table-fixed` + foizli kengliklar keng monitorda
             bo'sh joy qoldirmaydi (ustunlar nisbat bilan yoyiladi),
             `min-w` esa tor ekranda ularni siqilib ketishdan saqlaydi. */
          <div className="scroll-x">
            <table className="w-full min-w-[68rem] table-fixed text-sm">
              <colgroup>
                <col className="w-[9%]" />
                <col className="w-[20%]" />
                <col className="w-[15%]" />
                <col className="w-[9%]" />
                <col className="w-[19%]" />
                <col className="w-[15%]" />
                <col className="w-[13%]" />
              </colgroup>
              <thead>
                <tr className="border-b border-border text-left">
                  {/* Saralanadigan ustunlar — backenddagi
                      `ComplianceSort` bilan bir xil to'rttasi.
                      «Xulosa» bo'yicha saralash YO'Q: uni backend
                      qabul qilmaydi va toifalar aralashib ketardi;
                      toifa uchun yuqoridagi kartochkalar bor. */}
                  <SortHeader
                    field="date"
                    label={t('sales.col.date')}
                    firstOrder="desc"
                    state={sort}
                    onChange={reset(setSort)}
                  />
                  <SortHeader
                    field="partner"
                    label={t('sales.col.client')}
                    state={sort}
                    onChange={reset(setSort)}
                  />
                  <SortHeader
                    field="agent"
                    label={t('sales.col.branchAgent')}
                    state={sort}
                    onChange={reset(setSort)}
                  />
                  <SortHeader
                    field="amount"
                    label={t('sales.col.amountUsd')}
                    align="right"
                    firstOrder="desc"
                    state={sort}
                    onChange={reset(setSort)}
                  />
                  <Th>{t('sales.col.verdict')}</Th>
                  <Th>{t('sales.col.lastCall')}</Th>
                  <Th>{t('sales.col.decision')}</Th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((row) => (
                  /* ⚠️ BALANDLIK QAT'IY BELGILANGAN. `h-14` jadval
                     qatorida eng KICHIK balandlik degani, ya'ni
                     kafolat faqat hech bir katak undan oshmasa
                     ishlaydi — shuning uchun har katakda ko'pi bilan
                     ikki qator matn bor va hammasi `truncate`. */
                  <tr
                    key={row.id}
                    onClick={() => setTracked(row)}
                    tabIndex={0}
                    role="button"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        setTracked(row)
                      }
                    }}
                    className={cn(
                      'h-14 cursor-pointer border-b border-border/60 align-middle',
                      'transition-colors last:border-0',
                      'hover:bg-surface-2/60 focus-visible:bg-surface-2/60 focus-visible:outline-none',
                    )}
                  >
                    {/* Sana — vaqtsiz. Ostida SAP dagi operatsiya
                        raqami: rahbar shu raqam bilan SAP da qatorni
                        topadi, busiz dalilni tekshirib bo'lmaydi. */}
                    <Td>
                      <div className="tnum truncate text-sm">
                        {formatFullDate(`${row.occurred_on}T00:00:00`)}
                      </div>
                      <div className="tnum truncate text-2xs text-muted">
                        {row.external_id}
                      </div>
                    </Td>

                    {/* Mijoz: nomi, ostida kodi va telefoni. Ikkalasi
                        ham DALIL — kod SAP uchun, telefon esa
                        qo'ng'iroqlar tarixi uchun. */}
                    <Td>
                      <div
                        className="truncate font-medium"
                        title={row.partner_name ?? row.partner_code}
                      >
                        {/* Nomi bo'lmasa KOD sarlavha bo'ladi: «—»
                            hech narsa bermaydi, kod esa SAP da
                            qidirsa ham ishlaydi */}
                        {row.partner_name || row.partner_code}
                      </div>
                      <div className="tnum truncate text-2xs text-muted">
                        {row.partner_code}
                        {row.phone ? ` · ${row.phone}` : ''}
                      </div>
                    </Td>

                    <Td>
                      <div className="truncate" title={row.branch ?? undefined}>
                        {row.branch ?? '—'}
                      </div>
                      <div
                        className={cn(
                          'truncate text-2xs',
                          row.agent_name ? 'text-muted' : 'text-warn',
                        )}
                      >
                        {row.agent_name ?? t('sales.noAgent')}
                        {row.direction ? ` · ${row.direction}` : ''}
                      </div>
                    </Td>

                    {/* Dollar — asosiy son (taqqoslash faqat unda
                        ma'noli), hujjat valyutasi ostida va FAQAT u
                        boshqa bo'lsa: dollarlik savdoda «340 $» ni
                        ikki marta yozish shovqin. */}
                    <Td className="text-right">
                      <div className="tnum truncate font-semibold">
                        {usd(row.amount_usd)}
                      </div>
                      {row.currency !== 'USD' && row.amount != null && (
                        <div className="tnum truncate text-2xs text-muted">
                          {formatNumber(Math.round(row.amount))} {row.currency}
                        </div>
                      )}
                    </Td>

                    {/* ⚠️ FAQAT HOLAT KODLARI, bitta qatorda.
                        Sabab matni («Umumiy kod: bitta kod ostida ko'p
                        mijoz…», «Oldingi savdo … orasida 0 ta suhbat»)
                        BU YERGA YOZILMAYDI — u katakda paragrafga
                        aylanadi. Ma'nosi tepadagi izohda, tafsiloti
                        esa qator bosilganda ochiladigan oynada. */}
                    <Td>
                      <div className="flex items-center gap-1.5 overflow-hidden">
                        <VerdictBadge
                          verdict={row.verdict}
                          skipReason={row.skip_reason}
                        />
                        {row.skip_reason && <SkipBadge reason={row.skip_reason} />}
                        <RuleBadges
                          rules={row.broken_rules}
                          windowDays={windowDays}
                          hints={ruleHints(row, t, fmt.date)}
                        />
                      </div>
                    </Td>

                    {/* Oxirgi qo'ng'iroq — ustunlarning eng qimmati.
                        «Suhbat bo'lmagan» bo'sh katak bilan
                        almashtirilmaydi: bo'sh katak «ma'lumot
                        yuklanmadi» deb o'qilardi, bu esa aynan
                        teskari xulosa. Lekin u QIZIL YORLIQ ham
                        emas — rang faqat odam qaror qilgandan keyin
                        paydo bo'ladi. */}
                    <Td>
                      {row.last_call_at ? (
                        <>
                          <div className="tnum truncate text-sm">
                            {fmt.dateTime(row.last_call_at)}
                          </div>
                          <div className="truncate text-2xs text-muted">
                            {row.last_call_agent ?? '—'}
                            {row.days_before != null
                              ? ` · ${t('sales.daysBefore', { count: row.days_before })}`
                              : ''}
                          </div>
                        </>
                      ) : (
                        <span className="truncate text-xs text-muted">
                          {t('sales.noCallPlain')}
                        </span>
                      )}
                    </Td>

                    {/* Qaror: yorliq va ostida KIM qo'ygani. Sabab va
                        izoh maslahatnomada — ular katakda ikki-uch
                        qator bo'lib, qatorni cho'zib yuborardi.
                        To'lig'i qaror oynasida turadi. */}
                    <Td>
                      <ReviewBadge review={row.review} />
                      {row.review && (
                        <div
                          className="mt-1 truncate text-2xs text-muted"
                          title={reviewTitle(row, t, fmt.date)}
                        >
                          {t('sales.decision.by', {
                            who: row.review.reviewed_by ?? '—',
                            when: row.review.reviewed_at
                              ? fmt.date(row.review.reviewed_at)
                              : '—',
                          })}
                        </div>
                      )}
                    </Td>
                  </tr>
                ))}
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

      {/* Qator bosilsa AVVAL xronologiya ochiladi — «nega shubhali»
          degan savolga javob qarordan oldin kerak. Qaror oynasi esa
          o'sha yerdan chaqiriladi (ruxsati borlarda). */}
      <SaleTimelineModal
        sale={tracked}
        windowDays={windowDays}
        onClose={() => setTracked(null)}
        onReview={
          canReview
            ? (row) => {
                setTracked(null)
                setPicked(row)
              }
            : undefined
        }
      />
      <ReviewModal
        sale={picked}
        windowDays={windowDays}
        onClose={() => setPicked(null)}
      />
      <ImportModal open={importOpen} onClose={() => setImportOpen(false)} />
      <BranchesModal
        open={branchesOpen}
        onClose={() => setBranchesOpen(false)}
        canEdit={canReview}
      />
    </Page>
  )
}

/* ── Jadvalning kichik qismlari ──────────────────────────── */

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="truncate px-4 py-3 text-2xs font-medium uppercase tracking-wider text-muted">
      {children}
    </th>
  )
}

/** Katak — hamma joyda bir xil bo'shliq va bir xil `overflow` */
function Td({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <td className={cn('overflow-hidden px-4 py-2 align-middle', className)}>
      {children}
    </td>
  )
}

/** Qoida yorlig'ining maslahatnomasiga qo'shiladigan DALIL */
function ruleHints(
  row: ComplianceRow,
  t: TFunction,
  date: (value: string) => string,
): Partial<Record<SaleRule, string>> {
  const hints: Partial<Record<SaleRule, string>> = {}

  if (row.broken_rules.includes('R2')) {
    hints.R2 = row.previous_sale_on
      ? t('sales.betweenCalls', {
          date: date(`${row.previous_sale_on}T00:00:00`),
          count: row.calls_between,
        })
      : t('sales.noPreviousSale')
  }
  if (row.broken_rules.includes('R3')) {
    hints.R3 = t('sales.callsTotal', { count: row.calls_total })
  }

  return hints
}

/** Qarorning to'liq matni — maslahatnomada (sabab va izoh bilan) */
function reviewTitle(
  row: ComplianceRow,
  t: TFunction,
  date: (value: string) => string,
): string | undefined {
  if (!row.review) return undefined

  return [
    row.review.reason ? t(`sales.reason.${row.review.reason}`) : null,
    t('sales.decision.by', {
      who: row.review.reviewed_by ?? '—',
      when: row.review.reviewed_at ? date(row.review.reviewed_at) : '—',
    }),
    row.review.note ? `«${row.review.note}»` : null,
  ]
    .filter(Boolean)
    .join('\n')
}

/* ── Toifa kartochkasi ───────────────────────────────────── */

const TILE: Record<
  SaleVerdict,
  { icon: LucideIcon; tone: string; tile: string; ring: string }
> = {
  ok: {
    icon: ShieldCheck,
    tone: 'text-good',
    tile: 'bg-good/10 text-good',
    ring: 'ring-good/40',
  },
  suspicious: {
    icon: TriangleAlert,
    tone: 'text-warn',
    tile: 'bg-warn/10 text-warn',
    ring: 'ring-warn/40',
  },
  not_checkable: {
    icon: CircleHelp,
    tone: 'text-muted',
    tile: '',
    ring: 'ring-border',
  },
}

function VerdictTile({
  verdict,
  value,
  loading,
  active,
  onClick,
}: {
  verdict: SaleVerdict
  value: number | null
  loading?: boolean
  active: boolean
  onClick: () => void
}) {
  const { t } = useTranslation()
  const look = TILE[verdict]
  const Icon = look.icon

  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      /* Uzun izoh SHU YERDA qoladi — ekranda emas. «Tekshirishning
         iloji yo'q. Bu "toza" degani EMAS» degan jumla kartochkada
         ikki qator bo'lib turardi va uchalasi birgalikda ekranning
         uchdan birini yeb qo'yardi. */
      title={t(`sales.verdictHint.${verdict}`)}
      className={cn(
        'card card-hover flex items-center gap-3 p-3.5 text-left',
        'transition-all duration-250 ease-ios active:scale-[0.99]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
        active && `ring-2 ring-inset ${look.ring}`,
      )}
    >
      <span className={cn('icon-tile size-9 shrink-0', look.tile)}>
        <Icon className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        {loading ? (
          <Skeleton className="h-7 w-16" />
        ) : (
          <div className={cn('tnum text-2xl font-semibold leading-none', look.tone)}>
            {value != null ? formatNumber(value) : '—'}
          </div>
        )}
        <div className="mt-1 truncate text-2xs text-muted">
          {t(`sales.verdict.${verdict}`)}
        </div>
      </div>
      {/* Kartochka FILTR ekani ko'rinib tursin: faol holatda ramka
          va belgi, aks holda uni oddiy ko'rsatkich deb o'ylashadi */}
      <Check
        className={cn(
          'size-4 shrink-0 text-accent transition-opacity duration-250 ease-ios',
          active ? 'opacity-100' : 'opacity-0',
        )}
      />
    </button>
  )
}
