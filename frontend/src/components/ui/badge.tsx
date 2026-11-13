import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'
import { cn } from '@/lib/utils'

const badgeVariants = cva('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap', {
  variants: {
    tone: {
      neutral: 'border-line bg-surface-2 text-muted',
      primary: 'border-primary/40 bg-primary/15 text-[#a5a8ff]',
      accent: 'border-accent/40 bg-accent/10 text-accent',
      success: 'border-success/40 bg-success/10 text-success',
      warn: 'border-warn/40 bg-warn/10 text-warn',
      danger: 'border-danger/40 bg-danger/10 text-[#ff8585]',
    },
  },
  defaultVariants: { tone: 'neutral' },
})

export type Tone = NonNullable<VariantProps<typeof badgeVariants>['tone']>
export function Badge({ className, tone, ...p }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...p} />
}
