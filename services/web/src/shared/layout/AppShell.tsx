import {
  ArrowLeft,
  LayoutDashboard,
  ListChecks,
  LogOut,
  MapPin,
  Menu,
  MessagesSquare,
  Monitor,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Phone,
  Settings,
  Star,
  Sun,
  Users,
  UserCog,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { ErrorBoundary } from '@/shared/ui/ErrorBoundary'
import { QueryErrorBanner } from '@/shared/ui/QueryErrorBanner'

import { useAuth } from '@/modules/auth/store'
import { useTheme } from '@/shared/hooks/useTheme'
import { LANGUAGES, setLanguage, type LanguageCode } from '@/shared/i18n'
import { cn } from '@/shared/lib/utils'
import { Avatar } from '@/shared/ui/dataviz'
import { Button } from '@/shared/ui/primitives'

/* ── Navigatsiya ta'rifi ─────────────────────────────────── */

interface NavItem {
  to: string
  labelKey: string
  /** SALES roli uchun boshqa nom ("Mening qo'ng'iroqlarim") */
  salesLabelKey?: string
  icon: typeof LayoutDashboard
  /** Ko'rsatish uchun kerakli ruxsatlardan KAMIDA BITTASI */
  anyOf?: string[]
  group?: string
}

const NAV: NavItem[] = [
  {
    to: '/',
    labelKey: 'nav.dashboard',
    salesLabelKey: 'nav.myResults',
    icon: LayoutDashboard,
  },
  {
    to: '/calls',
    labelKey: 'nav.calls',
    salesLabelKey: 'nav.myCalls',
    icon: Phone,
    anyOf: ['calls:read', 'calls:read:own'],
  },

  {
    to: '/agents',
    labelKey: 'nav.agents',
    icon: Users,
    anyOf: ['agents:read'],
    group: 'nav.groupAnalyse',
  },
  {
    to: '/surveys',
    labelKey: 'nav.surveys',
    salesLabelKey: 'nav.myRatings',
    icon: Star,
    anyOf: ['surveys:read', 'surveys:read:own'],
  },

  {
    to: '/groups',
    labelKey: 'nav.groups',
    icon: MessagesSquare,
    anyOf: ['groups:read'],
    group: 'nav.groupManage',
  },
  {
    to: '/regions',
    labelKey: 'nav.regions',
    icon: MapPin,
    // `regions:read` EMAS, `regions:write`. Bu sahifa — hududlarni
    // BOSHQARISH (qo'shish, nomini o'zgartirish, o'chirish), o'qish
    // emas. `regions:read` savdo xodimida ham bor, chunki unga filtr
    // uchun hudud NOMLARI kerak — lekin boshqaruv sahifasida uning
    // qila oladigan ishi yo'q edi: menyu bandi ochilib, tugmalari
    // ishlamaydigan jadval chiqardi.
    anyOf: ['regions:write'],
    group: 'nav.groupManage',
  },
  {
    to: '/rubric',
    labelKey: 'nav.rubric',
    icon: ListChecks,
    anyOf: ['rubric:read'],
    group: 'nav.groupManage',
  },
  {
    to: '/users',
    labelKey: 'nav.users',
    icon: UserCog,
    anyOf: ['users:read'],
  },
  {
    to: '/settings',
    labelKey: 'nav.settings',
    icon: Settings,
    anyOf: ['settings:read'],
  },
]

const COLLAPSE_KEY = 'zvonki-sidebar-collapsed'

/* ── Shell ───────────────────────────────────────────────── */

export function AppShell() {
  const { t, i18n } = useTranslation()
  const { user, logout, can } = useAuth()
  const { toggle, isDark } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()

  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === '1',
  )
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0')
  }, [collapsed])

  // Sahifa almashganda mobil panel yopiladi
  useEffect(() => setMobileOpen(false), [location.pathname])

  const isHome = location.pathname === '/'

  // /calls/abc → /calls · /calls → / · /settings → /
  const parentPath = (() => {
    const parts = location.pathname.split('/').filter(Boolean)
    return parts.length > 1 ? `/${parts.slice(0, -1).join('/')}` : '/'
  })()
  const isSales = user?.role === 'sales'
  const items = NAV.filter(
    (item) => !item.anyOf || item.anyOf.some((permission) => can(permission)),
  )

  const label = (item: NavItem) =>
    t(isSales && item.salesLabelKey ? item.salesLabelKey : item.labelKey)

  return (
    // h-screen + overflow-hidden → SAHIFA scroll qilmaydi.
    // Faqat ichkaridagi ikkita joy scroll qiladi: menyu va asosiy kontent.
    <div className="flex h-screen overflow-hidden bg-bg">
      {/* ── Mobil qoplama ───────────────────────────────── */}
      {mobileOpen && (
        <button
          aria-label="Yopish"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-30 bg-black/25 backdrop-blur-sm lg:hidden"
        />
      )}

      {/* ── Yon panel ───────────────────────────────────── */}
      <aside
        className={cn(
          'z-40 flex shrink-0 flex-col gap-3 p-3 transition-[width] duration-250 ease-ios',
          collapsed ? 'w-[84px]' : 'w-[248px]',
          // Mobilda — chapdan chiqadigan panel
          'max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:w-[248px] max-lg:bg-bg max-lg:shadow-pop',
          'max-lg:transition-transform max-lg:duration-250 max-lg:ease-ios',
          mobileOpen ? 'max-lg:translate-x-0' : 'max-lg:-translate-x-full',
        )}
      >
        {/* Brend — QOTIB turadi */}
        <div
          className={cn(
            'flex shrink-0 items-center gap-3 rounded-2xl bg-surface py-3.5 shadow-soft',
            collapsed ? 'justify-center px-3' : 'px-4',
          )}
        >
          <img
            src="/brand/bonvi-mark.png"
            alt=""
            width={142}
            height={142}
            className="brand-logo size-8 shrink-0 object-contain"
          />
          {!collapsed && (
            <div className="min-w-0">
              <div className="truncate text-[0.8125rem] font-semibold leading-tight">
                {t('app.name')}
              </div>
              <div className="truncate text-2xs text-muted">{t('app.tagline')}</div>
            </div>
          )}
        </div>

        {/* Menyu — faqat SHU JOY scroll qiladi */}
        <nav className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto">
          {items.map((item, index) => {
            const Icon = item.icon
            const showGroup =
              !collapsed &&
              item.group &&
              (index === 0 || items[index - 1]?.group !== item.group)

            return (
              <div key={item.to}>
                {showGroup && (
                  <div className="px-4 pb-1.5 pt-4 text-2xs font-semibold uppercase tracking-wider text-muted/70">
                    {t(item.group!)}
                  </div>
                )}
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  title={collapsed ? label(item) : undefined}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 rounded-xl py-2.5 text-sm transition-all duration-250 ease-ios',
                      'active:scale-[0.98]',
                      collapsed ? 'justify-center px-0' : 'px-4',
                      isActive
                        ? 'bg-surface font-medium text-accent shadow-soft'
                        : 'text-muted hover:bg-surface/60 hover:text-text',
                    )
                  }
                >
                  <Icon className="size-[18px] shrink-0" />
                  {!collapsed && <span className="truncate">{label(item)}</span>}
                </NavLink>
              </div>
            )
          })}
        </nav>

        {/* Foydalanuvchi — QOTIB turadi, hech qachon siljimaydi */}
        <div
          className={cn(
            'flex shrink-0 items-center gap-2.5 rounded-2xl bg-surface shadow-soft',
            collapsed ? 'flex-col gap-2 p-2.5' : 'p-3',
          )}
        >
          <Avatar name={user?.full_name ?? '?'} size="sm" />
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-medium">{user?.full_name}</div>
              <div className="truncate text-2xs text-muted">
                {t(`roles.${user?.role}`)}
              </div>
            </div>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="size-8 shrink-0"
            title={t('auth.logout')}
            onClick={async () => {
              await logout()
              navigate('/login')
            }}
          >
            <LogOut className="size-4" />
          </Button>
        </div>
      </aside>

      {/* ── Asosiy qism ─────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center gap-2 px-4 lg:px-6">
          {/* Yon panelni yig'ish/ochish */}
          <Button
            variant="ghost"
            size="icon"
            className="rounded-xl max-lg:hidden"
            title={t(collapsed ? 'common.expandMenu' : 'common.collapseMenu')}
            onClick={() => setCollapsed((v) => !v)}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-[18px]" />
            ) : (
              <PanelLeftClose className="size-[18px]" />
            )}
          </Button>

          {/* Mobil menyu tugmasi */}
          <Button
            variant="ghost"
            size="icon"
            className="rounded-xl lg:hidden"
            title={t('common.menu')}
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="size-[18px]" />
          </Button>

          {/* Orqaga — faqat ichki sahifalarda.
              Brauzer tarixiga TAYANMAYDI: yo'lning ota qismini
              hisoblab qaytadi, shuning uchun natija har doim bir xil
              (link to'g'ridan ochilgan bo'lsa ham ishlaydi). */}
          {!isHome && (
            <Button
              variant="ghost"
              size="sm"
              className="animate-scale-in rounded-xl"
              onClick={() => navigate(parentPath)}
            >
              <ArrowLeft className="size-4" />
              <span className="max-sm:hidden">
                {parentPath === '/' ? t('nav.dashboard') : t('common.back')}
              </span>
            </Button>
          )}

          <div className="flex-1" />

          {/* Monitor — yangi tabda ochiladi (TV ekran rejimi) */}
          <Button
            variant="ghost"
            size="icon"
            className="rounded-xl"
            title={t('nav.monitor')}
            onClick={() => window.open('/monitor', '_blank', 'noopener')}
          >
            <Monitor className="size-[18px]" />
          </Button>

          {/* Til */}
          <div className="segment">
            {LANGUAGES.map((lang) => (
              <button
                key={lang.code}
                data-active={i18n.language === lang.code}
                onClick={() => setLanguage(lang.code as LanguageCode)}
                className="segment-item px-2.5 py-1 text-2xs"
                title={lang.label}
              >
                {lang.short}
              </button>
            ))}
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={toggle}
            title={t('common.theme')}
            className="rounded-xl"
          >
            {isDark ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
          </Button>
        </header>

        {/* Faqat shu joy scroll qiladi */}
        <main className="min-h-0 flex-1 overflow-y-auto pb-8">
          {/* Yuklanmagan so'rov haqidagi chiziq — bo'sh ro'yxat bilan
              yiqilgan so'rovni ajratib turadi */}
          <div className="px-4 pt-4 empty:hidden lg:px-6">
            <QueryErrorBanner />
          </div>
          {/* Chegara SAHIFA atrofida: bo'lim yiqilsa menyu va boshqa
              bo'limlar ishlashda qoladi. `key` — yo'l o'zgarganda
              chegara tozalanadi, aks holda bir marta yiqilgan xato
              boshqa bo'limga o'tganda ham ekranda qolib ketardi. */}
          <ErrorBoundary key={location.pathname} scope={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}
