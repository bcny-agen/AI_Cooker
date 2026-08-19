import axios from 'axios'

import { getAccessToken, notifyUnauthorized } from '../utils/authSession'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080'

export const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120_000,
  headers: {
    Accept: 'application/json',
  },
})

http.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      const path = error.config?.url ?? ''
      if (!path.startsWith('/api/auth/')) {
        notifyUnauthorized()
      }
    }
    return Promise.reject(error)
  },
)
