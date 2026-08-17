/**
 * Qidiruv maydoni.
 *
 * Yozilgan matn darhol emas, kechikish bilan yuboriladi — aks holda
 * har harfda backendga so'rov ketardi. Tozalash tugmasi matn
 * yozilgandagina ko'rinadi.
 */

import { Search, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { cn } from '@/shared/lib/utils'
import { Input } from '@/shared/ui/primitives'

export function SearchInput({
  value,
  onChange,
  placeholder,
  className,
  delay = 350,
}: {
  /** Tashqi qiymat — filtrlar tozalanganda maydon ham tozalansin */
  value: string
  onChange: (next: string) => void
  placeholder?: string
  className?: string
  delay?: number
}) {
  const [text, setText] = useState(value)

  // Tashqaridan o'zgarsa (masalan «Tozalash» bosilsa) maydonni tenglashtiramiz
  useEffect(() => {
    setText(value)
  }, [value])

  const latest = useRef(onChange)
  latest.current = onChange

  useEffect(() => {
    if (text === value) return
    const timer = setTimeout(() => latest.current(text), delay)
    return () => clearTimeout(timer)
    // `value` bilan solishtirish uchun kerak, lekin uni kuzatmaymiz —
    // aks holda tashqi yangilanish taymerni qayta ishga tushirardi
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, delay])

  return (
    <div className={cn('relative', className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
      <Input
        className={cn('pl-9', text && 'pr-9')}
        placeholder={placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setText('')
        }}
      />
      {text && (
        <button
          type="button"
          onClick={() => setText('')}
          className={cn(
            'absolute right-2.5 top-1/2 grid size-5 -translate-y-1/2 place-items-center',
            'rounded-full text-muted transition-colors duration-250 ease-ios',
            'hover:bg-surface-2 hover:text-text',
          )}
          aria-label="Tozalash"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  )
}
