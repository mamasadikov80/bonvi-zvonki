/**
 * Kichik vizual elementlar — jadval va kartalar ichida ishlatiladi.
 * Ular kutubxona emas, sof SVG/CSS — yengil va tez.
 */

import { useEffect, useId, useRef, useState } from 'react'
import { Area, AreaChart, ResponsiveContainer } from 'recharts'

import { BASE_URL } from '@/shared/api/client'
import { cn } from '@/shared/lib/utils'

/* ── Sparkline (KPI kartalar uchun) ──────────────────────── */

export function Sparkline({
  data,
  tone = 'accent',
  height = 32,
}: {
  data: (number | null)[]
  tone?: 'accent' | 'good' | 'warn' | 'bad'
  height?: number
}) {
  const points = data.filter((v): v is number => v != null)
  if (points.length < 2) return <div style={{ height }} />

  const rows = points.map((value, i) => ({ i, value }))
  const id = `spark-${tone}-${points.length}-${Math.round(points[0])}`

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={rows} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={`hsl(var(--${tone}))`} stopOpacity={0.25} />
            <stop offset="100%" stopColor={`hsl(var(--${tone}))`} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={`hsl(var(--${tone}))`}
          strokeWidth={1.75}
          fill={`url(#${id})`}
          isAnimationActive={false}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/* ── Ball halqasi (top-3 kartalari uchun) ────────────────── */

/** Foydalanuvchi animatsiyani o'chirib qo'yganmi */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return reduced
}

/** 0 dan `target` gacha silliq sanaydi. iOS uslubidagi sekinlashuv */
function useCountUp(target: number | null, duration = 900): number {
  const reduced = usePrefersReducedMotion()
  const [shown, setShown] = useState(reduced || target == null ? (target ?? 0) : 0)
  const frame = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (target == null) return
    if (reduced) {
      setShown(target)
      return
    }

    const from = 0
    const start = performance.now()
    const step = (now: number) => {
      const progress = Math.min(1, (now - start) / duration)
      // easeOutCubic — oxiriga borib yumshoq to'xtaydi
      const eased = 1 - Math.pow(1 - progress, 3)
      setShown(from + (target - from) * eased)
      if (progress < 1) frame.current = requestAnimationFrame(step)
    }
    frame.current = requestAnimationFrame(step)

    return () => {
      if (frame.current) cancelAnimationFrame(frame.current)
    }
  }, [target, duration, reduced])

  return shown
}

export function ScoreRing({
  value,
  max = 100,
  size = 52,
  tone = 'accent',
}: {
  value: number | null
  max?: number
  size?: number
  tone?: 'accent' | 'good' | 'warn' | 'bad'
}) {
  const gradientId = useId()
  const reduced = usePrefersReducedMotion()

  // Chiziq qalinligi o'lchamga bog'liq — katta aylana ingichka ko'rinmasin
  const stroke = Math.max(4, Math.round(size * 0.085))
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const target = value == null ? 0 : Math.min(1, Math.max(0, value / max))

  /* Yoy 0 dan boshlanib chiziladi. Boshidanoq oxirgi qiymat qo'yilsa
     CSS o'tishi ishlamaydi — shuning uchun birinchi kadrdan keyin
     yangilanadi. */
  const [progress, setProgress] = useState(reduced ? target : 0)
  useEffect(() => {
    if (reduced) {
      setProgress(target)
      return
    }
    const id = requestAnimationFrame(() => setProgress(target))
    return () => cancelAnimationFrame(id)
  }, [target, reduced])

  const counted = useCountUp(value)

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90 overflow-visible">
        <defs>
          {/* Bir xil rangdan ikki to'yinganlik — yoy tekis emas, tiriklay ko'rinadi */}
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={`hsl(var(--${tone}) / 0.72)`} />
            <stop offset="100%" stopColor={`hsl(var(--${tone}))`} />
          </linearGradient>
        </defs>

        {/* Iz — chegara rangi emas, o'sha tonning xira ko'rinishi */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={`hsl(var(--${tone}) / 0.13)`}
          strokeWidth={stroke}
        />

        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - progress)}
          className={cn(
            'transition-[stroke-dashoffset] duration-[900ms]',
            'motion-reduce:transition-none',
          )}
          style={{
            transitionTimingFunction: 'cubic-bezier(0.22, 1, 0.36, 1)',
            // Yumshoq nur — kartadagi soya bilan bir uslubda
            filter: `drop-shadow(0 1px 3px hsl(var(--${tone}) / 0.35))`,
          }}
        />
      </svg>

      <div className="absolute inset-0 grid place-items-center">
        <span
          className="tnum font-semibold leading-none"
          style={{ fontSize: Math.max(11, Math.round(size * 0.3)) }}
        >
          {value == null ? '—' : Math.round(counted)}
        </span>
      </div>
    </div>
  )
}

/* ── Avatar (bosh harflar) ───────────────────────────────── */

/** Nisbiy /media/... yo'lini backend manzili bilan to'ldiradi */
export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined
  return path.startsWith('http') ? path : `${BASE_URL}${path}`
}

export function Avatar({
  name,
  color,
  size = 'md',
  src,
}: {
  name: string
  color?: string
  size?: 'sm' | 'md' | 'lg'
  /** Profil rasmi. Bo'lmasa bosh harflar ko'rsatiladi */
  src?: string | null
}) {
  const initials = name
    .split(' ')
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()

  const sizes = {
    sm: 'size-7 text-2xs',
    md: 'size-9 text-xs',
    lg: 'size-11 text-sm',
  }

  const resolved = mediaUrl(src)

  if (resolved) {
    return (
      <img
        src={resolved}
        alt=""
        aria-hidden
        loading="lazy"
        className={cn('shrink-0 rounded-full object-cover', sizes[size])}
      />
    )
  }

  return (
    <div
      className={cn(
        'grid shrink-0 place-items-center rounded-full font-semibold text-white',
        sizes[size],
      )}
      style={{ background: color ?? 'hsl(var(--accent))' }}
      aria-hidden
    >
      {initials}
    </div>
  )
}

/* ── Inline progress bar (jadval ichida) ─────────────────── */

export function MiniBar({
  value,
  max = 100,
  tone = 'accent',
  width = 56,
}: {
  value: number | null
  max?: number
  tone?: 'accent' | 'good' | 'warn' | 'bad'
  width?: number
}) {
  const pct = value == null ? 0 : Math.min(100, (value / max) * 100)
  return (
    <span
      className={cn(
        'inline-block overflow-hidden rounded-full bg-border align-middle',
        width === 0 && 'block w-full',
      )}
      style={{ width: width === 0 ? undefined : width, height: 5 }}
    >
      <span
        className="block h-full rounded-full transition-[width] duration-500"
        style={{ width: `${pct}%`, background: `hsl(var(--${tone}))` }}
      />
    </span>
  )
}

/* ── Talk ratio (ikki tomonlama bar) ─────────────────────── */

export function TalkRatio({ agent, width = 56 }: { agent: number; width?: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 align-middle">
      <span
        className="inline-block overflow-hidden rounded-full bg-border"
        style={{ width, height: 5 }}
      >
        <span
          className="block h-full rounded-full bg-accent"
          style={{ width: `${agent}%` }}
        />
      </span>
      <span className="tnum text-2xs text-muted">
        {agent}/{100 - agent}
      </span>
    </span>
  )
}

/* ── Trend ko'rsatkichi ──────────────────────────────────── */

export function TrendDelta({ value }: { value: number | null | undefined }) {
  if (value == null || value === 0) {
    return <span className="tnum text-2xs text-muted">→ 0</span>
  }
  const up = value > 0
  return (
    <span
      className={cn('tnum inline-flex items-center gap-0.5 text-2xs font-medium', up ? 'text-good' : 'text-bad')}
    >
      {up ? '↑' : '↓'} {Math.abs(value)}
    </span>
  )
}
