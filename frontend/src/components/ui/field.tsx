import * as React from 'react'
import { cn } from '@/lib/utils'

const base =
  'w-full rounded-lg border border-line bg-bg/60 px-3 text-sm text-fg placeholder:text-muted/70 focus-visible:border-primary disabled:opacity-50'

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...p }, ref) => <input ref={ref} className={cn(base, 'h-9', className)} {...p} />,
)
Input.displayName = 'Input'

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...p }, ref) => <select ref={ref} className={cn(base, 'h-9 cursor-pointer pr-8', className)} {...p} />,
)
Select.displayName = 'Select'

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...p }, ref) => <textarea ref={ref} className={cn(base, 'min-h-20 py-2', className)} {...p} />,
)
Textarea.displayName = 'Textarea'

export function Field({ label, error, children, htmlFor }: { label: string; error?: string; children: React.ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-xs font-medium text-muted">{label}</label>
      {children}
      {error && <p role="alert" className="text-xs text-[#ff8585]">{error}</p>}
    </div>
  )
}
