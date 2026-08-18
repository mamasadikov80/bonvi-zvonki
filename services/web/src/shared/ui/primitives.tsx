import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'

import { cn } from '@/shared/lib/utils'

/* ── Button — iOS: yumaloq, bosilganda kichrayadi ─────────── */

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl',
    'text-sm font-medium transition-all duration-250 ease-ios',
    'active:scale-[0.97]',
    'disabled:pointer-events-none disabled:opacity-40',
    '[&_svg]:size-4 [&_svg]:shrink-0',
  ].join(' '),
  {
    variants: {
      variant: {
        primary: 'bg-accent text-white shadow-xs hover:bg-accent/90 hover:shadow-soft',
        secondary: 'bg-surface-2 text-text hover:bg-surface-2/60',
        ghost: 'text-muted hover:bg-surface-2 hover:text-text',
        danger: 'bg-bad text-white shadow-xs hover:bg-bad/90',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-9 px-4',
        lg: 'h-11 px-5 text-[0.9375rem]',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    )
  },
)
Button.displayName = 'Button'

/* ── Card ────────────────────────────────────────────────── */

export function Card({
  className,
  hover,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { hover?: boolean }) {
  return <div className={cn('card', hover && 'card-hover', className)} {...props} />
}

export function CardHeader({
  title,
  hint,
  action,
  className,
}: {
  title: string
  hint?: string
  action?: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex items-start justify-between gap-4 px-6 pt-5', className)}>
      <div className="min-w-0">
        <h3 className="text-[0.9375rem] font-semibold text-text">{title}</h3>
        {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      </div>
      {action}
    </div>
  )
}

/** `ComponentProps<'div'>` — `HTMLAttributes` dan farqi `ref` ni ham
 *  qabul qilishi. Ichida suriladigan karta (transkript) joriy qatorni
 *  ko'rinishga tortish uchun konteynerga murojaat qila olishi kerak. */
export function CardBody({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('p-6', className)} {...props} />
}

/* ── Badge — pill shaklda ────────────────────────────────── */

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-2xs font-medium',
  {
    variants: {
      tone: {
        neutral: 'bg-surface-2 text-muted',
        accent: 'bg-accent-soft text-accent',
        good: 'bg-good/10 text-good',
        warn: 'bg-warn/10 text-warn',
        bad: 'bg-bad/10 text-bad',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
)

export function Badge({
  className,
  tone,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />
}

/* ── Input / Label ───────────────────────────────────────── */

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      // ⚠️ CHEGARA MAJBURIY. `surface-2` oq kartada atigi 3,5% farq
      // qiladi — maydon oddiy matndek ko'rinadi va foydalanuvchi uni
      // boshqaruv elementi deb tanimaydi.
      'h-10 w-full rounded-xl bg-surface-2 px-3.5 text-sm text-text',
      'ring-1 ring-inset ring-border',
      'placeholder:text-muted/50 transition-all duration-250 ease-ios',
      'hover:ring-border/80 focus:bg-surface focus:outline-none focus:ring-2 focus:ring-accent/40',
      'disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
    {...props}
  />
))
Input.displayName = 'Input'

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement> & {
    /** Chap tomondagi belgicha — filtr nima haqidaligini bir qarashda
     *  bildiradi. Bir qatorda to'rt-besh tanlagich turganda matnni
     *  o'qimasdan farqlash imkonini beradi. */
    icon?: LucideIcon
    /** Tanlov qo'yilganmi — bo'sh filtrdan ajratib turadi */
    active?: boolean
    /** Ixcham variant (h-9) — ixcham filtr qatorlari uchun.
     *
     *  ⚠️ Alohida prop, chunki `className` endi TASHQI qavatga
     *  tushadi: u yerga `h-9` yozilsa tanlagichning o'zi baland
     *  qolib, qator elementlari bir chiziqda turmasdi. */
    compact?: boolean
  }
>(({ className, icon: Icon, active, compact, ...props }, ref) => (
  <div className={cn('relative', className)}>
    {Icon && (
      <Icon
        className={cn(
          'pointer-events-none absolute left-3 top-1/2 -translate-y-1/2',
          compact ? 'size-3.5' : 'size-4',
          active ? 'text-accent' : 'text-muted',
        )}
        aria-hidden
      />
    )}
    <select
      ref={ref}
      className={cn(
        // ⚠️ CHEGARA MAJBURIY. `surface-2` oq kartada atigi 3,5% farq
        // qiladi — tanlagich oddiy so'zdek ko'rinadi va uni bosish
        // mumkinligi bilinmaydi.
        'w-full cursor-pointer appearance-none rounded-xl bg-surface-2 pr-9',
        compact ? 'h-9 text-xs' : 'h-10 text-sm',
        'ring-1 ring-inset transition-all duration-250 ease-ios',
        'focus:bg-surface focus:outline-none focus:ring-2 focus:ring-accent/40',
        'disabled:cursor-not-allowed disabled:opacity-50',
        Icon ? 'pl-9' : 'pl-3.5',
        // Tanlov qo'yilgan filtr ajralib turadi — aks holda qaysi biri
        // ishlayotganini bilish uchun har birini o'qib chiqish kerak
        active
          ? 'bg-accent-soft font-medium text-accent ring-accent/30'
          : 'text-text ring-border hover:ring-border/80',
        "bg-[url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='%2394a3b8' stroke-width='1.5'%3E%3Cpath d='M4 6l4 4 4-4'/%3E%3C/svg%3E\")] bg-[length:16px] bg-[right_0.75rem_center] bg-no-repeat",
      )}
      {...props}
    />
  </div>
))
Select.displayName = 'Select'

export function Label({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn('mb-1.5 block text-xs font-medium text-text', className)}
      {...props}
    />
  )
}

/* ── Switch — iOS toggle ─────────────────────────────────── */

export function Switch({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  /** Ekran o'quvchilar uchun nom */
  label?: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        // inline-flex + items-center: knob oqim ichida qoladi,
        // shuning uchun trekdan hech qachon chiqib keta olmaydi
        'inline-flex h-7 w-12 shrink-0 grow-0 basis-auto items-center rounded-full p-0.5',
        'transition-colors duration-250 ease-ios',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-40',
        checked ? 'bg-good' : 'bg-muted/25',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'block size-6 rounded-full bg-white shadow-soft',
          'transition-transform duration-250 ease-ios',
          checked ? 'translate-x-5' : 'translate-x-0',
        )}
      />
    </button>
  )
}

/* ── Segmented control ───────────────────────────────────── */

export function Segmented<T extends string | number>({
  items,
  value,
  onChange,
  className,
}: {
  items: { value: T; label: string }[]
  value: T
  onChange: (next: T) => void
  className?: string
}) {
  return (
    <div className={cn('segment', className)}>
      {items.map((item) => (
        <button
          key={String(item.value)}
          type="button"
          data-active={item.value === value}
          onClick={() => onChange(item.value)}
          className="segment-item"
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}

/* ── Skeleton ────────────────────────────────────────────── */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-xl bg-surface-2', className)} />
}

/* ── Empty state ─────────────────────────────────────────── */

export function EmptyState({
  message,
  hint,
  action,
}: {
  message: string
  /** Nega bo'sh ekanini tushuntiruvchi qo'shimcha qator */
  hint?: string
  /** Chiqish yo'li — masalan «filtrni tozalash» */
  action?: { label: string; onClick: () => void }
}) {
  return (
    <div className="flex min-h-[160px] flex-col items-center justify-center gap-1.5 px-6 text-center">
      <p className="text-sm text-muted">{message}</p>
      {hint && <p className="max-w-md text-2xs leading-relaxed text-muted/80">{hint}</p>}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-1.5 h-8 rounded-xl bg-surface-2 px-3.5 text-xs font-medium transition-all duration-250 ease-ios active:scale-[0.97] hover:bg-surface-2/70"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
