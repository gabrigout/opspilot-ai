import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input, Select, Textarea } from '@/components/ui/field'
import { useAction } from '@/hooks/useMutationToast'
import { post } from '@/lib/api'
import { INCIDENT_TYPE_LABEL, PRIORITY_LABEL } from '@/lib/format'
import type { Incident } from '@/types/api'

export const incidentSchema = z.object({
  type: z.string().min(1, 'Selecione o tipo'),
  priority: z.string().min(1),
  description: z.string().trim().min(5, 'Descreva o problema (mín. 5 caracteres)').max(2000, 'Máximo de 2000 caracteres'),
  order_ref: z.string().trim().max(64).optional(),
  assignee: z.string().trim().max(120).optional(),
})
type Form = z.infer<typeof incidentSchema>

export function IncidentFormDialog({ open, onOpenChange, orderRef, defaults }: {
  open: boolean; onOpenChange: (o: boolean) => void; orderRef?: string; defaults?: Partial<Form>
}) {
  const { register, handleSubmit, reset, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(incidentSchema),
    defaultValues: { type: 'DELIVERY_DELAY', priority: 'MEDIUM', description: '', order_ref: orderRef ?? '', assignee: '', ...defaults },
  })
  const create = useAction(
    (v: Form) => post<Incident>('/incidents', { ...v, order_ref: v.order_ref || null, assignee: v.assignee || null }),
    { success: (i) => `Ocorrência ${i.code} criada`, onSuccess: () => { reset(); onOpenChange(false) } },
  )
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Nova ocorrência" description="Registre um problema operacional. O histórico de alterações é mantido automaticamente.">
        <form onSubmit={handleSubmit((v) => create.mutate(v))} noValidate className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Tipo" htmlFor="inc-type" error={errors.type?.message}>
              <Select id="inc-type" {...register('type')}>{Object.entries(INCIDENT_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
            </Field>
            <Field label="Prioridade" htmlFor="inc-priority">
              <Select id="inc-priority" {...register('priority')}>{Object.entries(PRIORITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
            </Field>
          </div>
          <Field label="Pedido associado (opcional)" htmlFor="inc-order" error={errors.order_ref?.message}>
            <Input id="inc-order" placeholder="ORD-1042" {...register('order_ref')} />
          </Field>
          <Field label="Responsável (opcional)" htmlFor="inc-assignee">
            <Input id="inc-assignee" placeholder="Nome do responsável" {...register('assignee')} />
          </Field>
          <Field label="Descrição" htmlFor="inc-desc" error={errors.description?.message}>
            <Textarea id="inc-desc" rows={4} {...register('description')} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancelar</Button>
            <Button type="submit" loading={create.isPending}>Criar ocorrência</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
