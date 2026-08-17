import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, ShieldCheck, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, ApiError } from '@/shared/api/client'
import { Page, PageHeader } from '@/shared/layout/Page'
import { cn } from '@/shared/lib/utils'
import { Avatar } from '@/shared/ui/dataviz'
import { Modal, ModalFields } from '@/shared/ui/Modal'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Input,
  Label,
  Select,
  Skeleton,
  Switch,
} from '@/shared/ui/primitives'

type Role = 'admin' | 'manager' | 'sales' | 'viewer'

interface UserRow {
  id: string
  email: string
  full_name: string
  role: Role
  is_active: boolean
  agent_id: string | null
  agent_name: string | null
  created_at: string
}

interface AgentOption {
  id: string
  full_name: string
  region: string
}

const ROLE_TONE: Record<Role, 'accent' | 'good' | 'warn' | 'neutral'> = {
  admin: 'accent',
  manager: 'good',
  sales: 'warn',
  viewer: 'neutral',
}

export function UsersPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  // null = yopiq · 'new' = yaratish · UserRow = tahrirlash
  const [editing, setEditing] = useState<UserRow | 'new' | null>(null)

  const users = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get<UserRow[]>('/users'),
  })

  const agents = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.get<AgentOption[]>('/agents'),
  })

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      api.patch(`/users/${id}`, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  return (
    <Page>
      <PageHeader
        title={t('nav.users')}
        subtitle={t('users.subtitle')}
        actions={
          <Button onClick={() => setEditing('new')}>
            <UserPlus className="size-4" />
            {t('users.create')}
          </Button>
        }
      />

      <Card>
        <CardHeader title={t('users.list')} />
        <CardBody className="grid gap-1.5 pt-3 2xl:grid-cols-2">
          {users.isLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))
          ) : !users.data?.length ? (
            <EmptyState message={t('table.empty')} />
          ) : (
            users.data.map((user) => (
              <div
                key={user.id}
                className={cn(
                  'flex items-center gap-3 rounded-xl bg-surface-2/60 p-3 transition-opacity',
                  !user.is_active && 'opacity-50',
                )}
              >
                <Avatar name={user.full_name} size="sm" />

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {user.full_name}
                    </span>
                    <Badge tone={ROLE_TONE[user.role]}>{t(`roles.${user.role}`)}</Badge>
                  </div>
                  <div className="truncate text-2xs text-muted">
                    {user.email}
                    {user.agent_name && ` · ${user.agent_name}`}
                  </div>
                </div>

                <Button
                  variant="ghost"
                  size="icon"
                  className="size-8 shrink-0"
                  title={t('common.edit')}
                  onClick={() => setEditing(user)}
                >
                  <Pencil className="size-3.5" />
                </Button>

                <Switch
                  checked={user.is_active}
                  label={user.full_name}
                  onChange={(next) =>
                    toggleActive.mutate({ id: user.id, is_active: next })
                  }
                />
              </div>
            ))
          )}
        </CardBody>
      </Card>

      {/* Yaratish / tahrirlash — FAQAT modal oynada */}
      <UserModal
        target={editing}
        agents={agents.data ?? []}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          queryClient.invalidateQueries({ queryKey: ['users'] })
        }}
      />
    </Page>
  )
}

/* ── Yaratish / tahrirlash modali ────────────────────────── */

function UserModal({
  target,
  agents,
  onClose,
  onSaved,
}: {
  target: UserRow | 'new' | null
  agents: AgentOption[]
  onClose: () => void
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const isNew = target === 'new'
  const existing = target && target !== 'new' ? target : null

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    role: 'manager' as Role,
    agent_id: '',
  })
  const [error, setError] = useState<string | null>(null)

  // Modal ochilganda formani mos ma'lumot bilan to'ldiramiz
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  const key = isNew ? 'new' : (existing?.id ?? null)
  if (key && key !== loadedKey) {
    setLoadedKey(key)
    setError(null)
    setForm({
      full_name: existing?.full_name ?? '',
      email: existing?.email ?? '',
      password: '',
      role: existing?.role ?? 'manager',
      agent_id: existing?.agent_id ?? '',
    })
  }

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        full_name: form.full_name,
        role: form.role,
        agent_id: form.role === 'sales' ? form.agent_id || null : null,
      }
      if (form.password) body.password = form.password
      if (isNew) {
        body.email = form.email
        return api.post('/users', body)
      }
      return api.patch(`/users/${existing!.id}`, body)
    },
    onSuccess: onSaved,
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Xatolik'),
  })

  const isSales = form.role === 'sales'
  const valid =
    form.full_name.trim().length >= 2 &&
    (!isNew || form.email.includes('@')) &&
    (!isNew || form.password.length >= 8) &&
    (form.password.length === 0 || form.password.length >= 8) &&
    (!isSales || Boolean(form.agent_id))

  return (
    <Modal
      open={target !== null}
      onOpenChange={(open) => !open && onClose()}
      title={isNew ? t('users.create') : t('users.edit')}
      description={existing?.email}
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? t('settings.saving') : t('common.save')}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <ModalFields>
          <div>
            <Label>{t('users.fullName')}</Label>
            <Input
              autoFocus
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
          </div>

          <div>
            <Label>{t('auth.email')}</Label>
            <Input
              type="email"
              disabled={!isNew}
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
            {!isNew && (
              <p className="mt-1 text-2xs text-muted">{t('users.emailLocked')}</p>
            )}
          </div>

          <div>
            <Label>{t('auth.password')}</Label>
            <Input
              type="password"
              placeholder={isNew ? t('users.passwordHint') : t('users.passwordKeep')}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </div>

          <div>
            <Label>{t('users.role')}</Label>
            <Select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
            >
              <option value="admin">{t('roles.admin')}</option>
              <option value="manager">{t('roles.manager')}</option>
              <option value="sales">{t('roles.sales')}</option>
              <option value="viewer">{t('roles.viewer')}</option>
            </Select>
          </div>
        </ModalFields>

        {/* SALES roli albatta xodimga bog'lanadi */}
        {isSales && (
          <div className="animate-scale-in">
            <Label>{t('users.linkAgent')}</Label>
            <Select
              value={form.agent_id}
              onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
            >
              <option value="">—</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.full_name} · {agent.region}
                </option>
              ))}
            </Select>
            <p className="mt-1.5 flex items-start gap-1.5 text-2xs text-muted">
              <ShieldCheck className="mt-px size-3 shrink-0" />
              {t('users.linkAgentHint')}
            </p>
          </div>
        )}

        {error && (
          <p className="animate-scale-in rounded-xl bg-bad/10 px-4 py-3 text-xs text-bad">
            {error}
          </p>
        )}
      </div>
    </Modal>
  )
}
