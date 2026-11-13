import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import * as React from 'react'
import { cn } from '@/lib/utils'

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close

export function DialogContent({
  className, children, title, description, side = 'center', ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & { title: string; description?: string; side?: 'center' | 'right' }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px]" />
      <DialogPrimitive.Content
        aria-describedby={description ? undefined : undefined}
        className={cn(
          'fixed z-50 flex flex-col border border-line bg-surface shadow-2xl shadow-black/50 focus:outline-none',
          side === 'center'
            ? 'left-1/2 top-1/2 max-h-[88vh] w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-xl'
            : 'right-0 top-0 h-full w-full max-w-xl border-y-0 border-r-0',
          className,
        )}
        {...props}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <DialogPrimitive.Title className="truncate text-base font-semibold">{title}</DialogPrimitive.Title>
            <DialogPrimitive.Description className={cn('mt-0.5 text-xs text-muted', !description && 'sr-only')}>
              {description ?? title}
            </DialogPrimitive.Description>
          </div>
          <DialogPrimitive.Close aria-label="Fechar" className="rounded-md p-1 text-muted hover:bg-surface-2 hover:text-fg cursor-pointer">
            <X className="h-4 w-4" />
          </DialogPrimitive.Close>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}
