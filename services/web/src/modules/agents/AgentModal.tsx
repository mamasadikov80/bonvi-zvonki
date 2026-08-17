import { AlertTriangle, Info, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  boundGroupCount,
  useAgent,
  useDeleteAvatar,
  useSaveAgent,
  useUploadAvatar,
  type Agent,
} from '@/modules/agents/api'
import { useRegionChoices } from '@/modules/regions/api'
import { ApiError } from '@/shared/api/client'
import { cn } from '@/shared/lib/utils'
import { mediaUrl } from '@/shared/ui/dataviz'
import { Modal, ModalFields } from '@/shared/ui/Modal'
import { Button, Input, Label, Select, Switch } from '@/shared/ui/primitives'

/** Yuklanadigan rasm chegaralari — backenddagi qiymatlar bilan bir xil */
const MAX_AVATAR_BYTES = 5 * 1024 * 1024
const ACCEPT = 'image/jpeg,image/png,image/webp,image/gif'


/** Avatar ranglari — kartochkalarda bir-biridan ajralib tursin */
const COLORS = [
  '#6366f1', '#8b5cf6', '#a855f7', '#d946ef', '#ec4899', '#f43f5e',
  '#ef4444', '#f59e0b', '#eab308', '#22c55e', '#10b981', '#14b8a6',
  '#06b6d4', '#0ea5e9', '#7c3aed',
]

export function AgentModal({
  target,
  onClose,
  onSaved,
}: {
  target: Agent | 'new' | null
  onClose: () => void
  /** Saqlangandan keyingi javob — `freed_groups` shu yerdan o'qiladi */
  onSaved?: (agent: Agent) => void
}) {
  const { t } = useTranslation()
  const isNew = target === 'new'
  const existing = target && target !== 'new' ? target : null

  const [form, setForm] = useState({
    full_name: '',
    region: '',
    phone: '',
    external_id: '',
    hired_at: '',
    color: COLORS[0],
    is_active: true,
  })
  const [error, setError] = useState<string | null>(null)

  /* ── Profil rasmi ───────────────────────────────────────
     Yangi xodimda hali id yo'q, shuning uchun fayl saqlanib
     turadi va xodim yaratilgandan keyin yuklanadi. */
  const fileInput = useRef<HTMLInputElement>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [removeAvatar, setRemoveAvatar] = useState(false)

  // Modal ochilganda formani to'ldiramiz
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  const key = isNew ? 'new' : (existing?.id ?? null)
  if (key && key !== loadedKey) {
    setLoadedKey(key)
    setError(null)
    setPendingFile(null)
    setPreview(null)
    setRemoveAvatar(false)
    setForm({
      full_name: existing?.full_name ?? '',
      region: existing?.region ?? '',
      phone: existing?.phone ?? '',
      external_id: existing?.external_id ?? '',
      hired_at: existing?.hired_at ?? '',
      color: existing?.color ?? COLORS[Math.floor(Math.random() * COLORS.length)],
      is_active: existing?.is_active ?? true,
    })
  }

  // Ko'rib turgan havolani xotirada qoldirmaymiz
  useEffect(() => {
    if (!pendingFile) return
    const url = URL.createObjectURL(pendingFile)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [pendingFile])

  const pickFile = (file: File | null) => {
    if (!file) return
    if (!ACCEPT.split(',').includes(file.type)) {
      setError(t('agents.avatarType'))
      return
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setError(t('agents.avatarSize'))
      return
    }
    setError(null)
    setRemoveAvatar(false)
    setPendingFile(file)
  }

  /* Hudud ro'yxati — admin boshqaradigan `GET /regions`.
     Tanlash uchun faqat FAOL hududlar chiqadi, lekin xodimga
     allaqachon biriktirilgan hudud faolsizlantirilgan bo'lsa ham
     ro'yxatda qoladi — aks holda tahrirlashda qiymat yo'qolardi. */
  const { names: regions } = useRegionChoices(existing?.region)

  const save = useSaveAgent()
  const upload = useUploadAvatar()
  const dropAvatar = useDeleteAvatar()

  /* ── Faolsizlantirish oqibati ─────────────────────────────
     Faol xodim «faol emas»ga o'tkazilsa, backend uning Telegram
     guruhlarini AVTOMATIK bo'shatadi. Buni saqlashdan OLDIN
     aytish kerak — keyin aytish kechikkan xabar bo'ladi.

     Guruh soni ro'yxatdan ham keladi, lekin u eskirgan bo'lishi
     mumkin (boshqa sahifada biriktirilgan bo'lsa), shuning uchun
     aynan shu paytda yangisi so'raladi. So'rov ketguncha ro'yxatdagi
     qiymat ko'rsatiladi — ogohlantirish kechikib chiqmasin. */
  const willDeactivate = Boolean(existing && existing.is_active && !form.is_active)
  const fresh = useAgent(willDeactivate ? existing?.id : undefined)
  const boundGroups = boundGroupCount(fresh.data ?? existing)

  const currentAvatar = removeAvatar ? null : (preview ?? existing?.avatar_url ?? null)
  const busy = save.isPending || upload.isPending || dropAvatar.isPending

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : 'Xatolik')

  const submit = () => {
    setError(null)
    save.mutate(
      {
        id: existing?.id,
        full_name: form.full_name.trim(),
        region: form.region,
        phone: form.phone.trim() || null,
        external_id: form.external_id.trim() || null,
        hired_at: form.hired_at || null,
        color: form.color,
        ...(isNew ? {} : { is_active: form.is_active }),
      },
      {
        // Xodim saqlangandan keyin rasm ustida ish ko'ramiz
        onSuccess: async (agent) => {
          try {
            if (pendingFile) {
              await upload.mutateAsync({ agentId: agent.id, file: pendingFile })
            } else if (removeAvatar && existing?.avatar_url) {
              await dropAvatar.mutateAsync(agent.id)
            }
          } catch (e) {
            fail(e)
            return
          }
          // `freed_groups` faqat shu javobda bor — chaqiruvchi uni
          // ko'rsatishi uchun uzatamiz
          onSaved?.(agent)
          onClose()
        },
        onError: fail,
      },
    )
  }

  const valid = form.full_name.trim().length >= 2 && form.region.length > 1

  return (
    <Modal
      open={target !== null}
      onOpenChange={(open) => !open && onClose()}
      title={isNew ? t('agents.create') : t('agents.edit')}
      description={existing?.full_name}
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!valid || busy} onClick={submit}>
            {busy
              ? t('settings.saving')
              : willDeactivate && boundGroups > 0
                ? // Tugma o'z oqibatini aytadi — «Saqlash» bu yerda juda yumshoq
                  t('agents.deactivateAction', { count: boundGroups })
                : t('common.save')}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {/* Profil rasmi */}
        <div className="flex items-center gap-4 rounded-2xl bg-surface-2/60 p-3.5">
          {currentAvatar ? (
            <img
              src={preview ?? mediaUrl(currentAvatar)}
              alt=""
              className="size-16 shrink-0 rounded-full object-cover shadow-soft"
            />
          ) : (
            <div
              className="grid size-16 shrink-0 place-items-center rounded-full text-lg font-semibold text-white shadow-soft"
              style={{ background: form.color }}
            >
              {form.full_name
                .trim()
                .split(/\s+/)
                .slice(0, 2)
                .map((word) => word[0]?.toUpperCase() ?? '')
                .join('') || '—'}
            </div>
          )}

          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium">{t('agents.avatar')}</div>
            <p className="mt-0.5 text-2xs text-muted">{t('agents.avatarHint')}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => fileInput.current?.click()}
              >
                <Upload className="size-3.5" />
                {currentAvatar ? t('agents.avatarReplace') : t('agents.avatarUpload')}
              </Button>
              {currentAvatar && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setPendingFile(null)
                    setPreview(null)
                    setRemoveAvatar(true)
                  }}
                >
                  <Trash2 className="size-3.5" />
                  {t('common.delete')}
                </Button>
              )}
            </div>
          </div>

          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              pickFile(e.target.files?.[0] ?? null)
              e.target.value = ''
            }}
          />
        </div>

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
            <Label>{t('filters.region')}</Label>
            <Select
              value={form.region}
              onChange={(e) => setForm({ ...form, region: e.target.value })}
            >
              {/* Ro'yxat backenddan kelguncha maydon bo'sh turadi —
                  tasodifan noto'g'ri hudud saqlanib qolmasin */}
              <option value="" disabled>
                {t('filters.selectRegion')}
              </option>
              {regions.map((region) => (
                <option key={region} value={region}>
                  {region}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <Label>{t('agents.phone')}</Label>
            <Input
              placeholder="+998 90 123 45 67"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </div>

          <div>
            <Label>{t('agents.hiredAt')}</Label>
            <Input
              type="date"
              value={form.hired_at}
              onChange={(e) => setForm({ ...form, hired_at: e.target.value })}
            />
          </div>
        </ModalFields>

        {/* MoyZvonki bog'lanishi */}
        <div>
          <Label>{t('agents.externalId')}</Label>
          <Input
            className="font-mono"
            placeholder={t('agents.externalIdPlaceholder')}
            value={form.external_id}
            onChange={(e) => setForm({ ...form, external_id: e.target.value })}
          />
          <p className="mt-1.5 flex items-start gap-1.5 text-2xs text-muted">
            <Info className="mt-px size-3 shrink-0" />
            {t('agents.externalIdHint')}
          </p>
        </div>

        {/* Rang tanlash */}
        <div>
          <Label>{t('agents.color')}</Label>
          <div className="flex flex-wrap gap-2">
            {COLORS.map((color) => (
              <button
                key={color}
                type="button"
                onClick={() => setForm({ ...form, color })}
                style={{ background: color }}
                aria-label={color}
                className={cn(
                  'size-7 rounded-full transition-all duration-250 ease-ios',
                  'active:scale-90',
                  form.color === color
                    ? 'ring-2 ring-accent ring-offset-2 ring-offset-surface'
                    : 'hover:scale-110',
                )}
              />
            ))}
          </div>
        </div>

        {/* Faollik — faqat tahrirlashda */}
        {!isNew && (
          <div className="space-y-2">
            <div className="flex items-center justify-between rounded-xl bg-surface-2/60 p-3">
              <div>
                <div className="text-sm font-medium">{t('agents.active')}</div>
                <p className="text-2xs text-muted">{t('agents.activeHint')}</p>
              </div>
              <Switch
                checked={form.is_active}
                label={t('agents.active')}
                onChange={(next) => setForm({ ...form, is_active: next })}
              />
            </div>

            {/* Guruhi bo'lmagan xodimda ogohlantirish CHIQMAYDI —
                bo'sh ogohlantirish haqiqiysining qadrini tushiradi */}
            {willDeactivate && boundGroups > 0 && (
              <div className="animate-scale-in rounded-xl bg-warn/[0.08] p-3.5 ring-1 ring-warn/25">
                <div className="flex items-start gap-2.5">
                  <AlertTriangle className="mt-px size-4 shrink-0 text-warn" />
                  <div className="min-w-0 space-y-1.5">
                    <p className="text-xs font-semibold text-warn">
                      {t('agents.deactivateTitle', { count: boundGroups })}
                    </p>
                    <p className="text-2xs leading-relaxed text-text">
                      {t('agents.deactivateGroups', {
                        name: existing?.full_name ?? '',
                        count: boundGroups,
                      })}
                    </p>
                    <p className="text-2xs leading-relaxed text-muted">
                      {t('agents.deactivateKept')}
                    </p>
                  </div>
                </div>
              </div>
            )}
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
