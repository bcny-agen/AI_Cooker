import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authApi } from '../api/auth'
import { getAccessToken } from '../utils/authSession'
import { useAuthStore } from './auth'

vi.mock('../api/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
  },
}))

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('persists a login token and restores it in a new store', async () => {
    vi.mocked(authApi.login).mockResolvedValue({ token: 'jwt-value', expiresIn: 3600 })
    const store = useAuthStore()

    await store.login({ username: 'cook', password: 'password123' })

    expect(store.isAuthenticated).toBe(true)
    expect(getAccessToken()).toBe('jwt-value')

    setActivePinia(createPinia())
    expect(useAuthStore().token).toBe('jwt-value')
  })

  it('clears the persisted session on logout', () => {
    localStorage.setItem('ai-cooker.access-token', 'old-token')
    setActivePinia(createPinia())
    const store = useAuthStore()

    store.clearSession()

    expect(store.token).toBeNull()
    expect(getAccessToken()).toBeNull()
  })
})
