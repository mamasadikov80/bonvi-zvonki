/**
 * Mini App'ning o'z primitivlari.
 *
 * Dashboard'ning `Page` / `PageHeader` / `AppShell` qismlari ATAYLAB
 * ishlatilmaydi: bu sahifa admin panelining bir bo'lagi emas, Telegram
 * ichidagi mustaqil varaq. Ranglar `--sv-*` o'zgaruvchilaridan olinadi
 * (`telegram.ts`), shuning uchun loyihaning `bg`/`surface` sinflari
 * bu yerda uchramaydi — ular Telegram mavzusini bilmaydi.
 *
 * O'lchamlar 360px kenglikdagi arzon Android telefonga mo'ljallangan:
 * eng kichik bosish maydoni 48px, asosiy tugma 54px.
 */

import { Check, Star } from 'lucide-react'
import * as React from 'react'

import { cn } from '@/shared/lib/utils'

/* ── Karta ───────────────────────────────────────────────────
   Chegara emas, yumshoq soya ajratadi (loyiha uslubi). */

export function Section({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={cn(
        'rounded-2xl bg-[var(--sv-surface)] p-4',
        'shadow-[0_1px_2px_rgb(var(--sv-separator-rgb)/0.10),0_6px_20px_rgb(var(--sv-separator-rgb)/0.10)]',
        'ring-1 ring-[rgb(var(--sv-separator-rgb)/0.14)]',
        className,
      )}
      {...props}
    />
  )
}

export function SectionTitle({
  title,
  hint,
}: {
  title: string
  hint?: string
}) {
  return (
    <div className="mb-3">
      <h2 className="text-[1.0625rem] font-semibold leading-tight text-[var(--sv-text)]">
        {title}
      </h2>
      {hint ? (
        <p className="mt-1 text-[0.8125rem] leading-snug text-[var(--sv-hint)]">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

/* ── Baho: 1–5 yulduz ────────────────────────────────────────

   Majburiy maydon. Shuning uchun u sahifaning eng tepasida va eng
   katta elementi — odam nima qilishi kerakligini o'ylab o'tirmasin.

   To'ldirish YIG'INDI: 4 tanlansa 1–4 yulduz bo'yaladi. Bu odamlarga
   tanish naqsh; alohida-alohida bo'yalsa «4» emas «faqat 4-chi» degan
   ma'no chiqadi. */

export function StarRating({
  value,
  onChange,
  labels,
}: {
  value: number | null
  onChange: (value: number) => void
  /** 1..5 uchun matnli izoh: «Yomon» … «Juda yaxshi» */
  labels: Record<number, string>
}) {
  return (
    <div>
      <div className="flex justify-between gap-1.5" role="radiogroup">
        {[1, 2, 3, 4, 5].map((star) => {
          const filled = value !== null && star <= value
          return (
            <button
              key={star}
              type="button"
              role="radio"
              aria-checked={value === star}
              aria-label={labels[star] ?? String(star)}
              onClick={() => onChange(star)}
              className={cn(
                'flex min-h-[68px] flex-1 flex-col items-center justify-center gap-1',
                'rounded-xl transition-all duration-250 ease-ios active:scale-[0.94]',
                filled
                  ? 'bg-[rgb(var(--sv-accent-rgb)/0.12)]'
                  : 'bg-[rgb(var(--sv-separator-rgb)/0.10)]',
              )}
            >
              <Star
                className={cn(
                  'size-8 transition-colors duration-250 ease-ios',
                  filled
                    ? 'fill-[var(--sv-accent)] text-[var(--sv-accent)]'
                    : 'fill-transparent text-[rgb(var(--sv-hint-rgb)/0.55)]',
                )}
                strokeWidth={1.75}
              />
              <span
                className={cn(
                  'text-[0.75rem] font-semibold tabular-nums',
                  filled ? 'text-[var(--sv-accent)]' : 'text-[var(--sv-hint)]',
                )}
              >
                {star}
              </span>
            </button>
          )
        })}
      </div>

      {/* Balandlik qat'iy — tanlanganda sahifa sakramasin */}
      <p
        className={cn(
          'mt-2.5 min-h-[1.25rem] text-center text-[0.9375rem] font-medium',
          'transition-opacity duration-250 ease-ios',
          value === null ? 'opacity-0' : 'opacity-100',
        )}
        style={{ color: 'var(--sv-accent)' }}
        aria-live="polite"
      >
        {value === null ? ' ' : (labels[value] ?? '')}
      </p>
    </div>
  )
}

/* ── Nimadan norozi: bitta ko'p tanlovli ro'yxat ─────────────

   Yorliqlar SERVERDAN keladi. Bu yerda ro'yxat yo'q va bo'lmasligi
   kerak: serverda yangi mezon qo'shilsa u deploysiz paydo bo'lishi
   shart. Bitta ro'yxat — ikkita kategoriya emas: do'kondor uchun
   «xodim aybi» va «kompaniya aybi» degan bo'linish begona. */

export function OptionList({
  options,
  selected,
  onToggle,
}: {
  options: Array<{ key: string; label: string }>
  selected: string[]
  onToggle: (key: string) => void
}) {
  return (
    <div className="flex flex-col gap-2">
      {options.map((option) => {
        const active = selected.includes(option.key)
        return (
          <button
            key={option.key}
            type="button"
            role="checkbox"
            aria-checked={active}
            onClick={() => onToggle(option.key)}
            className={cn(
              'flex min-h-[52px] w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-left',
              'transition-all duration-250 ease-ios active:scale-[0.985]',
              active
                ? 'bg-[rgb(var(--sv-accent-rgb)/0.12)] ring-1 ring-[rgb(var(--sv-accent-rgb)/0.45)]'
                : 'bg-[rgb(var(--sv-separator-rgb)/0.10)] ring-1 ring-transparent',
            )}
          >
            <span
              className={cn(
                'grid size-6 shrink-0 place-items-center rounded-md transition-all duration-250 ease-ios',
                active
                  ? 'bg-[var(--sv-accent)]'
                  : 'ring-[1.5px] ring-[rgb(var(--sv-hint-rgb)/0.5)]',
              )}
            >
              {active ? (
                <Check
                  className="size-4 text-[var(--sv-accent-text)]"
                  strokeWidth={3}
                />
              ) : null}
            </span>
            <span className="text-[0.9375rem] leading-snug text-[var(--sv-text)]">
              {option.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}

/* ── Asosiy tugma ────────────────────────────────────────────
   Telegram'ning `MainButton` i ataylab ishlatilmadi: u ekran ostida
   turadi va eski mijozlarda matni kech yangilanadi. Sahifadagi tugma
   har yerda bir xil ko'rinadi. */

export function PrimaryButton({
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(
        'flex min-h-[54px] w-full items-center justify-center gap-2 rounded-2xl px-5',
        'bg-[var(--sv-accent)] text-[1.0625rem] font-semibold text-[var(--sv-accent-text)]',
        'shadow-[0_4px_16px_rgb(var(--sv-accent-rgb)/0.32)]',
        'transition-all duration-250 ease-ios active:scale-[0.97]',
        'disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none',
        className,
      )}
      {...props}
    />
  )
}

export function GhostButton({
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(
        'flex min-h-[50px] w-full items-center justify-center rounded-2xl px-5',
        'bg-[rgb(var(--sv-separator-rgb)/0.12)] text-[1rem] font-medium text-[var(--sv-text)]',
        'transition-all duration-250 ease-ios active:scale-[0.97]',
        className,
      )}
      {...props}
    />
  )
}

/* ── To'liq ekranli holat (xato, rahmat, «Telegram ichida oching») ──
   Forma o'rniga chiqadi. Hech qachon xom xato matni yoki kod emas. */

export function StatusScreen({
  icon,
  tone = 'neutral',
  title,
  text,
  children,
}: {
  icon: React.ReactNode
  tone?: 'neutral' | 'accent' | 'danger'
  title: string
  text: string
  children?: React.ReactNode
}) {
  const tint =
    tone === 'accent'
      ? 'bg-[rgb(var(--sv-accent-rgb)/0.14)] text-[var(--sv-accent)]'
      : tone === 'danger'
        ? 'bg-[rgb(var(--sv-danger-rgb)/0.14)] text-[var(--sv-danger)]'
        : 'bg-[rgb(var(--sv-separator-rgb)/0.14)] text-[var(--sv-hint)]'

  return (
    <div className="flex min-h-[80vh] animate-fade-up flex-col items-center justify-center px-6 text-center">
      <div className={cn('mb-5 grid size-[72px] place-items-center rounded-3xl', tint)}>
        {icon}
      </div>
      <h1 className="text-[1.375rem] font-semibold leading-tight text-[var(--sv-text)]">
        {title}
      </h1>
      <p className="mt-2.5 max-w-[19rem] text-[0.9375rem] leading-relaxed text-[var(--sv-hint)]">
        {text}
      </p>
      {children ? <div className="mt-7 w-full max-w-[19rem]">{children}</div> : null}
    </div>
  )
}
