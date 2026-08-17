/**
 * Guruhni tahrirlash modali.
 *
 * QOIDA: tahrirlash faqat shu yerda. Sahifaga inline input chiqmaydi.
 *
 * Ikkita narsa ochiq aytiladi:
 *
 *   1. HUDUD — guruhning ishchi yoki yo'qligini aynan shu belgilaydi.
 *      Hududni bo'shatish «unutib qoldirish» emas, ATAYIN amal:
 *      mijozsiz ichki guruh shunday chetga chiqariladi. Shuning uchun
 *      hudud tanlovi ostida oqibat yozilgan.
 *
 *   2. QO'LDA BIRIKTIRISH — bu oynada saqlangan guruh `bound_by="manual"`
 *      bo'ladi va avtomatik biriktirish unga boshqa tegmaydi. Aks
 *      holda admin tuzatgan narsa keyingi aylanishda yana buzilardi —
 *      lekin buning teskari tomoni ham bor: bot endi bu qatorni
 *      yangilamaydi. Admin buni bilib turishi kerak.
 */

import { Bot, Hand, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAgents } from '@/modules/agents/api'
import {
  errorMessage,
  isManual,
  useSaveGroup,
  type TelegramGroup,
} from '@/modules/groups/api'
import { useRegionChoices } from '@/modules/regions/api'
import { cn } from '@/shared/lib/utils'
import { Modal, ModalFields } from '@/shared/ui/Modal'
import { Badge, Button, Label, Select, Switch } from '@/shared/ui/primitives'

export function GroupModal({
  group,
  onClose,
}: {
  group: TelegramGroup | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  // Faol emaslar ham kerak: guruh allaqachon shunday xodimga
  // biriktirilgan bo'lsa, u ro'yxatdan tushib qolmasligi kerak
  const agents = useAgents(true)
  const save = useSaveGroup()

  const [form, setForm] = useState({ agent_id: '', region: '', is_active: true })
  const [error, setError] = useState<string | null>(null)
  /** Hudud taklifdan kelganmi — shundagina "aniqlandi" eslatmasi chiqadi */
  const [regionFromHint, setRegionFromHint] = useState(false)

  // Modal ochilganda formani to'ldiramiz.
  // Hudud bo'sh bo'lsa — taklif oldindan tanlanadi. Bor bo'lsa — tegilmaydi.
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  // Yopilganda kalit tozalanadi — qayta ochilganda forma serverdagi
  // eng so'nggi holatdan to'ldiriladi, eski qiymat qolib ketmaydi
  if (!group && loadedKey !== null) setLoadedKey(null)
  if (group && group.id !== loadedKey) {
    setLoadedKey(group.id)
    setError(null)
    const suggested = group.region ? null : (group.suggested_region ?? null)
    setRegionFromHint(Boolean(suggested))
    setForm({
      agent_id: group.agent_id ?? '',
      region: group.region ?? suggested ?? '',
      is_active: group.is_active,
    })
  }

  /* Hududlar — admin boshqaradigan `GET /regions`.
     Tanlash uchun faqat faol hududlar, lekin guruhda allaqachon
     turgan hudud (faolsizlantirilgan bo'lsa ham) ro'yxatda qoladi. */
  const { names: options } = useRegionChoices(group?.region || form.region || null)

  const willBind = Boolean(form.agent_id && form.region)
  const showSuggestion = regionFromHint && form.region === group?.suggested_region
  // Hududi bor edi, endi bo'shatilyapti — bu ataylab qilinadigan amal
  const clearingRegion = Boolean(group?.region) && !form.region

  const submit = () => {
    if (!group) return
    setError(null)
    save.mutate(
      {
        id: group.id,
        agent_id: form.agent_id || null,
        // ATAYIN `null`: backend «yuborilmagan» dan farqlaydi
        region: form.region || null,
        is_active: form.is_active,
      },
      {
        onSuccess: onClose,
        onError: (e) => setError(errorMessage(e, t('common.error'))),
      },
    )
  }

  return (
    <Modal
      open={group !== null}
      onOpenChange={(open) => !open && onClose()}
      title={group?.title ?? t('groups.edit')}
      description={group ? `${t('groups.chatId')}: ${group.chat_id}` : undefined}
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button disabled={save.isPending} onClick={submit}>
            {save.isPending ? t('settings.saving') : t('common.save')}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {/* Kim boshqaryapti: bot yoki admin */}
        {group && group.bound_by != null && (
          <div className="flex flex-wrap items-center gap-2">
            {isManual(group) ? (
              <>
                <Badge tone="accent">
                  <Hand className="size-3" />
                  {t('groups.tree.manual')}
                </Badge>
                <span className="text-2xs leading-relaxed text-muted">
                  {t('groups.tree.manualHint')}
                </span>
              </>
            ) : (
              <>
                <Badge tone="neutral">
                  <Bot className="size-3" />
                  {t('groups.tree.auto')}
                </Badge>
                <span className="text-2xs leading-relaxed text-muted">
                  {t('groups.tree.autoHint')}
                </span>
              </>
            )}
          </div>
        )}

        <ModalFields>
          <div>
            <Label>{t('groups.agentField')}</Label>
            <Select
              autoFocus
              value={form.agent_id}
              onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
            >
              <option value="">{t('groups.noAgent')}</option>
              {(agents.data ?? []).map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.is_active
                    ? agent.full_name
                    : `${agent.full_name} · ${t('groups.inactive')}`}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <Label>{t('groups.regionField')}</Label>
            <Select
              value={form.region}
              onChange={(e) => {
                // Admin o'zi tanladi — taklif eslatmasi so'nadi
                setRegionFromHint(false)
                setForm({ ...form, region: e.target.value })
              }}
            >
              <option value="">{t('groups.tree.regionless')}</option>
              {options.map((region) => (
                <option key={region} value={region}>
                  {region}
                </option>
              ))}
            </Select>
            {showSuggestion && (
              <p className="animate-scale-in mt-1.5 flex items-start gap-1.5 text-2xs text-accent">
                <Sparkles className="mt-px size-3 shrink-0" />
                {t('groups.regionSuggested')}
              </p>
            )}
          </div>
        </ModalFields>

        {/* Hududni bo'shatish — «keraksiz guruh» aynan shunday belgilanadi */}
        {clearingRegion && (
          <p className="animate-scale-in rounded-xl bg-warn/[0.09] px-4 py-3 text-2xs leading-relaxed text-warn">
            {t('groups.bulk.clearExplain')}
          </p>
        )}

        <div className="flex items-center justify-between rounded-xl bg-surface-2/60 p-3">
          <div className="min-w-0 pr-3">
            <div className="text-sm font-medium">{t('groups.activeLabel')}</div>
            <p className="text-2xs text-muted">{t('groups.activeHint')}</p>
          </div>
          <Switch
            checked={form.is_active}
            label={t('groups.activeLabel')}
            onChange={(next) => setForm({ ...form, is_active: next })}
          />
        </div>

        <p
          className={cn(
            'rounded-xl px-4 py-3 text-2xs leading-relaxed',
            willBind ? 'bg-good/10 text-good' : 'bg-surface-2/60 text-muted',
          )}
        >
          {willBind ? t('groups.bindReady') : t('groups.bindHint')}
        </p>

        {/* Saqlash = qo'lda biriktirish. Oqibati oldindan aytiladi. */}
        <p className="flex items-start gap-2 rounded-xl bg-surface-2/60 px-4 py-3 text-2xs leading-relaxed text-muted">
          <Hand className="mt-px size-3.5 shrink-0" />
          {t('groups.bulk.manualWarning')}
        </p>

        {error && (
          <p className="animate-scale-in rounded-xl bg-bad/10 px-4 py-3 text-xs text-bad">
            {error}
          </p>
        )}
      </div>
    </Modal>
  )
}
