import { describe, expect, it } from 'vitest'

import { clearAccessToken, saveAccessToken } from '../utils/authSession'
import { createAppRouter, createMemoryHistory } from './index'

describe('router authentication guard', () => {
  it('redirects unauthenticated users from chat to login', async () => {
    clearAccessToken()
    const router = createAppRouter(createMemoryHistory())

    await router.push('/chat')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/chat')
  })

  it('protects forum routes with the same authentication guard', async () => {
    clearAccessToken()
    const router = createAppRouter(createMemoryHistory())

    await router.push('/forum/new')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/forum/new')
  })

  it('protects memory settings with the authentication guard', async () => {
    clearAccessToken()
    const router = createAppRouter(createMemoryHistory())

    await router.push('/settings/memory')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/settings/memory')
  })

  it('keeps authenticated users out of guest-only pages', async () => {
    saveAccessToken('jwt')
    const router = createAppRouter(createMemoryHistory())

    await router.push('/login')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('chat')
  })
})
