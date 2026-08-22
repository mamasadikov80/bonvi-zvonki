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
 *   · har qatorda DALIL bor va u qisqartirilmaydi: rahbar sonni
 *     qo'lda qayta hisoblab tekshirishi kerak (shartnoma, 4-bo'lim).
 *
 * ⚠️ Sana filtri `YYYY-MM-DD` yuboradi, ISO vaqt EMAS: savdoda vaqt
 * yo'q (`sales.occurred_on` — `date`), shuning uchun ilovadagi
 * `rangeToQuery` bu yerda ishlatilmaydi.
 */

import {
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Flag,
  RotateCcw,
  Sheet,
  ShieldAlert,
  SlidersHorizontal,
  Store,
  Upload,
  User,
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
import { ReviewBadge, RuleBadges, RuleLegend, VerdictBadge } from '@/modules/sales/badges'
import { BranchesModal } from '@/modules/sales/BranchesModal'
import { exportCompliance } from '@/modules/sales/export'
import { ImportModal } from '@/modules/sales/ImportModal'
import { ReviewModal } from '@/modules/sales/ReviewModal'
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

const PAGE_SIZES = [20, 50] as const

const VERDICTS: SaleVerdict[] = ['ok', 'suspicious', 'not_checkable']

const orUndefined = (list: string[]): string[] | undefined =>
  list.length ? list : undefined

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
  /* Sukut — KO'RILMAGANLAR: bu tekshiruv navbati, ko'rib bo'lingan
     savdo unda turishi kerak emas (shartnoma, 5-bo'lim).

     ⚠️ «Hammasi» varianti yo'q — sabab `api.ts` da: backendda
     parametrning sukut qiymati `new`, ya'ni uni yubormaslik
     «hammasi» emas, «ko'rilmaganlar» degani. */
  const [review, setReview] = useState<SaleReviewFilter>('new')

  const [search, setSearch] = useState('')
  const [applied, setApplied] = useState('')
  const [sort, setSort] = useState<SortState<SaleSort>>({
    field: 'date',
    order: 'desc',
  })
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0])

  const [picked, setPicked] = useState<ComplianceRow | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [branchesOpen, setBranchesOpen] = useState(false)

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

  const total = list.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const windowDays = list.data?.window_days ?? summary.data?.window_days

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
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              onClick={runExport}
              disabled={!total || exporting}
              title={t('sales.export.hint')}
            >
              <Sheet className="size-4" />
              {exporting ? t('sales.export.running') : t('sales.export.button')}
            </Button>
            <Button variant="secondary" onClick={() => setBranchesOpen(true)}>
              <Store className="size-4" />
              {t('sales.branches.button')}
            </Button>
            {canImport && (
              <Button onClick={() => setImportOpen(true)}>
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
          o'zgartirmaydi, aks holda tanlov o'z asosini yo'q qilardi. */}
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

      {/* ── Filtrlar ─────────────────────────────────────────── */}
      <div className="card animate-fade-up p-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
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

          <Select
            compact
            icon={ShieldAlert}
            active={Boolean(verdict)}
            className="w-44"
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
            className="w-36"
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

          {/* Qaror holati. Uchta qiymat — «hammasi» YO'Q va bu
              ataylab: backendda sukut qiymat `new`, ya'ni bo'sh
              tanlov «hammasi» emas, «ko'rilmaganlar» bo'lardi va
              yorliq yolg'on gapirardi. */}
          <Select
            compact
            icon={ClipboardCheck}
            active={review !== 'new'}
            className="w-52"
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
      </div>

      {/* Oyna ochiq yoziladi: savdoda vaqt yo'q, shuning uchun qidiruv
          oynasi = savdo kuni + oldingi N kun. Buni aytmasak «kecha
          gaplashgan edim-ku» degan e'tirozga javob bo'lmasdi. */}
      {windowDays != null && (
        <p className="rounded-xl bg-surface-2/50 px-3.5 py-2.5 text-2xs leading-relaxed text-muted">
          {t('sales.windowNote', { count: windowDays })}
        </p>
      )}

      <RuleLegend windowDays={windowDays} />

      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
          <SearchInput
            className="min-w-[240px] flex-1"
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
          <div className="scroll-x">
            <table className="w-full text-sm">
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
                  <th className="px-4 py-3 text-2xs font-medium uppercase tracking-wider text-muted">
                    {t('sales.col.verdict')}
                  </th>
                  <th className="px-4 py-3 text-2xs font-medium uppercase tracking-wider text-muted">
                    {t('sales.col.rules')}
                  </th>
                  <th className="px-4 py-3 text-2xs font-medium uppercase tracking-wider text-muted">
                    {t('sales.col.lastCall')}
                  </th>
                  <th className="px-4 py-3 text-2xs font-medium uppercase tracking-wider text-muted">
                    {t('sales.col.decision')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((row) => (
                  <tr
                    key={row.id}
                    onClick={canReview ? () => setPicked(row) : undefined}
                    className={cn(
                      'border-b border-border/60 align-top transition-colors last:border-0',
                      canReview && 'cursor-pointer hover:bg-surface-2/60',
                    )}
                  >
                    {/* Sana — vaqtsiz. Ostida SAP dagi operatsiya
                        raqami: rahbar shu raqam bilan SAP da qatorni
                        topadi, busiz dalilni tekshirib bo'lmaydi. */}
                    <td className="whitespace-nowrap px-4 py-3">
                      <div className="tnum text-sm">
                        {formatFullDate(`${row.occurred_on}T00:00:00`)}
                      </div>
                      <div className="tnum text-2xs text-muted">{row.external_id}</div>
                    </td>

                    {/* Mijoz: nomi, ostida kodi va telefoni. Ikkalasi
                        ham DALIL — kod SAP uchun, telefon esa
                        qo'ng'iroqlar tarixi uchun. */}
                    <td className="px-4 py-3">
                      <div className="max-w-[260px] truncate font-medium">
                        {/* Nomi bo'lmasa KOD sarlavha bo'ladi: «—»
                            hech narsa bermaydi, kod esa SAP da
                            qidirsa ham ishlaydi */}
                        {row.partner_name || row.partner_code}
                      </div>
                      <div className="tnum text-2xs text-muted">
                        {row.partner_code}
                        {row.phone ? ` · ${row.phone}` : ''}
                      </div>
                    </td>

                    <td className="px-4 py-3">
                      <div className="max-w-[200px] truncate">{row.branch ?? '—'}</div>
                      <div
                        className={cn(
                          'truncate text-2xs',
                          row.agent_name ? 'text-muted' : 'text-warn',
                        )}
                      >
                        {row.agent_name ?? t('sales.noAgent')}
                        {row.direction ? ` · ${row.direction}` : ''}
                      </div>
                    </td>

                    {/* Dollar — asosiy son (taqqoslash faqat unda
                        ma'noli), hujjat valyutasi ostida. Summa
                        `null` bo'lishi mumkin: SAP eksportida katak
                        bo'sh qolgan qatorlar uchraydi. */}
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <div className="tnum font-semibold">
                        {row.amount_usd != null
                          ? `${formatNumber(Math.round(row.amount_usd))} $`
                          : '—'}
                      </div>
                      {row.currency !== 'USD' && row.amount != null && (
                        <div className="tnum text-2xs text-muted">
                          {formatNumber(Math.round(row.amount))} {row.currency}
                        </div>
                      )}
                    </td>

                    <td className="px-4 py-3">
                      <VerdictBadge verdict={row.verdict} skipReason={row.skip_reason} />
                      {row.verdict === 'not_checkable' && row.skip_reason && (
                        <div className="mt-1 max-w-[180px] text-2xs leading-relaxed text-muted">
                          {t(`sales.skip.${row.skip_reason}`)}
                        </div>
                      )}
                    </td>

                    {/* Qoidalar + ularning DALILI. Yorliqning o'zi
                        yetmaydi: «R2» nima ekanini bilgan odam ham
                        «oldingi savdo qachon edi?» deb so'raydi. */}
                    <td className="px-4 py-3">
                      <RuleBadges rules={row.broken_rules} windowDays={windowDays} />
                      {row.broken_rules.length > 0 && (
                        <div className="mt-1 max-w-[220px] space-y-0.5 text-2xs leading-relaxed text-muted">
                          {row.broken_rules.includes('R2') && (
                            <div>
                              {row.previous_sale_on
                                ? t('sales.betweenCalls', {
                                    date: formatFullDate(
                                      `${row.previous_sale_on}T00:00:00`,
                                    ),
                                    count: row.calls_between,
                                  })
                                : t('sales.noPreviousSale')}
                            </div>
                          )}
                          {row.broken_rules.includes('R3') && (
                            <div className="text-bad">
                              {t('sales.callsTotal', { count: row.calls_total })}
                            </div>
                          )}
                        </div>
                      )}
                    </td>

                    {/* Oxirgi qo'ng'iroq — ustunlarning eng qimmati.
                        «Umuman yo'q» bo'sh katak bilan almashtirilmaydi:
                        bo'sh katak «ma'lumot yuklanmadi» deb o'qilardi,
                        bu esa aynan teskari xulosa. */}
                    <td className="whitespace-nowrap px-4 py-3">
                      {row.last_call_at ? (
                        <>
                          <div className="tnum text-sm">
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
                        <Badge tone="bad">{t('sales.noCallEver')}</Badge>
                      )}
                    </td>

                    <td className="px-4 py-3">
                      <ReviewBadge review={row.review} />
                      {row.review?.reason && (
                        <div className="mt-1 text-2xs text-muted">
                          {t(`sales.reason.${row.review.reason}`)}
                        </div>
                      )}
                    </td>
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

/* ── Toifa kartochkasi ───────────────────────────────────── */

const TILE: Record<SaleVerdict, { tone: string; ring: string }> = {
  ok: { tone: 'text-good', ring: 'ring-good/40' },
  suspicious: { tone: 'text-warn', ring: 'ring-warn/40' },
  not_checkable: { tone: 'text-muted', ring: 'ring-border' },
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

  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      title={t(`sales.verdictHint.${verdict}`)}
      className={cn(
        'card card-hover flex items-start gap-3.5 p-5 text-left',
        'transition-all duration-250 ease-ios active:scale-[0.99]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
        active && `ring-2 ring-inset ${look.ring}`,
      )}
    >
      <div className="min-w-0 flex-1">
        {loading ? (
          <Skeleton className="h-8 w-20" />
        ) : (
          <div className={cn('tnum text-[1.75rem] font-semibold leading-none', look.tone)}>
            {value != null ? formatNumber(value) : '—'}
          </div>
        )}
        <div className="mt-1.5 truncate text-[0.8125rem] text-muted">
          {t(`sales.verdict.${verdict}`)}
        </div>
        <div className="mt-1 text-2xs leading-relaxed text-muted/80">
          {t(`sales.verdictHint.${verdict}`)}
        </div>
      </div>
    </button>
  )
}
