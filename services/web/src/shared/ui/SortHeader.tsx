/**
 * Saralanadigan jadval sarlavhasi.
 *
 * Bosilganda: o'sish → kamayish → boshlang'ich holat.
 * Faol ustun ajralib turadi, qolganlarida strelka faqat kursor
 * ustiga kelganda ko'rinadi — jadval tinch qoladi.
 */

import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'

import { cn } from '@/shared/lib/utils'

export interface SortState<F extends string> {
  field: F
  order: 'asc' | 'desc'
}

export function SortHeader<F extends string>({
  field,
  label,
  state,
  onChange,
  align = 'left',
  /** Boshlang'ich yo'nalish. Raqamlar uchun odatda kamayish qulayroq */
  firstOrder = 'asc',
}: {
  field: F
  label: string
  state: SortState<F>
  onChange: (next: SortState<F>) => void
  align?: 'left' | 'right'
  firstOrder?: 'asc' | 'desc'
}) {
  const active = state.field === field
  const order = active ? state.order : null

  const toggle = () => {
    if (!active) return onChange({ field, order: firstOrder })
    onChange({ field, order: state.order === 'asc' ? 'desc' : 'asc' })
  }

  const Icon = order === 'asc' ? ArrowUp : order === 'desc' ? ArrowDown : ChevronsUpDown

  return (
    <th
      className={cn(
        'px-4 py-3 text-2xs font-medium uppercase tracking-wider',
        align === 'right' ? 'text-right' : 'text-left',
      )}
      aria-sort={
        active ? (state.order === 'asc' ? 'ascending' : 'descending') : 'none'
      }
    >
      <button
        type="button"
        onClick={toggle}
        className={cn(
          'group inline-flex items-center gap-1 rounded-md px-1 py-0.5 -mx-1',
          'uppercase tracking-wider transition-colors duration-250 ease-ios',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30',
          align === 'right' && 'flex-row-reverse',
          active ? 'text-accent' : 'text-muted hover:text-text',
        )}
      >
        {label}
        <Icon
          className={cn(
            'size-3 shrink-0 transition-opacity duration-250 ease-ios',
            active ? 'opacity-100' : 'opacity-0 group-hover:opacity-40',
          )}
        />
      </button>
    </th>
  )
}
