import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { authApi } from '../api/auth'
import type { LoginRequest, RegisterRequest } from '../types/api'
import { clearAccessToken, getAccessToken, saveAccessToken } from '../utils/authSession'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(getAccessToken())
  const isAuthenticated = computed(() => Boolean(token.value))

  async function login(request: LoginRequest): Promise<void> {
    const response = await authApi.login(request)
    token.value = response.token
    saveAccessToken(response.token)
  }

  async function register(request: RegisterRequest): Promise<void> {
    await authApi.register(request)
  }

  function clearSession(): void {
    token.value = null
    clearAccessToken()
  }

  return { token, isAuthenticated, login, register, clearSession }
})
