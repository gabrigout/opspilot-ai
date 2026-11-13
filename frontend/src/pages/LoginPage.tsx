import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { Info } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Field, Input } from '@/components/ui/field'
import { useAuth } from '@/hooks/useAuth'
import { errorMessage, get } from '@/lib/api'

export const loginSchema = z.object({
  email: z.string().min(1, 'Informe o e-mail').regex(/^[^@\s]+@[^@\s]+$/, 'E-mail inválido'),
  password: z.string().min(1, 'Informe a senha'),
})
type LoginForm = z.infer<typeof loginSchema>

export default function LoginPage() {
  const { login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  // Demo credentials are only offered when the backend says it is NOT a production environment.
  const health = useQuery({ queryKey: ['health'], queryFn: () => get<{ environment: string }>('/health'), retry: false, staleTime: Infinity })
  const showDemoHint = !!health.data && health.data.environment !== 'production'
  const { register, handleSubmit, setValue, formState: { errors, isSubmitting } } = useForm<LoginForm>({ resolver: zodResolver(loginSchema) })

  const onSubmit = handleSubmit(async (v) => {
    setError(null)
    try { await login(v.email, v.password) } catch (e) { setError(errorMessage(e)) }
  })

  return (
    <div className="grid min-h-full place-items-center p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary shadow-lg shadow-primary/30">
            <svg viewBox="0 0 32 32" className="h-6 w-6" aria-hidden><path d="M8 20 L16 7 L24 20 L16 16.5 Z" fill="#F9FAFB" /><circle cx="16" cy="24" r="2" fill="#22D3EE" /></svg>
          </span>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">OpsPilot <span className="text-accent">AI</span></h1>
            <p className="text-xs text-muted">Intelligent Delivery Operations Platform</p>
          </div>
        </div>
        <form onSubmit={onSubmit} noValidate className="space-y-4 rounded-xl border border-line bg-surface/90 p-6 shadow-xl shadow-black/30">
          <h2 className="text-base font-semibold">Entrar</h2>
          <Field label="E-mail" htmlFor="email" error={errors.email?.message}>
            <Input id="email" type="email" autoComplete="username" {...register('email')} />
          </Field>
          <Field label="Senha" htmlFor="password" error={errors.password?.message}>
            <Input id="password" type="password" autoComplete="current-password" {...register('password')} />
          </Field>
          {error && <p role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-[#ff8585]">{error}</p>}
          <Button type="submit" className="w-full" loading={isSubmitting}>Entrar</Button>
          {showDemoHint && (
            <button type="button" className="flex w-full cursor-pointer items-start gap-2 rounded-lg border border-line bg-bg/50 p-3 text-left text-xs text-muted hover:bg-surface-2"
              onClick={() => { setValue('email', 'admin@opspilot.local'); setValue('password', 'opspilot-demo') }}>
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" aria-hidden />
              <span>Ambiente de demonstração com dados fictícios. Clique para preencher a conta <code className="text-fg">admin@opspilot.local</code> (senha <code className="text-fg">opspilot-demo</code>).</span>
            </button>
          )}
        </form>
        <p className="mt-4 text-center text-[11px] leading-relaxed text-muted">
          Projeto independente de demonstração tecnológica. Todos os dados são fictícios e simulados; sem vínculo com empresas reais.
        </p>
      </div>
    </div>
  )
}
