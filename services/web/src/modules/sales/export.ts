/**
 * Savdo nazoratini Excelga chiqarish.
 *
 * NEGA BU KERAK — bu qulaylik emas, TALAB (shartnoma, 4-bo'lim:
 * «rahbar sonni qo'lda qayta hisoblab ko'rmoqchi»). Shuning uchun
 * faylda dalil ustunlarining HAMMASI bor: oxirgi qo'ng'iroq qachon
 * va kim bilan bo'lgani, savdodan necha kun oldin, oldingi savdo,
 * orasidagi va jami suhbatlar soni, mijoz kodi va telefoni. Bularsiz
 * faylni SAP bilan solishtirib bo'lmaydi.
 *
 * ⚠️ EKRANDAGI SAHIFA EMAS, BUTUN TANLOV. Ekranda 20–50 qator turadi;
 * faylga esa filtrga tushgan hammasi tushadi (`fetchAllCompliance`).
 * Bir sahifalik fayl «shubhalilar 12 ta» degan yolg'on xulosa berardi.
 *
 * Kutubxona DINAMIK import qilinadi — u faqat tugma bosilganda kerak
 * (`activity/export.ts` bilan bir xil sabab).
 */

import type { TFunction } from 'i18next'
import type { CellObject, Row, SheetData } from 'write-excel-file/browser'

import type {
  ComplianceRow,
  ComplianceSummary,
  SaleVerdict,
} from '@/modules/sales/api'
import { formatFullDate, formatFullDateTime } from '@/shared/lib/date'

/* ── Ranglar — ilovaning yorug' mavzusidagi qiymatlari ───── */

const NAVY = '#215A8C'
const GOOD = '#1E8052'
const WARN = '#B35C05'
const BAD = '#CC1F36'
const MUTED = '#6B7280'
const BAND = '#F4F7FA'

const NUM = '#,##0'
/** Pul — uch xonali kasr bazadagidek (`numeric(18,3)`) emas, ikkita:
 *  hisobotda uchinchi xona hech qachon o'qilmaydi, lekin ustunni
 *  kengaytirib jadvalni buzadi. */
const MONEY = '#,##0.00'
const DATE = 'dd.mm.yyyy'
const DATETIME = 'dd.mm.yyyy hh:mm'

/* ── Kataklar ─────────────────────────────────────────────── */

function text(value: string | null | undefined, style: CellObject = {}): CellObject {
  if (!value) return { ...style }
  return { value, type: String, ...style }
}

function num(value: number | null | undefined, style: CellObject = {}): CellObject {
  if (value == null) return { ...style }
  return { value, type: Number, format: NUM, ...style }
}

function money(value: number | null | undefined, style: CellObject = {}): CellObject {
  if (value == null) return { ...style }
  return { value, type: Number, format: MONEY, ...style }
}

/**
 * `YYYY-MM-DD` → Excel sanasi.
 *
 * ⚠️ `new Date('2026-08-14')` UTC yarim tunini beradi va bu yerda
 * aynan SHU kerak: kutubxona sanani `getTime()` orqali Excel raqamiga
 * aylantiradi, mahalliy yarim tun berilsa (Toshkentda UTC+5) fayl
 * sanani bir kun oldingisi qilib ko'rsatardi.
 */
function day(value: string | null | undefined, style: CellObject = {}): CellObject {
  if (!value) return { ...style }
  return { value: new Date(value), type: Date, format: DATE, ...style }
}

/**
 * ISO vaqt → Excel sanasi, EKRANDAGI (mahalliy) ko'rinishda.
 *
 * ⚠️ To'g'ridan-to'g'ri `new Date(iso)` bermaydi: kutubxona uni UTC
 * deb o'qiydi va Toshkentda ekranda `14:22` turgan qo'ng'iroq faylda
 * `09:22` bo'lib chiqardi — ya'ni fayl ekranga zid gapirardi.
 * Shuning uchun mahalliy soat-daqiqa UTC sifatida qayta yig'iladi.
 */
function moment(value: string | null | undefined, style: CellObject = {}): CellObject {
  if (!value) return { ...style }
  const d = new Date(value)
  const shifted = new Date(
    Date.UTC(d.getFullYear(), d.getMonth(), d.getDate(), d.getHours(), d.getMinutes()),
  )
  return { value: shifted, type: Date, format: DATETIME, ...style }
}

const VERDICT_COLOR: Record<SaleVerdict, string | undefined> = {
  ok: GOOD,
  suspicious: WARN,
  not_checkable: MUTED,
}

/* ── Ustunlar ─────────────────────────────────────────────── */

interface Column {
  header: string
  width: number
  cell: (row: ComplianceRow, base: CellObject) => CellObject
}

function columns(t: TFunction, windowDays?: number): Column[] {
  const label = (key: string, value: string | null | undefined) =>
    value ? t(`${key}.${value}`, { defaultValue: value }) : ''

  return [
    {
      header: t('sales.col.date'),
      width: 12,
      cell: (row, base) => day(row.occurred_on, { align: 'center', ...base }),
    },
    {
      /* SAP dagi `Номер операции`. Faylning butun ma'nosi shunda:
         rahbar shu raqam bilan SAP dagi qatorni topadi. */
      header: t('sales.col.operation'),
      width: 13,
      cell: (row, base) => text(row.external_id, { textColor: MUTED, ...base }),
    },
    {
      header: t('sales.col.client'),
      width: 32,
      cell: (row, base) => text(row.partner_name, base),
    },
    {
      header: t('sales.col.code'),
      width: 11,
      cell: (row, base) => text(row.partner_code, { textColor: MUTED, ...base }),
    },
    {
      header: t('sales.col.phone'),
      width: 16,
      cell: (row, base) => text(row.phone, base),
    },
    {
      header: t('sales.col.branch'),
      width: 22,
      cell: (row, base) => text(row.branch, base),
    },
    {
      header: t('sales.col.direction'),
      width: 12,
      cell: (row, base) => text(row.direction, { textColor: MUTED, ...base }),
    },
    {
      header: t('sales.col.agent'),
      width: 20,
      /* Xodimsiz savdo bo'sh EMAS, ochiq yoziladi: `Зухриддин`
         ATAYLAB bog'lanmagan va bo'sh katak buni nosozlik deb
         ko'rsatardi. */
      cell: (row, base) =>
        row.agent_name
          ? text(row.agent_name, base)
          : text(t('sales.noAgent'), { textColor: MUTED, ...base }),
    },
    {
      header: t('sales.col.amountUsd'),
      width: 14,
      cell: (row, base) => money(row.amount_usd, { fontWeight: 'bold', ...base }),
    },
    {
      header: t('sales.col.amount'),
      width: 16,
      cell: (row, base) => money(row.amount, base),
    },
    {
      header: t('sales.col.currency'),
      width: 9,
      cell: (row, base) => text(row.currency, { align: 'center', ...base }),
    },
    {
      header: t('sales.col.verdict'),
      width: 18,
      cell: (row, base) =>
        text(label('sales.verdict', row.verdict), {
          textColor: VERDICT_COLOR[row.verdict],
          fontWeight: 'bold',
          ...base,
        }),
    },
    {
      header: t('sales.col.skipReason'),
      width: 26,
      cell: (row, base) =>
        text(label('sales.skip', row.skip_reason), { textColor: MUTED, ...base }),
    },
    {
      header: t('sales.col.rules'),
      width: 14,
      cell: (row, base) =>
        text(row.broken_rules.join(', '), {
          textColor: row.broken_rules.length ? WARN : undefined,
          align: 'center',
          ...base,
        }),
    },
    {
      /* Oyna faylda ham yoziladi: sozlama o'zgarsa, eski fayl qaysi
         chegara bilan olinganini o'zi aytib turadi */
      header: t('sales.col.window'),
      width: 10,
      cell: (_row, base) => num(windowDays ?? null, { align: 'center', ...base }),
    },
    {
      header: t('sales.col.lastCall'),
      width: 18,
      cell: (row, base) =>
        row.last_call_at
          ? moment(row.last_call_at, base)
          : text(t('sales.noCallEver'), { textColor: BAD, ...base }),
    },
    {
      header: t('sales.col.lastCallAgent'),
      width: 20,
      cell: (row, base) => text(row.last_call_agent, base),
    },
    {
      header: t('sales.col.daysBefore'),
      width: 14,
      cell: (row, base) => num(row.days_before, { align: 'center', ...base }),
    },
    {
      header: t('sales.col.previousSale'),
      width: 13,
      cell: (row, base) => day(row.previous_sale_on, { align: 'center', ...base }),
    },
    {
      header: t('sales.col.callsBetween'),
      width: 14,
      cell: (row, base) =>
        num(row.calls_between, {
          align: 'center',
          textColor: row.calls_between === 0 ? WARN : undefined,
          ...base,
        }),
    },
    {
      header: t('sales.col.callsTotal'),
      width: 13,
      cell: (row, base) =>
        num(row.calls_total, {
          align: 'center',
          textColor: row.calls_total === 0 ? BAD : undefined,
          ...base,
        }),
    },
    {
      header: t('sales.col.decision'),
      width: 18,
      cell: (row, base) =>
        row.review
          ? text(label('sales.review', row.review.status), {
              textColor: row.review.status === 'justified' ? GOOD : BAD,
              fontWeight: 'bold',
              ...base,
            })
          : text(t('sales.review.new'), { textColor: MUTED, ...base }),
    },
    {
      header: t('sales.col.decisionReason'),
      width: 18,
      cell: (row, base) => text(label('sales.reason', row.review?.reason), base),
    },
    {
      header: t('sales.col.note'),
      width: 34,
      cell: (row, base) => text(row.review?.note, { wrap: true, ...base }),
    },
    {
      header: t('sales.col.reviewedBy'),
      width: 20,
      cell: (row, base) => text(row.review?.reviewed_by, { textColor: MUTED, ...base }),
    },
    {
      header: t('sales.col.reviewedAt'),
      width: 18,
      cell: (row, base) => moment(row.review?.reviewed_at, { textColor: MUTED, ...base }),
    },
  ]
}

/* ── Uslublar ─────────────────────────────────────────────── */

const HEADER: CellObject = {
  fontWeight: 'bold',
  textColor: '#FFFFFF',
  backgroundColor: NAVY,
  align: 'center',
  alignVertical: 'center',
  wrap: true,
  height: 40,
}

/* ── Varaqlar ─────────────────────────────────────────────── */

/**
 * Savdolar varag'i: sarlavha bloki → jadval.
 *
 * Sarlavha blokida davr, filtr va yuklab olingan payt turadi.
 * Fayl pochta orqali yuborilganda kontekst yo'qoladi va bu ayniqsa
 * shu hisobotda xavfli: «45 ta shubhali savdo» degan son qaysi davr
 * va qaysi filtr bo'yicha ekani yozilmasa, uni butun yilga tegishli
 * deb o'qish mumkin.
 */
function salesSheet(
  rows: ComplianceRow[],
  t: TFunction,
  meta: { period: string; scope: string; generated: string; windowDays?: number },
): { data: SheetData; widths: number[] } {
  const cols = columns(t, meta.windowDays)
  const span = cols.length

  const title = (value: string, style: CellObject): Row => [
    { value, type: String, ...style, columnSpan: span },
    ...Array.from({ length: span - 1 }, () => null),
  ]

  const data: SheetData = [
    title(t('sales.title'), { fontWeight: 'bold', fontSize: 16, textColor: NAVY }),
    /* Ogohlantirish faylning O'ZIDA: bu ro'yxat AYBLAMAYDI. Ekranda
       u sarlavha ostida turadi, fayl esa ekrandan ajralib ketadi va
       qo'ldan qo'lga o'tadi — izohsiz u ayblov ro'yxatiga aylanardi. */
    title(t('sales.subtitle'), { fontSize: 10, textColor: WARN }),
    title(meta.period, { fontSize: 11, textColor: MUTED }),
    title(meta.scope, { fontSize: 10, textColor: MUTED }),
    title(meta.generated, { fontSize: 10, textColor: MUTED }),
    [],
    cols.map((column) => ({ value: column.header, type: String, ...HEADER })),
  ]

  rows.forEach((row, index) => {
    const base: CellObject = index % 2 ? { backgroundColor: BAND } : {}
    data.push(cols.map((column) => column.cell(row, base)))
  })

  return { data, widths: cols.map((column) => column.width) }
}

/**
 * Yig'ma varaq: uch toifa va xodimlar kesimi.
 *
 * Uchala toifa ham yoziladi — shu jumladan `not_checkable`. Uni
 * tashlab ketish faylni ekranga zid qilardi va «tekshirib bo'lmadi»
 * degan son ko'zdan yo'qolardi.
 */
function summarySheet(
  summary: ComplianceSummary,
  t: TFunction,
): { data: SheetData; widths: number[] } {
  const data: SheetData = [
    [
      { value: t('sales.summaryTitle'), type: String, fontWeight: 'bold', fontSize: 14, textColor: NAVY },
      null,
    ],
    [],
    ...(['ok', 'suspicious', 'not_checkable'] as SaleVerdict[]).map((verdict) => [
      { value: t(`sales.verdict.${verdict}`), type: String } as CellObject,
      {
        value: summary[verdict],
        type: Number,
        format: NUM,
        fontWeight: 'bold',
        textColor: VERDICT_COLOR[verdict],
      } as CellObject,
    ]),
    [
      { value: t('sales.total'), type: String, fontWeight: 'bold' },
      { value: summary.total, type: Number, format: NUM, fontWeight: 'bold' },
    ],
  ]

  /* Xodimlar kesimi — «kimda oqlanmagan savdo ko'p» degan savolga
     javob. Shu bilan birga `not_checkable` ustuni ham bor: bir
     xodimda u yuqori bo'lsa, muammo xodimda emas, o'sha filialning
     SAP dagi ma'lumot sifatida. */
  if (summary.agents?.length) {
    data.push([], [])
    data.push([
      { value: t('sales.col.agent'), type: String, ...HEADER },
      { value: t('sales.col.sales'), type: String, ...HEADER },
      { value: t('sales.verdict.ok'), type: String, ...HEADER },
      { value: t('sales.verdict.suspicious'), type: String, ...HEADER },
      { value: t('sales.verdict.not_checkable'), type: String, ...HEADER },
      { value: t('sales.review.new'), type: String, ...HEADER },
      { value: t('sales.review.justified'), type: String, ...HEADER },
      { value: t('sales.review.confirmed'), type: String, ...HEADER },
    ])
    summary.agents.forEach((agent, index) => {
      const base: CellObject = index % 2 ? { backgroundColor: BAND } : {}
      data.push([
        text(agent.agent_name ?? t('sales.noAgent'), base),
        num(agent.sales, base),
        num(agent.ok, { textColor: GOOD, ...base }),
        num(agent.suspicious, {
          textColor: agent.suspicious ? WARN : undefined,
          ...base,
        }),
        num(agent.not_checkable, { textColor: MUTED, ...base }),
        num(agent.new, base),
        num(agent.justified, { textColor: GOOD, ...base }),
        num(agent.confirmed, { textColor: agent.confirmed ? BAD : undefined, ...base }),
      ])
    })
  }

  return { data, widths: [30, 14, 12, 16, 18, 16, 14, 22] }
}

/* ── Kirish nuqtasi ───────────────────────────────────────── */

export interface SalesExportOptions {
  rows: ComplianceRow[]
  summary?: ComplianceSummary
  /** Yorliqlar foydalanuvchining tilida chiqishi uchun */
  t: TFunction
  /** Ekrandagi davr — `YYYY-MM-DD` */
  since: string
  until: string
  /** Ekrandagi filtrning qisqacha tavsifi */
  scope?: string
  windowDays?: number
}

/** Fayl nomi: `savdo-nazorati-2026-07-22_2026-08-20.xlsx` */
function fileName(t: TFunction, since: string, until: string): string {
  return `${t('sales.export.file')}-${since}_${until}.xlsx`
}

export async function exportCompliance({
  rows,
  summary,
  t,
  since,
  until,
  scope,
  windowDays,
}: SalesExportOptions): Promise<void> {
  const writeXlsxFile = (await import('write-excel-file/browser')).default

  const period = t('sales.export.period', {
    from: formatFullDate(`${since}T00:00:00`),
    to: formatFullDate(`${until}T00:00:00`),
  })

  const sales = salesSheet(rows, t, {
    period,
    scope: [t('sales.export.rows', { count: rows.length }), scope]
      .filter(Boolean)
      .join(' · '),
    generated: t('sales.export.generated', { value: formatFullDateTime(new Date()) }),
    windowDays,
  })

  const sheets = [
    {
      data: sales.data,
      sheet: t('sales.export.sheetSales'),
      columns: sales.widths.map((width) => ({ width })),
      /* Sarlavha bloki (5 qator) + bo'sh qator + jadval sarlavhasi = 7.
         Birinchi ustun ham qotiriladi: 26 ustunli jadvalda o'ngga
         siljiganda qaysi savdo ekani bilinmay qolardi. */
      stickyRowsCount: 7,
      stickyColumnsCount: 1,
    },
  ]

  if (summary) {
    const totals = summarySheet(summary, t)
    sheets.push({
      data: totals.data,
      sheet: t('sales.export.sheetSummary'),
      columns: totals.widths.map((width) => ({ width })),
      stickyRowsCount: 1,
      stickyColumnsCount: 1,
    })
  }

  await writeXlsxFile(sheets).toFile(fileName(t, since, until))
}

/** Brauzersiz tekshirish uchun — ilovaning o'zi buni ishlatmaydi */
export const __sheets = { salesSheet, summarySheet }
