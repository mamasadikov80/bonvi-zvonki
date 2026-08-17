import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Soniyani "8:42" ko'rinishiga o'giradi */
export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
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
