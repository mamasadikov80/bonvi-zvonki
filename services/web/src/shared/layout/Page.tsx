/**
 * Sahifa konteyneri.
 *
 * Barcha sahifalar shundan foydalanadi — kenglik va bo'shliqlar
 * bitta joyda boshqariladi.
 *
 * Prinsip: qat'iy `max-width` YO'Q. Kontent mavjud kenglikni
 * to'liq egallaydi, faqat yon bo'shliq ekran o'sishi bilan kengayadi.
 * Shunday qilib 4K monitorda ham, televizorda ham bo'sh joy qolmaydi.
 */

import type { ReactNode } from 'react'

import { cn } from '@/shared/lib/utils'

export function Page({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'w-full space-y-4',
        // Yon bo'shliq ekran bilan birga o'sadi
        'px-4 py-4 sm:px-5 lg:px-6 lg:py-6 2xl:px-10 3xl:px-14',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight 2xl:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

/**
 * Ustunli tarmoq — keng ekranda kartalar yonma-yon joylashadi.
 *
 * Sabab: matnli kontent (rubrika kriteriyalari, sozlama maydonlari)
 * 2000px kenglikda cho'zilib ketsa o'qish qiyinlashadi. Cho'zish
 * o'rniga ustunlarga bo'lamiz — bo'sh joy ham qolmaydi, o'qish ham qulay.
 */
export function PageGrid({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        // `items-start` — MUHIM. CSS grid'da element qatordagi eng
        // balandiga cho'ziladi (`align-items: stretch`). Sozlamalar
        // sahifasida yonma-yon turgan kartalar juda har xil: biri
        // ikkita tugmadan iborat, ikkinchisi butun AI bloki. Shu
        // sababli kichigining tagida ulkan bo'sh joy qolardi.
        // Endi har karta o'z mazmuni qadar baland.
        'grid grid-cols-1 items-start gap-4 xl:grid-cols-2 3xl:grid-cols-3',
        className,
      )}
    >
      {children}
    </div>
  )
}
