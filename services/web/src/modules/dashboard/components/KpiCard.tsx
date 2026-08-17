import type { LucideIcon } from 'lucide-react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'

import { cn } from '@/shared/lib/utils'
import { Sparkline } from '@/shared/ui/dataviz'
import { Skeleton } from '@/shared/ui/primitives'

interface Props {
  label: string
  value: string | number | null
  suffix?: string
  delta?: number | null
  /** true bo'lsa o'sish yomon (masalan, qoidabuzarliklar) */
  invertDelta?: boolean
  icon?: LucideIcon
  spark?: (number | null)[]
  tone?: 'accent' | 'good' | 'warn' | 'bad'
  loading?: boolean
  /** Qiymat yo'qligining sababi — quruq chiziqcha «buzilgan» degan
   *  taassurot beradi, izoh esa nimani kutayotganini tushuntiradi */
  hint?: string
}

const TILE_TONE: Record<string, string> = {
  accent: 'bg-accent-soft text-accent',
  good: 'bg-good/10 text-good',
  warn: 'bg-warn/10 text-warn',
  bad: 'bg-bad/10 text-bad',
}

export function KpiCard({
  label,
  value,
  suffix,
  delta,
  invertDelta = false,
  icon: Icon,
  spark,
  tone = 'accent',
  loading,
  hint,
}: Props) {
  const isPositive = delta != null && delta > 0
  const isGood = invertDelta ? !isPositive : isPositive

  return (
    // Ikonka YONIDA, tagida emas. Ilgari uch qavat edi — ikonka,
    // raqam, yorliq — va karta baland bo'lib, ekranning yarmini
    // beshta sanoq egallardi. Endi ikonka chapda, matn o'ngda:
    // qatorlar ikkitaga tushdi, ko'z esa raqamdan yorliqqa
    // to'g'ridan-to'g'ri o'tadi.
    //
    // `flex h-full flex-col` + sparkline'dagi `mt-auto` — kartalar
    // bir qatorda turli balandlikda bo'lgani uchun kerak (biriga
    // sparkline tushadi, biriga izoh). Ularsiz yorliqlar bir
    // chiziqda turmasdi.
    <div className="card card-hover animate-fade-up flex h-full flex-col overflow-hidden p-5">
      <div className="flex items-start gap-3.5">
        {Icon && (
          <span className={cn('icon-tile size-10 shrink-0', TILE_TONE[tone])}>
            <Icon className="size-[18px]" />
          </span>
        )}

        <div className="min-w-0 flex-1">
          {loading ? (
            <Skeleton className="h-8 w-24" />
          ) : (
            <div className="flex items-baseline gap-1.5">
              <span className="tnum text-[1.75rem] font-semibold leading-none tracking-tight">
                {value ?? '—'}
              </span>
              {suffix && value != null && (
                <span className="text-sm text-muted">{suffix}</span>
              )}
            </div>
          )}

          {/* Yorliq bir qatorda qoladi: uzun nom («O'rtacha davomiylik»)
              ikkinchi qatorga tushsa, o'sha karta qo'shnilaridan baland
              bo'lib qatorni buzardi. Sig'masa uchta nuqta qo'yiladi. */}
          <div className="mt-1.5 truncate text-[0.8125rem] text-muted" title={label}>
            {label}
          </div>
        </div>

        {!loading && delta != null && (
          <span
            className={cn(
              'tnum inline-flex shrink-0 items-center gap-0.5 rounded-full px-2 py-1 text-2xs font-semibold',
              isGood ? 'bg-good/10 text-good' : 'bg-bad/10 text-bad',
            )}
          >
            {isPositive ? (
              <ArrowUpRight className="size-3" />
            ) : (
              <ArrowDownRight className="size-3" />
            )}
            {Math.abs(delta)}%
          </span>
        )}
      </div>

      {!loading && hint && (
        <div className="mt-2 text-2xs leading-snug text-muted/80">{hint}</div>
      )}

      {/* Sparkline — kartaning tagida. `mt-auto` bo'lmasa u matnga
          yopishib, sparklinesiz kartalar bilan qator buzilardi. */}
      {!loading && spark && spark.length > 1 && (
        <div className="-mx-5 -mb-5 mt-auto pt-4">
          <Sparkline data={spark} tone={tone} height={38} />
        </div>
      )}
    </div>
  )
}
