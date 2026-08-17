/**
 * Ko'p tanlovli dropdown.
 *
 * Nima uchun kerak: hududlar ro'yxati endi admin qo'lida va u o'sib
 * boradi (bitta viloyat bir nechta hududga bo'linadi). Tanlovni ekranga
 * uzun tugmalar qatori qilib yoyish 10 tadan keyin filtrlar panelini
 * yeb qo'yadi. Shuning uchun tanlov popover ichida, tugmada esa faqat
 * NATIJA turadi: «Hududlar» → «Samarqand» → «3 ta hudud».
 *
 * Idioma `DateRangePicker` dan olingan: Radix Popover, `rounded-2xl`,
 * `shadow-pop`, `ease-ios`. Klaviatura: Tab bilan kiriladi, ↑/↓ bilan
 * yuriladi, Home/End chetiga sakraydi, Enter/Space belgilaydi,
 * Esc yopadi (Radix). Fokus halqasi har doim ko'rinadi.
 */

import * as Popover from '@radix-ui/react-popover'
import { Check, ChevronDown, Search } from 'lucide-react'
import { useMemo, useRef, useState, type ComponentType, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/shared/lib/utils'
import { Input } from '@/shared/ui/primitives'

export interface MultiSelectOption {
  value: string
  label: string
  /** Ikkinchi qator — masalan «faol emas» yoki xodimning hududi */
  hint?: string
}

/** Element soni shundan oshsa qidiruv maydoni chiqadi */
const SEARCH_AFTER = 8

export function MultiSelect({
  options,
  value,
  onChange,
  label,
  summary,
  icon: Icon,
  align = 'start',
  className,
  disabled,
}: {
  options: MultiSelectOption[]
  value: string[]
  onChange: (next: string[]) => void
  /** Hech narsa tanlanmaganda tugmada turadigan matn: «Hududlar» */
  label: string
  /** 2 va undan ortiq tanlovda: (3) => «3 ta hudud» */
  summary?: (count: number) => string
  icon?: ComponentType<{ className?: string }>
  align?: 'start' | 'center' | 'end'
  className?: string
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  const selected = useMemo(() => new Set(value), [value])
  const showSearch = options.length > SEARCH_AFTER

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    if (!needle) return options
    return options.filter(
      (option) =>
        option.label.toLocaleLowerCase().includes(needle) ||
        (option.hint?.toLocaleLowerCase().includes(needle) ?? false),
    )
  }, [options, query])

  // Tugmadagi matn: bo'sh → nom, bitta → o'sha nom, ko'p → son
  const triggerText =
    value.length === 0
      ? label
      : value.length === 1
        ? (options.find((option) => option.value === value[0])?.label ?? value[0])
        : (summary?.(value.length) ?? t('filters.selected', { count: value.length }))

  const toggle = (item: string) =>
    onChange(
      selected.has(item) ? value.filter((x) => x !== item) : [...value, item],
    )

  /** ↑/↓/Home/End — ro'yxat bo'ylab fokusni ko'chirish */
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End']
    if (!keys.includes(event.key)) return
    const nodes = Array.from(
      listRef.current?.querySelectorAll<HTMLButtonElement>('[data-option]') ?? [],
    )
    if (!nodes.length) return
    event.preventDefault()

    const current = nodes.indexOf(document.activeElement as HTMLButtonElement)
    let next: number
    if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = nodes.length - 1
    else {
      const step = event.key === 'ArrowDown' ? 1 : -1
      next =
        current < 0
          ? step === 1
            ? 0
            : nodes.length - 1
          : (current + step + nodes.length) % nodes.length
    }
    nodes[next]?.focus()
  }

  const allSelected = options.length > 0 && value.length === options.length
  const active = value.length > 0

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setQuery('')
      }}
    >
      <Popover.Trigger asChild>
        <button
          type="button"
          disabled={disabled}
          aria-label={label}
          className={cn(
            'inline-flex h-9 max-w-[16rem] items-center gap-2 rounded-xl px-3.5 text-xs font-medium',
            'transition-all duration-250 ease-ios active:scale-[0.97]',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
            'disabled:pointer-events-none disabled:opacity-40',
            active
              ? 'bg-accent-soft text-accent'
              : 'bg-surface-2 text-text hover:bg-surface-2/70',
            className,
          )}
        >
          {Icon && (
            <Icon
              className={cn('size-3.5 shrink-0', active ? 'text-accent' : 'text-muted')}
            />
          )}
          <span className="truncate">{triggerText}</span>
          <ChevronDown
            className={cn(
              'size-3.5 shrink-0 transition-transform duration-250 ease-ios',
              open && 'rotate-180',
              active ? 'text-accent' : 'text-muted',
            )}
          />
        </button>
      </Popover.Trigger>

      <Popover.Portal>
        <Popover.Content
          align={align}
          sideOffset={8}
          onKeyDown={onKeyDown}
          className={cn(
            'z-50 w-[min(20rem,calc(100vw-2rem))] rounded-2xl bg-surface p-1.5 shadow-pop',
            'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
            'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
            'focus:outline-none',
          )}
        >
          {/* Sarlavha + ommaviy amallar */}
          <div className="flex items-center justify-between gap-2 px-2 pb-1 pt-1.5">
            <span className="label-eyebrow truncate">{label}</span>
            <div className="flex shrink-0 items-center gap-0.5">
              <QuickAction
                onClick={() => onChange(options.map((option) => option.value))}
                disabled={allSelected}
              >
                {t('filters.all')}
              </QuickAction>
              <QuickAction onClick={() => onChange([])} disabled={!active}>
                {t('filters.reset')}
              </QuickAction>
            </div>
          </div>

          {/* Qidiruv — ro'yxat uzun bo'lgandagina */}
          {showSearch && (
            <div className="relative px-1 pb-1.5 pt-0.5">
              <Search className="pointer-events-none absolute left-4 top-1/2 size-3.5 -translate-y-1/2 text-muted" />
              <Input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t('common.search')}
                aria-label={t('common.search')}
                className="h-9 pl-9 text-xs"
              />
            </div>
          )}

          {/* Ro'yxat — faqat shu joy scroll qiladi */}
          <div
            ref={listRef}
            role="listbox"
            aria-multiselectable
            aria-label={label}
            className="max-h-[17rem] space-y-0.5 overflow-y-auto p-0.5"
          >
            {visible.length === 0 ? (
              <p className="px-3 py-6 text-center text-2xs text-muted">
                {t('filters.notFound')}
              </p>
            ) : (
              visible.map((option) => {
                const checked = selected.has(option.value)
                return (
                  <button
                    key={option.value}
                    type="button"
                    data-option
                    role="option"
                    aria-selected={checked}
                    onClick={() => toggle(option.value)}
                    className={cn(
                      'flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-xs',
                      'transition-colors duration-250 ease-ios',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
                      checked
                        ? 'bg-accent-soft text-accent'
                        : 'text-text hover:bg-surface-2',
                    )}
                  >
                    <span
                      aria-hidden
                      className={cn(
                        'grid size-4 shrink-0 place-items-center rounded-md',
                        'transition-colors duration-250 ease-ios',
                        checked ? 'bg-accent text-white' : 'bg-surface-2',
                      )}
                    >
                      {checked && <Check className="size-3" strokeWidth={3} />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{option.label}</span>
                      {option.hint && (
                        <span className="block truncate text-2xs text-muted">
                          {option.hint}
                        </span>
                      )}
                    </span>
                  </button>
                )
              })
            )}
          </div>

          {active && (
            <p className="px-2.5 pb-1 pt-1.5 text-2xs text-muted">
              {t('filters.selected', { count: value.length })}
            </p>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

function QuickAction({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void
  disabled?: boolean
  children: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded-lg px-2 py-1 text-2xs font-medium',
        'transition-colors duration-250 ease-ios',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
        'disabled:pointer-events-none disabled:opacity-35',
        'text-muted hover:bg-surface-2 hover:text-text',
      )}
    >
      {children}
    </button>
  )
}
