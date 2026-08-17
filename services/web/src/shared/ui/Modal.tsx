/**
 * Modal oyna.
 *
 * QOIDA: har qanday yaratish / tahrirlash SHU YERDA bo'ladi.
 * Sahifaning o'ziga input maydonlari chiqarilmaydi.
 *
 * Radix Dialog ustiga qurilgan — fokus tuzog'i, Esc, aria
 * atributlari tayyor holda keladi.
 */

import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/primitives'

type Size = 'sm' | 'md' | 'lg' | 'xl'

const SIZE: Record<Size, string> = {
  sm: 'max-w-md',
  md: 'max-w-xl',
  lg: 'max-w-3xl',
  xl: 'max-w-5xl',
}

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  size = 'md',
  children,
  footer,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  size?: Size
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            'fixed inset-0 z-50 bg-black/30 backdrop-blur-sm',
            'data-[state=open]:animate-in data-[state=open]:fade-in-0',
            'data-[state=closed]:animate-out data-[state=closed]:fade-out-0',
          )}
        />

        <Dialog.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2',
            SIZE[size],
            'flex max-h-[calc(100vh-4rem)] flex-col overflow-hidden',
            'rounded-2xl bg-surface shadow-pop',
            'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
            'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
            'focus:outline-none',
          )}
        >
          {/* Sarlavha — qotib turadi */}
          <div className="flex shrink-0 items-start justify-between gap-4 px-6 pt-5">
            <div className="min-w-0">
              <Dialog.Title className="text-base font-semibold tracking-tight">
                {title}
              </Dialog.Title>
              {description && (
                <Dialog.Description className="mt-1 text-xs text-muted">
                  {description}
                </Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon" className="size-8 shrink-0">
                <X className="size-4" />
              </Button>
            </Dialog.Close>
          </div>

          {/* Tana — faqat shu joy scroll qiladi */}
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>

          {/* Amallar — qotib turadi */}
          {footer && (
            <div className="flex shrink-0 items-center justify-end gap-2 bg-surface-2/50 px-6 py-4">
              {footer}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/** Modal ichidagi forma maydonlari uchun tarmoq */
export function ModalFields({
  children,
  columns = 2,
}: {
  children: ReactNode
  columns?: 1 | 2
}) {
  return (
    <div className={cn('grid gap-4', columns === 2 && 'sm:grid-cols-2')}>{children}</div>
  )
}
