/**
 * Sana formatlash va davr (range) hisoblash.
 *
 * ⚠️ `toLocaleDateString('uz-UZ', {month:'long'})` ISHLATILMAYDI:
 * Chrome/V8 da uz-UZ lokali oylarni "M04" ko'rinishida qaytaradi.
 * Shuning uchun oy nomlari qo'lda yozilgan.
 *
 * Jadvallardagi sana HAMMA rol uchun bir xil: 12/08/2026.
 * Ixcham ko'rinish (`12 avg`) faqat grafik o'qlarida qoldi.
 */

import { useCallback, useMemo } from 'react'

type DateLike = string | number | Date

export const MONTHS_UZ = [
  'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun',
  'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr',
]

export const MONTHS_UZ_SHORT = [
  'yan', 'fev', 'mar', 'apr', 'may', 'iyn',
  'iyl', 'avg', 'sen', 'okt', 'noy', 'dek',
]

function toDate(value: DateLike): Date {
  return value instanceof Date ? value : new Date(value)
}

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/** 12/08/2026 */
export function formatFullDate(value: DateLike): string {
  const d = toDate(value)
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`
}

/** 14:30 */
export function formatTime(value: DateLike): string {
  const d = toDate(value)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 12/08/2026 14:30 */
export function formatFullDateTime(value: DateLike): string {
  return `${formatFullDate(value)} ${formatTime(value)}`
}

/** 12 avg */
export function formatShortDate(value: DateLike): string {
  const d = toDate(value)
  return `${pad(d.getDate())} ${MONTHS_UZ_SHORT[d.getMonth()]}`
}

/** avgust 2026 */
export function formatMonthYear(value: DateLike): string {
  const d = toDate(value)
  return `${MONTHS_UZ[d.getMonth()]} ${d.getFullYear()}`
}

/** <input type="date"> uchun: 2026-08-12 */
export function toInputValue(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/* ══════════════════════════════════════════════════════════════
   Davr (range) hisoblash
   ══════════════════════════════════════════════════════════════ */

export type PresetKey =
  | 'last7'
  | 'last30'
  | 'last45'
  | 'last90'
  | 'thisMonth'
  | 'lastMonth'
  | 'thisQuarter'
  | 'thisYear'

export interface DateRange {
  from: Date
  to: Date
  /** Tayyor davr tanlanganmi yoki qo'lda kiritilganmi */
  preset: PresetKey | null
  /** Butun yil tanlangan bo'lsa */
  year?: number
  /** Aniq oy tanlangan bo'lsa (0–11). `year` bilan birga keladi */
  month?: number
}

const startOfDay = (d: Date) =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0)

const endOfDay = (d: Date) =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999)

/** `"2026-07-03"` → shu kunning MAHALLIY yarim tuni.
 *
 * `new Date("2026-07-03")` UTC yarim tunini beradi — Toshkentda (UTC+5)
 * bu 3-iyul 05:00. Shu qiymatni mahalliy yarim tunda boshlanadigan davr
 * bilan solishtirish soatlik xatoga olib keladi: aynan chegara kunidan
 * boshlanadigan davr «chegaradan oldin» bo'lib chiqadi. */
export function localDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day, 0, 0, 0, 0)
}

export function resolvePreset(preset: PresetKey): DateRange {
  const now = new Date()

  switch (preset) {
    case 'last7':
      return { from: startOfDay(addDays(now, -6)), to: endOfDay(now), preset }
    case 'last30':
      return { from: startOfDay(addDays(now, -29)), to: endOfDay(now), preset }
    case 'last45':
      return { from: startOfDay(addDays(now, -44)), to: endOfDay(now), preset }
    case 'last90':
      return { from: startOfDay(addDays(now, -89)), to: endOfDay(now), preset }
    case 'thisMonth':
      return {
        from: new Date(now.getFullYear(), now.getMonth(), 1),
        to: endOfDay(now),
        preset,
      }
    case 'lastMonth': {
      const from = new Date(now.getFullYear(), now.getMonth() - 1, 1)
      const to = new Date(now.getFullYear(), now.getMonth(), 0, 23, 59, 59, 999)
      return { from, to, preset }
    }
    case 'thisQuarter': {
      const q = Math.floor(now.getMonth() / 3)
      return {
        from: new Date(now.getFullYear(), q * 3, 1),
        to: endOfDay(now),
        preset,
      }
    }
    case 'thisYear':
      return {
        from: new Date(now.getFullYear(), 0, 1),
        to: endOfDay(now),
        preset,
      }
  }
}

export function resolveYear(year: number): DateRange {
  const now = new Date()
  const isCurrent = year === now.getFullYear()
  return {
    from: new Date(year, 0, 1),
    to: isCurrent ? endOfDay(now) : new Date(year, 11, 31, 23, 59, 59, 999),
    preset: null,
    year,
  }
}

/** Aniq oy: «aprel 2024». Joriy oy bo'lsa bugungi kunda tugaydi */
export function resolveMonth(year: number, month: number): DateRange {
  const now = new Date()
  const isCurrent = year === now.getFullYear() && month === now.getMonth()
  return {
    from: new Date(year, month, 1),
    // Keyingi oyning 0-kuni = shu oyning oxirgi kuni
    to: isCurrent ? endOfDay(now) : new Date(year, month + 1, 0, 23, 59, 59, 999),
    preset: null,
    year,
    month,
  }
}

/** Oy kelajakdami — tanlash uchun yopiq bo'lishi kerak */
export function isFutureMonth(year: number, month: number): boolean {
  const now = new Date()
  return year > now.getFullYear() || (year === now.getFullYear() && month > now.getMonth())
}

export function customRange(from: Date, to: Date): DateRange {
  return { from: startOfDay(from), to: endOfDay(to), preset: null }
}

function addDays(d: Date, days: number): Date {
  const next = new Date(d)
  next.setDate(next.getDate() + days)
  return next
}

/** Davrdagi kunlar soni */
export function rangeDays(range: DateRange): number {
  return Math.max(
    1,
    Math.round((range.to.getTime() - range.from.getTime()) / 86_400_000),
  )
}

/** API uchun ISO qiymatlar */
export function rangeToQuery(range: DateRange) {
  return {
    date_from: range.from.toISOString(),
    date_to: range.to.toISOString(),
  }
}

/* ══════════════════════════════════════════════════════════════
   Ilova bo'ylab yagona sana ko'rinishi
   ══════════════════════════════════════════════════════════════ */

/**
 * Jadval va kartochkalardagi sana — HAMMA uchun bir xil: `12/08/2026`.
 *
 * Ilgari format rolga bog'liq edi: admin va menejer to'liq sanani,
 * savdo xodimi va kuzatuvchi esa ixchamini (`12 avg`) ko'rardi.
 * Amalda bu ish bermadi — yildan xoli sana ikki xil o'qiladi
 * («bu yilgimi yoki o'tganmi?»), va bir xil jadvalni ikki kishi
 * ikki xil ko'rgani ularning gaplashishini qiyinlashtirardi.
 *
 * Ixcham ko'rinish (`formatShortDate`) o'chirilmadi — u grafik
 * o'qlarida kerak, u yerda joy tor va yil takrorlanadi.
 *
 * Hook bo'lib qolgani ataylab: chaqiruv joylari o'zgarmadi va
 * kelajakda til/vaqt mintaqasi sozlamasi qo'shilsa, o'zgarish
 * yana shu yagona joyda bo'ladi.
 */
export function useDateFormat() {
  const date = useCallback((value: DateLike) => formatFullDate(value), [])
  const dateTime = useCallback((value: DateLike) => formatFullDateTime(value), [])

  return useMemo(() => ({ date, dateTime, time: formatTime }), [date, dateTime])
}
