import { ArrowRight, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate } from 'react-router-dom'

import { useAuth } from '@/modules/auth/store'
import { cn } from '@/shared/lib/utils'
import { Button, Input, Label } from '@/shared/ui/primitives'

const DEMO_ACCOUNTS = [
  { email: 'admin@zvonki.uz', password: 'admin12345', roleKey: 'roles.admin' },
  { email: 'manager@zvonki.uz', password: 'manager12345', roleKey: 'roles.manager' },
  { email: 'sardor@zvonki.uz', password: 'sardor12345', roleKey: 'roles.sales' },
  { email: 'viewer@zvonki.uz', password: 'viewer12345', roleKey: 'roles.viewer' },
]

export function LoginPage() {
  const { t } = useTranslation()
  const { login, status } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('admin@zvonki.uz')
  const [password, setPassword] = useState('admin12345')
  const [error, setError] = useState<string | null>(null)

  if (status === 'authenticated') return <Navigate to="/" replace />

  const loading = status === 'loading'

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await login(email, password)
      // Kuzatuvchi — TV ekran hisobi, to'g'ridan monitor rejimiga.
      // Bu FAQAT kirish paytida bir marta, keyin u xohlasa
      // boshqaruv paneliga o'ta oladi (tuzoqqa tushmaydi).
      const role = useAuth.getState().user?.role
      navigate(role === 'viewer' ? '/monitor' : '/')
    } catch {
      setError(t('auth.invalidCredentials'))
    }
  }

  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden bg-bg p-6">
      {/* Yumshoq fon nuri — iOS'ga xos chuqurlik hissi */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-0 size-[640px] -translate-x-1/2 -translate-y-1/3 rounded-full opacity-[0.07] blur-3xl"
        style={{ background: 'hsl(var(--accent))' }}
      />

      <div className="relative w-full max-w-[440px]">
        {/* Brend */}
        <div className="mb-10 animate-fade-up text-center">
          <img
            src="/brand/bonvi-lockup.png"
            alt="Bonvi"
            width={582}
            height={142}
            className="brand-logo mx-auto mb-8 h-9 w-auto"
          />
          <h1 className="text-[1.75rem] font-semibold leading-tight tracking-tight">
            {t('auth.welcome')}
          </h1>
          <p className="mx-auto mt-2.5 max-w-[340px] text-[0.9375rem] leading-relaxed text-muted">
            {t('auth.subtitle')}
          </p>
        </div>

        {/* Forma */}
        <form onSubmit={submit} className="card animate-scale-in space-y-5 p-8">
          <div>
            <Label htmlFor="email" className="mb-2 text-[0.8125rem]">
              {t('auth.email')}
            </Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              className="h-12 text-[0.9375rem]"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div>
            <Label htmlFor="password" className="mb-2 text-[0.8125rem]">
              {t('auth.password')}
            </Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              className="h-12 text-[0.9375rem]"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <p className="animate-scale-in rounded-xl bg-bad/10 px-4 py-3 text-[0.8125rem] text-bad">
              {error}
            </p>
          )}

          <Button
            type="submit"
            size="lg"
            className="h-12 w-full text-[0.9375rem]"
            disabled={loading}
          >
            {loading ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                {t('auth.signingIn')}
              </>
            ) : (
              <>
                {t('auth.signIn')}
                <ArrowRight className="size-4" />
              </>
            )}
          </Button>
        </form>

        {/* Demo hisoblar */}
        <div className="mt-8 animate-fade-up">
          <p className="mb-3 text-center text-2xs font-medium uppercase tracking-wider text-muted">
            {t('auth.demoHint')}
          </p>
          <div className="grid grid-cols-2 gap-2">
            {DEMO_ACCOUNTS.map((account) => {
              const active = email === account.email
              return (
                <button
                  key={account.email}
                  type="button"
                  onClick={() => {
                    setEmail(account.email)
                    setPassword(account.password)
                    setError(null)
                  }}
                  className={cn(
                    'rounded-xl bg-surface px-4 py-3 text-left transition-all duration-250 ease-ios',
                    'active:scale-[0.97] hover:shadow-soft',
                    active ? 'shadow-soft ring-1 ring-accent/40' : 'shadow-xs',
                  )}
                >
                  <div className="text-[0.8125rem] font-medium text-text">
                    {t(account.roleKey)}
                  </div>
                  <div className="truncate text-2xs text-muted">{account.email}</div>
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
