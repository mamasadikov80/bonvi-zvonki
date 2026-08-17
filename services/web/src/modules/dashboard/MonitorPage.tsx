/**
 * Monitor rejimi — savdo xonasidagi ekran uchun.
 *
 * Yon panel yo'q, shrift kattaroq, har 60 soniyada avtomatik yangilanadi.
 * VIEWER roli aynan shu sahifa uchun mo'ljallangan.
 */

import { ArrowLeft, LogOut, Maximize2, Minimize2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { useAgentLeaderboard, useOverview } from '@/modules/analytics/api'
import { useAuth } from '@/modules/auth/store'
import { formatNumber, scoreTone, TONE_CLASS } from '@/shared/lib/utils'
import { Avatar, MiniBar, ScoreRing } from '@/shared/ui/dataviz'
import { cn } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/primitives'

const REFRESH_MS = 60_000
const CONTROLS_HIDE_MS = 3_000
const QUERY = { days: 30 }

export function MonitorPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [updatedAt, setUpdatedAt] = useState(new Date())

  const overview = useOverview(QUERY)
  const agents = useAgentLeaderboard(QUERY)

  useEffect(() => {
    const timer = setInterval(() => {
      void overview.refetch()
      void agents.refetch()
      setUpdatedAt(new Date())
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [overview, agents])

  /* ── Chiqish boshqaruvi ────────────────────────────────
     TV ekranda sichqoncha yo'q — shuning uchun tugmalar
     ko'rinmaydi va dizaynni buzmaydi. Odam sichqonchani
     qimirlatsa 3 soniyaga paydo bo'ladi. */

  const [controlsVisible, setControlsVisible] = useState(true)
  const hideTimer = useRef<number | undefined>(undefined)

  const showControls = useCallback(() => {
    setControlsVisible(true)
    window.clearTimeout(hideTimer.current)
    hideTimer.current = window.setTimeout(
      () => setControlsVisible(false),
      CONTROLS_HIDE_MS,
    )
  }, [])

  useEffect(() => {
    showControls()
    window.addEventListener('mousemove', showControls)
    window.addEventListener('touchstart', showControls)
    return () => {
      window.removeEventListener('mousemove', showControls)
      window.removeEventListener('touchstart', showControls)
      window.clearTimeout(hideTimer.current)
    }
  }, [showControls])

  const isViewer = user?.role === 'viewer'

  const exit = useCallback(async () => {
    if (isViewer) {
      await logout()
      navigate('/login')
    } else {
      navigate('/')
    }
  }, [isViewer, logout, navigate])

  // Esc bosilsa ham chiqadi
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !document.fullscreenElement) void exit()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [exit])

  const [fullscreen, setFullscreen] = useState(false)
  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void document.documentElement.requestFullscreen()
  }

  const rows = agents.data ?? []
  const podium = rows.slice(0, 3)
  const rest = rows.slice(3, 10)

  return (
    <div className="min-h-screen bg-bg p-6 lg:p-8 2xl:p-12 3xl:p-16">
      {/* ── Chiqish boshqaruvi ────────────────────────────
          Sichqoncha qimirlaganda paydo bo'ladi, 3 soniyada
          yashirinadi. TV ekranda umuman ko'rinmaydi. */}
      <div
        className={cn(
          'fixed right-5 top-5 z-50 flex items-center gap-2 rounded-2xl bg-surface p-1.5 shadow-lift',
          'transition-all duration-400 ease-ios',
          controlsVisible
            ? 'translate-y-0 opacity-100'
            : 'pointer-events-none -translate-y-2 opacity-0',
        )}
      >
        <Button
          variant="ghost"
          size="icon"
          className="rounded-xl"
          title={fullscreen ? t('monitor.exitFullscreen') : t('monitor.fullscreen')}
          onClick={toggleFullscreen}
        >
          {fullscreen ? (
            <Minimize2 className="size-[18px]" />
          ) : (
            <Maximize2 className="size-[18px]" />
          )}
        </Button>

        <Button variant="secondary" size="sm" className="rounded-xl" onClick={exit}>
          {isViewer ? (
            <>
              <LogOut className="size-3.5" />
              {t('auth.logout')}
            </>
          ) : (
            <>
              <ArrowLeft className="size-3.5" />
              {t('nav.dashboard')}
            </>
          )}
        </Button>
      </div>

      {/* Sarlavha */}
      <header className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            {t('monitor.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">
            {t('monitor.updated')}:{' '}
            {updatedAt.toLocaleTimeString('uz-UZ', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted">
          <span className="size-2 animate-pulse rounded-full bg-good" />
          Jonli
        </div>
      </header>

      {/* KPI */}
      <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4 2xl:gap-6">
        <BigStat
          label={t('kpi.calls')}
          value={formatNumber(overview.data?.calls.value ?? 0)}
        />
        <BigStat
          label={t('kpi.aiScore')}
          value={overview.data?.ai_score.value?.toFixed(1) ?? '—'}
          suffix="/100"
        />
        <BigStat
          label={t('kpi.clientRating')}
          value={
            overview.data?.client_rating.ready
              ? (overview.data.client_rating.value?.toFixed(2) ?? '—')
              : '—'
          }
          suffix="/5"
        />
        <BigStat
          label={t('kpi.redFlags')}
          value={String(overview.data?.red_flags.value ?? 0)}
          tone="bad"
        />
      </div>

      {/* Podium */}
      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3 2xl:gap-6">
        {podium.map((row, index) => {
          const tone = scoreTone(row.ai_score) as 'accent' | 'good' | 'warn' | 'bad'
          return (
            <div
              key={row.agent_id}
              className={cn('card p-6', index === 0 && 'ring-2 ring-accent/30')}
            >
              <div className="mb-4 text-sm font-medium text-muted">#{index + 1}</div>
              <div className="flex items-center gap-4">
                <Avatar name={row.full_name} color={row.color} src={row.avatar_url} size="lg" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-lg font-semibold">{row.full_name}</div>
                  <div className="text-sm text-muted">{row.region}</div>
                </div>
                <ScoreRing value={row.ai_score} tone={tone} size={64} />
              </div>
            </div>
          )
        })}
      </div>

      {/* Qolganlar */}
      <div className="card divide-y divide-border">
        {rest.map((row, index) => {
          const tone = scoreTone(row.ai_score) as 'accent' | 'good' | 'warn' | 'bad'
          return (
            <div key={row.agent_id} className="flex items-center gap-4 px-6 py-3.5">
              <span className="tnum w-6 text-sm text-muted">{index + 4}</span>
              <Avatar name={row.full_name} color={row.color} src={row.avatar_url} size="sm" />
              <span className="flex-1 truncate text-base font-medium">
                {row.full_name}
              </span>
              <span className="tnum w-20 text-right text-sm text-muted">
                {formatNumber(row.calls)}
              </span>
              <MiniBar value={row.ai_score} tone={tone} width={90} />
              <span className={cn('tnum w-14 text-right text-lg font-semibold', TONE_CLASS[tone])}>
                {row.ai_score?.toFixed(1) ?? '—'}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function BigStat({
  label,
  value,
  suffix,
  tone = 'accent',
}: {
  label: string
  value: string
  suffix?: string
  tone?: 'accent' | 'bad'
}) {
  return (
    <div className="card p-6">
      <div className="text-sm uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span
          className={cn(
            'tnum text-4xl font-semibold tracking-tight',
            tone === 'bad' && 'text-bad',
          )}
        >
          {value}
        </span>
        {suffix && <span className="text-base text-muted">{suffix}</span>}
      </div>
    </div>
  )
}
