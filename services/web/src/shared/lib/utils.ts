import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Soniyani "8:42" ko'rinishiga o'giradi — BITTA qo'ng'iroq uchun. */
export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Uzoq davomiylik — "5 s 42 daq" ko'rinishida.
 *
 *  ⚠️ JAMLANMA uchun `formatDuration` YARAMAYDI. U daqiqa:soniya
 *  shaklini beradi va oylik yig'indida «20468:17» chiqadi — «Suhbat»
 *  sarlavhasi ostida bu son soat emas, MIQDOR bo'lib o'qiladi.
 *  O'lchandi: 30 kunlik jami aynan shunday ko'rinardi. */
export function formatLongDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} son`
  const soat = Math.floor(seconds / 3600)
  const daq = Math.round((seconds % 3600) / 60)
  if (!soat) return `${daq} daq`
  // Daqiqa 60 ga yaxlitlansa soatga qo'shiladi — «5 s 60 daq» bo'lmasin
  return daq === 60 ? `${soat + 1} s` : daq ? `${soat} s ${daq} daq` : `${soat} s`
}

/** Daqiqani odam o'qiydigan shaklga: 42 → "42 daq", 158.7 → "2 s 39 daq".
 *
 *  ⚠️ Katta qiymat daqiqada qolsa o'qilmaydi: «158,7 daq» ni odam
 *  soatga o'zi aylantirishi kerak bo'ladi. Haqiqiy ma'lumotda median
 *  1 daqiqadan 159 gacha o'zgaradi. */
export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} daq`
  return formatLongDuration(minutes * 60)
}

/** 12345 → "12 345" */
export function formatNumber(value: number): string {
  return new Intl.NumberFormat('uz-UZ').format(value)
}

/** Ballni semantik rangga bog'laydi */
export function scoreTone(score: number | null | undefined) {
  if (score == null) return 'muted'
  if (score >= 85) return 'good'
  if (score >= 70) return 'accent'
  if (score >= 55) return 'warn'
  return 'bad'
}

export const TONE_CLASS: Record<string, string> = {
  good: 'text-good',
  accent: 'text-accent',
  warn: 'text-warn',
  bad: 'text-bad',
  muted: 'text-muted',
}

export const TONE_BG: Record<string, string> = {
  good: 'bg-good/10 text-good',
  accent: 'bg-accent/10 text-accent',
  warn: 'bg-warn/10 text-warn',
  bad: 'bg-bad/10 text-bad',
  muted: 'bg-muted/10 text-muted',
}
