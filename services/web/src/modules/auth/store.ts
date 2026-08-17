import { create } from 'zustand'

import { api, tokenStore } from '@/shared/api/client'

export type Role = 'admin' | 'manager' | 'sales' | 'viewer'

export interface CurrentUser {
  id: string
  email: string
  full_name: string
  role: Role
  agent_id: string | null
  permissions: string[]
}

interface LoginResponse {
  access_token: string
  refresh_token: string
}

interface AuthState {
  user: CurrentUser | null
  status: 'idle' | 'loading' | 'authenticated' | 'anonymous'
  error: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  restore: () => Promise<void>
  can: (permission: string) => boolean
}

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  status: 'idle',
  error: null,

  async login(email, password) {
    set({ status: 'loading', error: null })
    try {
      const tokens = await api.post<LoginResponse>('/auth/login', { email, password })
      tokenStore.set(tokens.access_token, tokens.refresh_token)
      const user = await api.get<CurrentUser>('/auth/me')
      set({ user, status: 'authenticated', error: null })
    } catch (error) {
      tokenStore.clear()
      set({
        user: null,
        status: 'anonymous',
        error: error instanceof Error ? error.message : 'Xatolik',
      })
      throw error
    }
  },

  async logout() {
    try {
      await api.post('/auth/logout')
    } catch {
      /* server javob bermasa ham lokal holatni tozalaymiz */
    }
    tokenStore.clear()
    set({ user: null, status: 'anonymous' })
  },

  async restore() {
    if (!tokenStore.get()) {
      set({ status: 'anonymous' })
      return
    }
    set({ status: 'loading' })
    try {
      const user = await api.get<CurrentUser>('/auth/me')
      set({ user, status: 'authenticated' })
    } catch {
      tokenStore.clear()
      set({ user: null, status: 'anonymous' })
    }
  },

  can(permission) {
    return get().user?.permissions.includes(permission) ?? false
  },
}))
