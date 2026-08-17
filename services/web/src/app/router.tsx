import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { LoginPage } from '@/modules/auth/LoginPage'
import { AgentProfilePage } from '@/modules/agents/AgentProfilePage'
import { AgentsPage } from '@/modules/agents/AgentsPage'
import { useAuth } from '@/modules/auth/store'
import { CallDetailPage } from '@/modules/calls/CallDetailPage'
import { CallsPage } from '@/modules/calls/CallsPage'
import { DashboardPage } from '@/modules/dashboard/DashboardPage'
import { MonitorPage } from '@/modules/dashboard/MonitorPage'
import { GroupsPage } from '@/modules/groups/GroupsPage'
import { RegionsPage } from '@/modules/regions/RegionsPage'
import { RubricPage } from '@/modules/rubric/RubricPage'
import { SettingsPage } from '@/modules/settings/SettingsPage'
import { SurveyWebAppPage } from '@/modules/survey-webapp/SurveyWebAppPage'
import { SurveysPage } from '@/modules/surveys/SurveysPage'
import { UsersPage } from '@/modules/users/UsersPage'
import { AppShell } from '@/shared/layout/AppShell'
import { Skeleton } from '@/shared/ui/primitives'

function FullPageLoader() {
  return (
    <div className="grid min-h-screen place-items-center bg-bg">
      <Skeleton className="size-10 rounded-2xl" />
    </div>
  )
}

function Protected({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'idle' || status === 'loading') return <FullPageLoader />
  if (status === 'anonymous') {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return <>{children}</>
}

/** Ruxsatlardan kamida bittasi bo'lishi kerak */
function Gate({
  anyOf,
  children,
}: {
  anyOf: string[]
  children: React.ReactNode
}) {
  const { can } = useAuth()
  if (!anyOf.some((permission) => can(permission))) return <Navigate to="/" replace />
  return <>{children}</>
}

export function AppRouter() {
  const { status, restore } = useAuth()

  useEffect(() => {
    if (status === 'idle') void restore()
  }, [status, restore])

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* So'rovnoma (Telegram Mini App) — do'kondor uchun OCHIQ sahifa.
          `Protected` ham, `Gate` ham yo'q va bo'lmasligi kerak: javob
          beruvchi tizimga hech qachon kirmaydi, uni `/login` ga otib
          yuborish so'rovnomani butunlay o'ldiradi. Autentifikatsiya
          o'rniga — `Telegram.WebApp.initData` imzosi, uni backend
          tekshiradi. `AppShell` ham yo'q: sidebar va menyu begona. */}
      <Route path="/s" element={<SurveyWebAppPage />} />

      {/* Monitor — AppShell'siz, to'liq ekran */}
      <Route
        path="/monitor"
        element={
          <Protected>
            <MonitorPage />
          </Protected>
        }
      />

      <Route
        element={
          <Protected>
            <AppShell />
          </Protected>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route
          path="calls"
          element={
            <Gate anyOf={['calls:read', 'calls:read:own']}>
              <CallsPage />
            </Gate>
          }
        />
        <Route
          path="calls/:callId"
          element={
            <Gate anyOf={['calls:read', 'calls:read:own']}>
              <CallDetailPage />
            </Gate>
          }
        />

        <Route
          path="agents"
          element={
            <Gate anyOf={['agents:read']}>
              <AgentsPage />
            </Gate>
          }
        />
        <Route
          path="agents/:agentId"
          element={
            <Gate anyOf={['agents:read', 'analytics:read:own']}>
              <AgentProfilePage />
            </Gate>
          }
        />
        <Route
          path="surveys"
          element={
            <Gate anyOf={['surveys:read', 'surveys:read:own']}>
              <SurveysPage />
            </Gate>
          }
        />
        <Route
          path="rubric"
          element={
            <Gate anyOf={['rubric:read']}>
              <RubricPage />
            </Gate>
          }
        />
        <Route
          path="groups"
          element={
            <Gate anyOf={['groups:read']}>
              <GroupsPage />
            </Gate>
          }
        />
        {/* Boshqaruv sahifasi — `regions:write`. Faqat menyuni yashirish
            yetarli emas: manzilni qo'lda yozganlar sahifani ochib
            olardi. Ruxsati yo'q bo'lsa `Gate` bosh sahifaga qaytaradi. */}
        <Route
          path="regions"
          element={
            <Gate anyOf={['regions:write']}>
              <RegionsPage />
            </Gate>
          }
        />
        <Route
          path="users"
          element={
            <Gate anyOf={['users:read']}>
              <UsersPage />
            </Gate>
          }
        />
        <Route
          path="settings"
          element={
            <Gate anyOf={['settings:read']}>
              <SettingsPage />
            </Gate>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
