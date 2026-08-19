import {
  AxiosError,
  AxiosHeaders,
  type AxiosAdapter,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { clearAccessToken, getAccessToken, saveAccessToken, setUnauthorizedHandler } from '../utils/authSession'
import { http } from './http'

const originalAdapter = http.defaults.adapter

function response(config: InternalAxiosRequestConfig, status = 200): AxiosResponse {
  return {
    data: {},
    status,
    statusText: status === 200 ? 'OK' : 'Unauthorized',
    headers: new AxiosHeaders(),
    config,
  }
}

afterEach(() => {
  http.defaults.adapter = originalAdapter
  clearAccessToken()
})

describe('HTTP authentication', () => {
  it('adds the persisted JWT to Java API requests', async () => {
    let captured: InternalAxiosRequestConfig | undefined
    const adapter: AxiosAdapter = async (config) => {
      captured = config
      return response(config)
    }
    http.defaults.adapter = adapter
    saveAccessToken('signed-jwt')

    await http.get('/api/conversations')

    expect(captured?.headers.get('Authorization')).toBe('Bearer signed-jwt')
  })

  it('clears the session and notifies the app after a protected 401', async () => {
    const unauthorized = vi.fn()
    setUnauthorizedHandler(unauthorized)
    saveAccessToken('expired-jwt')
    http.defaults.adapter = async (config) => {
      const rejected = response(config, 401)
      throw new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, rejected)
    }

    await expect(http.get('/api/conversations')).rejects.toBeInstanceOf(AxiosError)

    expect(getAccessToken()).toBeNull()
    expect(unauthorized).toHaveBeenCalledOnce()
  })

  it('does not clear unrelated state for a failed login request', async () => {
    const unauthorized = vi.fn()
    setUnauthorizedHandler(unauthorized)
    saveAccessToken('existing-jwt')
    http.defaults.adapter = async (config) => {
      const rejected = response(config, 401)
      throw new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, rejected)
    }

    await expect(http.post('/api/auth/login', {})).rejects.toBeInstanceOf(AxiosError)

    expect(getAccessToken()).toBe('existing-jwt')
    expect(unauthorized).not.toHaveBeenCalled()
  })
})
