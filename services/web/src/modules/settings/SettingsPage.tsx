import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Lock, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuth } from '@/modules/auth/store'
import { AiSection, isAiManagedField } from '@/modules/settings/AiSection'
import {
  isFieldDirty,
  type Integration,
  type SettingField,
  type SettingGroup,
} from '@/modules/settings/types'
import { api } from '@/shared/api/client'
import { Page, PageGrid, PageHeader } from '@/shared/layout/Page'
import { cn } from '@/shared/lib/utils'
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Input,
  Label,
  Select,
  Switch,
} from '@/shared/ui/primitives'

/** AI bo'limi — reyestrdan chiziladigan maydonlar ustiga qo'shimcha
 *  qavat oladi (holat + «Tekshirish» + model takliflari) */
const AI_CATEGORY = 'ai'

/* ── Sahifa ──────────────────────────────────────────────── */

export function SettingsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Record<string, unknown>>({})

  const isAdmin = user?.role === 'admin'

  const groups = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get<SettingGroup[]>('/settings'),
  })

  const health = useQuery({
    queryKey: ['settings', 'health'],
    queryFn: () => api.get<Integration[]>('/settings/health'),
  })

  /** Qaysi blok hozirgina saqlandi — qisqa tasdiq uchun */
  const [savedGroup, setSavedGroup] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: ({ values }: { category: string; values: Record<string, unknown> }) =>
      api.put('/settings', { values }),
    onSuccess: (_data, variables) => {
      // Faqat shu blokning kalitlari tozalanadi — boshqa bloklardagi
      // saqlanmagan o'zgarishlar joyida qoladi
      setDraft((current) => {
        const next = { ...current }
        for (const key of Object.keys(variables.values)) delete next[key]
        return next
      })
      setSavedGroup(variables.category)
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  // Tasdiq belgisi bir necha soniyadan keyin o'chadi
  useEffect(() => {
    if (!savedGroup) return
    const timer = setTimeout(() => setSavedGroup(null), 2500)
    return () => clearTimeout(timer)
  }, [savedGroup])

  return (
    <Page>
      <PageHeader
        title={t('settings.title')}
        subtitle={t('settings.subtitle')}
        actions={
          isAdmin ? null : (
            <span className="inline-flex items-center gap-1.5 text-xs text-muted">
              <Lock className="size-3.5" />
              {t('settings.adminOnly')}
            </span>
          )
        }
      />

      {/* Integratsiyalar holati */}
      <Card>
        <CardHeader title={t('settings.integrations')} />
        <CardBody className="pt-3">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
            {health.data?.map((item) => (
              <div
                key={item.id}
                className="flex items-start gap-2.5 rounded-md border border-border p-3"
              >
                <span
                  className={cn(
                    'mt-0.5 grid size-5 shrink-0 place-items-center rounded-full',
                    item.configured ? 'bg-good/15 text-good' : 'bg-muted/15 text-muted',
                  )}
                >
                  {item.configured ? (
                    <Check className="size-3" />
                  ) : (
                    <X className="size-3" />
                  )}
                </span>
                <div className="min-w-0">
                  <div className="text-xs font-medium">{item.label}</div>
                  <div className="truncate text-2xs text-muted">{item.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      {/* Sozlama guruhlari — har biri mustaqil saqlanadi */}
      <PageGrid>
      {groups.data?.map((group) => {
        const changed = group.fields.filter((field) =>
          isFieldDirty(field, draft[field.key]),
        )
        const dirty = changed.length > 0
        const saving = save.isPending && save.variables?.category === group.category
        const justSaved = savedGroup === group.category

        const submit = () => {
          const values: Record<string, unknown> = {}
          for (const field of changed) values[field.key] = draft[field.key]
          save.mutate({ category: group.category, values })
        }

        const revert = () =>
          setDraft((current) => {
            const next = { ...current }
            for (const field of group.fields) delete next[field.key]
            return next
          })

        const isAi = group.category === AI_CATEGORY

        /* AI blokidagi maydonlar (provayder, model, kalitlar) `AiSection`
           ichida chiziladi — bu yerda TAKRORLANMASIN. Qolganlari
           (masalan «Minimal davomiylik») odatdagidek ko'rinadi. */
        const plainFields = isAi
          ? group.fields.filter((field) => !isAiManagedField(field.key))
          : group.fields

        return (
          <Card key={group.category}>
            <CardHeader title={group.label} />
            <CardBody className="space-y-4 pt-3">
              {isAi && (
                <AiSection
                  group={group}
                  draft={draft}
                  dirty={dirty}
                  canEdit={isAdmin}
                  onChange={(key, value) =>
                    setDraft((d) => ({ ...d, [key]: value }))
                  }
                />
              )}

              {plainFields.map((field) => (
                <Field
                  key={field.key}
                  field={field}
                  disabled={!isAdmin}
                  draftValue={draft[field.key]}
                  dirty={isFieldDirty(field, draft[field.key])}
                  onChange={(value) => setDraft((d) => ({ ...d, [field.key]: value }))}
                />
              ))}

              {isAdmin && (
                <div className="flex items-center gap-2 border-t border-border/60 pt-3.5">
                  <span
                    className={cn(
                      'text-2xs transition-opacity duration-250 ease-ios',
                      justSaved
                        ? 'text-good opacity-100'
                        : dirty
                          ? 'text-muted opacity-100'
                          : 'opacity-0',
                    )}
                  >
                    {justSaved
                      ? t('settings.saved')
                      : t('settings.pendingCount', { count: changed.length })}
                  </span>

                  <div className="ml-auto flex items-center gap-2">
                    {dirty && !saving && (
                      <Button variant="ghost" size="sm" onClick={revert}>
                        {t('settings.revert')}
                      </Button>
                    )}
                    <Button size="sm" disabled={!dirty || saving} onClick={submit}>
                      {saving ? t('settings.saving') : t('settings.save')}
                    </Button>
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        )
      })}
      </PageGrid>
    </Page>
  )
}

/* ── Bitta maydon ────────────────────────────────────────── */

function Field({
  field,
  disabled,
  draftValue,
  dirty,
  onChange,
}: {
  field: SettingField
  disabled: boolean
  draftValue: unknown
  dirty: boolean
  onChange: (value: unknown) => void
}) {
  const { t } = useTranslation()
  const current = draftValue !== undefined ? draftValue : field.value

  return (
    <div className="grid gap-1.5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] sm:items-start sm:gap-4">
      <div className="pt-1.5">
        <Label className="mb-0">
          {field.label}
          {/* Saqlanmagan maydon ko'zga tashlanib tursin */}
          {dirty && (
            <span
              className="ml-1.5 inline-block size-1.5 rounded-full bg-accent align-middle"
              title={t('settings.unsaved')}
            />
          )}
        </Label>
        {field.hint && <p className="mt-0.5 text-2xs text-muted">{field.hint}</p>}
        {field.source === 'env' && (
          <span className="mt-1 inline-block rounded bg-surface-2 px-1.5 py-0.5 font-mono text-2xs text-muted">
            .env
          </span>
        )}
      </div>

      <div>
        {field.type === 'boolean' ? (
          <Switch
            checked={Boolean(current)}
            disabled={disabled}
            label={field.label}
            onChange={(next) => onChange(next)}
          />
        ) : field.type === 'select' ? (
          <Select
            disabled={disabled}
            value={String(current ?? '')}
            onChange={(e) => onChange(e.target.value)}
          >
            {field.options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        ) : (
          <>
            <Input
              type={field.type === 'secret' ? 'password' : field.type === 'number' ? 'number' : 'text'}
              disabled={disabled}
              autoComplete={field.type === 'secret' ? 'new-password' : 'off'}
              value={
                field.type === 'secret'
                  ? (draftValue as string) ?? ''
                  : String(current ?? '')
              }
              placeholder={
                field.type === 'secret' && field.is_set ? '••••••••' : ''
              }
              onChange={(e) =>
                onChange(
                  field.type === 'number' ? Number(e.target.value) : e.target.value,
                )
              }
            />

            {field.type === 'secret' && field.is_set && (
              <p className="mt-1 text-2xs text-muted">{t('settings.secretHint')}</p>
            )}
          </>
        )}
      </div>
    </div>
  )
}
