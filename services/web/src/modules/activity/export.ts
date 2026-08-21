/**
 * Faollik hisobotini Excelga chiqarish.
 *
 * NEGA BRAUZERDA, backendda emas. Faylga AYNAN ekrandagi ma'lumot
 * tushishi shart — o'sha filtr, o'sha sonlar. Ular allaqachon shu
 * yerda: sahifa `useActivity` javobini chizadi. Backendda ikkinchi
 * marta hisoblansa ikkita haqiqat paydo bo'lardi va ular vaqt o'tib
 * ajralib ketardi (bir joyga filtr qo'shiladi, boshqasida yaxlitlash
 * o'zgaradi) — rahbar esa ekrandagi va fayldagi raqam nega farq
 * qilishini so'rardi. Yorliqlar ham foydalanuvchining TILIDA chiqadi;
 * backend faqat o'zbekcha yozardi.
 *
 * Kutubxona DINAMIK import qilinadi — u faqat tugma bosilganda kerak.
 * Statik import bo'lsa uni har bir foydalanuvchi, hech qachon eksport
 * qilmasa ham, sahifa bilan birga yuklab olardi.
 */

import type { TFunction } from 'i18next'
import type { CellObject, Row, SheetData } from 'write-excel-file/browser'

import type {
  ActivityDay,
  ActivityHour,
  ActivityReport,
  ActivityRow,
} from '@/modules/activity/api'
import { formatFullDate, formatFullDateTime, toInputValue } from '@/shared/lib/date'

/* ── Ranglar ──────────────────────────────────────────────────
   Ilovaning yorug' mavzusidagi ranglari (`index.css` dagi HSL
   tokenlar) — Excelda mavzu yo'q, shuning uchun aynan o'sha
   qiymatlar. Fayl ekranning davomi bo'lib ko'rinishi kerak: qizil
   son ekranda ham, faylda ham bir xil qizil bo'lsin. */
const NAVY = '#215A8C' // --accent
const GOOD = '#1E8052' // --good
const WARN = '#B35C05' // --warn
const BAD = '#CC1F36' // --bad
const MUTED = '#6B7280'
const BAND = '#F4F7FA' // qatorlar orasidagi yengil zebra

/** Sonlar formati — mingliklar ajratilgan holda. */
const NUM = '#,##0'
/** Foiz: bazada 0–100, Excelda esa ulush kutiladi (0–1). */
const PCT = '0.0%'
/** Daqiqa — bitta kasr xonasi bilan (ekranda ham shunday). */
const MIN = '0.0'
/**
 * Suhbat vaqti — HAQIQIY vaqt sifatida (`6:59:00`), matn emas.
 *
 * ⚠️ `[h]` kvadrat qavsda: oddiy `h` 24 soatdan keyin nolga qaytadi
 * va «31 soat 12 daqiqa» ekranda «7:12» bo'lib ko'rinardi. Jami
 * qatorida bu deyarli har doim sodir bo'lardi.
 */
const DUR = '[h]:mm:ss'

/** Excel kunni 1 deb hisoblaydi — soniyani shu o'lchovga keltiramiz. */
const DAY_SECONDS = 86_400

/* ── Kataklar ─────────────────────────────────────────────── */

function num(value: number | null | undefined, style: CellObject = {}): CellObject {
  if (value == null) return { ...style }
  return { value, type: Number, format: NUM, ...style }
}

/** Foiz katagi. `null` — bo'sh (ekranda ham «—» turadi). */
function pct(value: number | null, style: CellObject = {}): CellObject {
  if (value == null) return { ...style }
  return { value: value / 100, type: Number, format: PCT, ...style }
}

function minutes(value: number | null, style: CellObject = {}): CellObject {
  if (value == null) return { ...style }
  return { value, type: Number, format: MIN, ...style }
}

function duration(seconds: number, style: CellObject = {}): CellObject {
  return { value: seconds / DAY_SECONDS, type: Number, format: DUR, ...style }
}

/** Qaytish darajasining rangi — ekrandagi `callbackTone` bilan BIR XIL.
 *
 *  Chegaralar takrorlanmasin desa ham, `callbackTone` Tailwind sinfini
 *  qaytaradi (`text-good`), Excelga esa HEX kerak. Umumiy narsa —
 *  raqamlar; ular shu yerda ham, u yerda ham 90 va 60. */
function rateColor(rate: number | null): string | undefined {
  if (rate == null) return undefined
  if (rate >= 90) return GOOD
  if (rate >= 60) return WARN
  return BAD
}

/** Qaytish VAQTINING rangi — ekrandagi `medianTone` bilan bir xil. */
function medianColor(value: number | null): string | undefined {
  if (value == null) return undefined
  if (value <= 10) return GOOD
  if (value <= 30) return WARN
  return BAD
}

/* ── Ustunlar ─────────────────────────────────────────────── */

interface Column {
  header: string
  width: number
  /** Katak qiymati va uslubi. `base` — qator foni (zebra). */
  cell: (row: ActivityRow, base: CellObject) => CellObject
}

/**
 * Jadval ustunlari — ekrandagi tartibda.
 *
 * Ekranda yo'q ikkita ustun ATAYLAB qo'shilgan: «javob berilgan»
 * sonlari. Ular yuqoridagi kartochkalarda ko'rinadi va bitta javobda
 * keladi, ya'ni yangi hisob emas. Excelda joy tor emas, hisobotni
 * qayta ochib qidirmaslik esa foydali.
 */
function columns(t: TFunction): Column[] {
  return [
    {
      header: t('table.agent'),
      width: 28,
      cell: (row, base) => ({ value: row.agent_name, type: String, ...base }),
    },
    {
      header: t('activity.export.region'),
      width: 16,
      cell: (row, base) => ({
        value: row.region ?? '',
        type: String,
        textColor: MUTED,
        ...base,
      }),
    },
    {
      header: t('activity.colOut'),
      width: 12,
      cell: (row, base) => num(row.outbound_total, base),
    },
    {
      header: t('activity.export.outAnswered'),
      width: 14,
      cell: (row, base) => num(row.outbound_answered, { textColor: MUTED, ...base }),
    },
    {
      header: t('activity.colOutNoAnswer'),
      width: 16,
      cell: (row, base) => num(row.outbound_no_answer, base),
    },
    {
      header: t('activity.colIn'),
      width: 12,
      cell: (row, base) => num(row.inbound_total, base),
    },
    {
      header: t('activity.export.inAnswered'),
      width: 14,
      cell: (row, base) => num(row.inbound_answered, { textColor: MUTED, ...base }),
    },
    {
      header: t('activity.colMissed'),
      width: 16,
      /* Qizil — faqat noldan katta bo'lganda. Nolni qizil qilish
         «bu yerda muammo bor» degan yolg'on signal bo'lardi. */
      cell: (row, base) =>
        num(row.missed, { textColor: row.missed ? BAD : undefined, ...base }),
    },
    {
      header: t('activity.export.missedRate'),
      width: 12,
      cell: (row, base) => pct(row.missed_rate, base),
    },
    {
      header: t('activity.colClients'),
      width: 11,
      cell: (row, base) => num(row.missed_clients, base),
    },
    {
      header: t('activity.colUnreached'),
      width: 14,
      cell: (row, base) =>
        num(row.clients_unreached, {
          textColor: row.clients_unreached ? BAD : undefined,
          fontWeight: row.clients_unreached ? 'bold' : undefined,
          ...base,
        }),
    },
    {
      header: t('activity.colRate'),
      width: 12,
      cell: (row, base) =>
        pct(row.callback_rate, {
          textColor: rateColor(row.callback_rate),
          fontWeight: 'bold',
          ...base,
        }),
    },
    {
      header: t('activity.export.median'),
      width: 15,
      cell: (row, base) =>
        minutes(row.callback_median_minutes, {
          textColor: medianColor(row.callback_median_minutes),
          ...base,
        }),
    },
    {
      header: t('activity.colTalk'),
      width: 13,
      /* Matn emas, HAQIQIY vaqt: Excelda saralash va qo'shish
         ishlaydi. «6 soat 59 daq» degan satr bilan ikkalasi ham
         imkonsiz bo'lardi. */
      cell: (row, base) => duration(row.talk_seconds, base),
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
  height: 38,
}

const TOTAL: CellObject = {
  fontWeight: 'bold',
  backgroundColor: '#EDF1F5',
  topBorderStyle: 'medium',
  topBorderColor: NAVY,
}

/* ── Varaqlar ─────────────────────────────────────────────── */

/**
 * Xodimlar varag'i: sarlavha bloki → jadval → «Jami» qatori.
 *
 * Sarlavha bloki UCH qator — davr, filtr va yuklab olingan payt.
 * Fayl pochta orqali yuborilganda kontekst yo'qoladi: qaysi davr,
 * qaysi filtr bilan olingani faylning O'ZIDA yozilmasa, uni ochgan
 * odam raqamlarni noto'g'ri o'qishi mumkin.
 */
function agentsSheet(
  report: ActivityReport,
  t: TFunction,
  meta: { period: string; scope: string; generated: string },
): { data: SheetData; widths: number[] } {
  const cols = columns(t)
  const span = cols.length

  const title = (value: string, style: CellObject): Row => [
    { value, type: String, ...style, columnSpan: span },
    ...Array.from({ length: span - 1 }, () => null),
  ]

  const data: SheetData = [
    title(t('activity.title'), { fontWeight: 'bold', fontSize: 16, textColor: NAVY }),
    title(meta.period, { fontSize: 11, textColor: MUTED }),
    title(meta.scope, { fontSize: 10, textColor: MUTED }),
    title(meta.generated, { fontSize: 10, textColor: MUTED }),
    [],
    cols.map((column) => ({ value: column.header, type: String, ...HEADER })),
  ]

  report.agents.forEach((row, index) => {
    /* Zebra — o'qishni osonlashtiradi: 14 ustunli qatorda ko'z
       yo'ldan adashadi. Chiziq ataylab juda och. */
    const base: CellObject = index % 2 ? { backgroundColor: BAND } : {}
    data.push(cols.map((column) => column.cell(row, base)))
  })

  /* «Jami» — jadvalning ICHIDA, oxirgi qator. Alohida varaqda
     bo'lsa taqqoslash uchun varaq almashtirish kerak bo'lardi. */
  if (report.agents.length > 1) {
    const total = report.total
    data.push([
      { value: t('activity.totalRow'), type: String, ...TOTAL },
      { ...TOTAL },
      num(total.outbound_total, TOTAL),
      num(total.outbound_answered, TOTAL),
      num(total.outbound_no_answer, TOTAL),
      num(total.inbound_total, TOTAL),
      num(total.inbound_answered, TOTAL),
      num(total.missed, { ...TOTAL, textColor: total.missed ? BAD : undefined }),
      pct(total.missed_rate, TOTAL),
      num(total.missed_clients, TOTAL),
      num(total.clients_unreached, {
        ...TOTAL,
        textColor: total.clients_unreached ? BAD : undefined,
      }),
      pct(total.callback_rate, {
        ...TOTAL,
        textColor: rateColor(total.callback_rate),
      }),
      /* ⚠️ Xodimlar medianasining o'rtachasi EMAS — hisobotning o'z
         medianasi. Medianalarni o'rtachalab bo'lmaydi va ekranda ham
         aynan shu qiymat turadi. */
      minutes(report.callback_median_minutes, {
        ...TOTAL,
        textColor: medianColor(report.callback_median_minutes),
      }),
      duration(total.talk_seconds, TOTAL),
    ])
  }

  return { data, widths: cols.map((column) => column.width) }
}

/**
 * Dinamika varag'i — grafikdagi ustunlarning o'zi.
 *
 * Kesim ekrandagiga MOS keladi: bir kunlik davrda soatlar, undan
 * uzunida kunlar. Grafik nimani ko'rsatgan bo'lsa, faylda ham o'sha
 * bo'lishi kerak.
 */
function seriesSheet(
  report: ActivityReport,
  t: TFunction,
  byHour: boolean,
): { data: SheetData; widths: number[] } {
  const headers = [
    byHour ? t('activity.export.hour') : t('activity.export.day'),
    t('activity.colIn'),
    t('activity.export.inAnswered'),
    t('activity.colMissed'),
    t('activity.colOut'),
    t('activity.colOutNoAnswer'),
    ...(byHour ? [t('activity.export.missedRate')] : []),
  ]

  const data: SheetData = [headers.map((value) => ({ value, type: String, ...HEADER }))]

  /* ⚠️ ANIQ BIRLASHTIRILGAN TUR. `byHour ? a : b` ning turi
     `ActivityHour[] | ActivityDay[]` bo'lib chiqadi va TypeScript
     bunday birlashmada `forEach` ni chaqirishga ruxsat bermaydi. */
  const rows: (ActivityDay | ActivityHour)[] = byHour
    ? report.hours_series
    : report.days_series
  rows.forEach((row, index) => {
    const base: CellObject = index % 2 ? { backgroundColor: BAND } : {}
    const first: CellObject =
      'hour' in row
        ? {
            value: `${String(row.hour).padStart(2, '0')}:00`,
            type: String,
            align: 'center',
            ...base,
          }
        : {
            /* ⚠️ `new Date('2026-08-20')` — UTC yarim tuni, va bu yerda
               aynan SHU kerak: kutubxona sanani `getTime()` orqali
               Excel raqamiga aylantiradi. Mahalliy yarim tun berilsa
               (Toshkentda UTC+5) fayl sanani bir kun oldingisi qilib
               ko'rsatardi. */
            value: new Date(row.day),
            type: Date,
            format: 'dd.mm.yyyy',
            align: 'center',
            ...base,
          }

    data.push([
      first,
      num(row.inbound, base),
      num(row.inbound_answered, { textColor: MUTED, ...base }),
      num(row.missed, { textColor: row.missed ? BAD : undefined, ...base }),
      num(row.outbound, base),
      num(row.outbound_no_answer, base),
      ...('hour' in row ? [pct(row.missed_rate, base)] : []),
    ])
  })

  if (rows.length > 1) {
    const sum = (pick: (row: (typeof rows)[number]) => number) =>
      rows.reduce((acc, row) => acc + pick(row), 0)
    data.push([
      { value: t('activity.totalRow'), type: String, ...TOTAL },
      num(sum((row) => row.inbound), TOTAL),
      num(sum((row) => row.inbound_answered), TOTAL),
      num(sum((row) => row.missed), TOTAL),
      num(sum((row) => row.outbound), TOTAL),
      num(sum((row) => row.outbound_no_answer), TOTAL),
      ...(byHour ? [{ ...TOTAL }] : []),
    ])
  }

  return {
    data,
    widths: [14, ...Array.from({ length: headers.length - 1 }, () => 14)],
  }
}

/* ── Kirish nuqtasi ───────────────────────────────────────── */

export interface ActivityExportOptions {
  report: ActivityReport
  /** Yorliqlar foydalanuvchining tilida chiqishi uchun */
  t: TFunction
  /** Grafik kesimi — ekrandagi bilan bir xil bo'lishi kerak */
  byHour: boolean
  /** Tanlangan hududlar — sarlavha blokidagi izoh uchun */
  regions?: string[]
}

/** Fayl nomi: `faollik-2026-07-15_2026-08-20.xlsx`.
 *
 *  Sana nomda bo'lgani muhim: bunday fayllar papkada to'planadi va
 *  «faollik(3).xlsx» qaysi davrga tegishli ekanini hech kim bilmaydi. */
function fileName(report: ActivityReport, t: TFunction): string {
  const from = toInputValue(new Date(report.date_from))
  const to = toInputValue(new Date(report.date_to))
  return `${t('activity.export.file')}-${from}_${to}.xlsx`
}

export async function exportActivity({
  report,
  t,
  byHour,
  regions,
}: ActivityExportOptions): Promise<void> {
  const writeXlsxFile = (await import('write-excel-file/browser')).default

  const period = t('activity.export.period', {
    from: formatFullDate(report.date_from),
    to: formatFullDate(report.date_to),
    count: report.days,
  })
  const scope = [
    t('activity.export.agents', { count: report.agents.length }),
    regions?.length ? t('activity.export.regions', { value: regions.join(', ') }) : null,
  ]
    .filter(Boolean)
    .join(' · ')

  const agents = agentsSheet(report, t, {
    period,
    scope,
    generated: t('activity.export.generated', {
      value: formatFullDateTime(new Date()),
    }),
  })
  const series = seriesSheet(report, t, byHour)

  await writeXlsxFile([
    {
      data: agents.data,
      sheet: t('activity.export.sheetAgents'),
      columns: agents.widths.map((width) => ({ width })),
      /* Sarlavha bloki (4 qator) + bo'sh qator + jadval sarlavhasi =
         6. Aylantirilganda ustun nomlari joyida qoladi — 14 ustunli
         jadvalda busiz qaysi son qaysi ustunga tegishli ekani
         bilinmaydi. Birinchi ustun ham qotiriladi: o'ngga
         siljitilganda xodim ismi ko'rinib tursin. */
      stickyRowsCount: 6,
      stickyColumnsCount: 1,
    },
    {
      data: series.data,
      sheet: byHour
        ? t('activity.export.sheetHours')
        : t('activity.export.sheetDays'),
      columns: series.widths.map((width) => ({ width })),
      stickyRowsCount: 1,
    },
  ]).toFile(fileName(report, t))
}

/**
 * Brauzersiz tekshirish uchun: varaqlar tuzilishini tayyor holda
 * beradi, faylni esa chaqiruvchi o'zi yozadi (Node'da
 * `write-excel-file/node` bilan). Ilovaning o'zi buni ishlatmaydi.
 */
export const __sheets = { agentsSheet, seriesSheet }
