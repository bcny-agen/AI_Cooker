import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { conversationsApi } from '../api/conversations'
import { imagesApi } from '../api/images'
import { modelsApi } from '../api/models'
import { createAppRouter, createMemoryHistory } from '../router'
import { saveAccessToken } from '../utils/authSession'
import ChatView from './ChatView.vue'

vi.mock('../api/chat', () => ({ chatApi: { send: vi.fn(), stream: vi.fn() } }))
vi.mock('../api/conversations', () => ({
  conversationsApi: {
    list: vi.fn(),
    messages: vi.fn(),
    get: vi.fn(),
    changeModel: vi.fn(),
    rename: vi.fn(),
    delete: vi.fn(),
  },
}))
vi.mock('../api/models', () => ({ modelsApi: { list: vi.fn() } }))
vi.mock('../api/images', () => ({
  imagesApi: {
    upload: vi.fn(),
    get: vi.fn(),
  },
}))

const emptyPage = { content: [], page: 0, size: 100, totalElements: 0, totalPages: 0 }

describe('historical image previews', () => {
  beforeEach(() => {
    saveAccessToken('jwt')
    vi.mocked(conversationsApi.list).mockResolvedValue(emptyPage)
    vi.mocked(conversationsApi.get).mockResolvedValue({
      id: 'conversation-1',
      title: 'Image conversation',
      modelId: 'STEP_FLASH_3_7',
      createdAt: '2026-08-01T00:00:00Z',
      updatedAt: '2026-08-01T00:00:00Z',
    })
    vi.mocked(modelsApi.list).mockResolvedValue([
      { id: 'STEP_FLASH_3_7', displayName: 'Step 3.7 Flash', supportsText: true, supportsTools: true, supportsStreaming: true, supportsImages: true, available: true },
      { id: 'DEEPSEEK_V4_PRO', displayName: 'DeepSeek V4 Pro', supportsText: true, supportsTools: true, supportsStreaming: true, supportsImages: false, available: true },
    ])
    vi.mocked(conversationsApi.messages).mockResolvedValue({
      content: [{
        id: 1,
        role: 'USER',
        content: '<script>unsafe()</script>\nSecond line',
        imageId: 'owned-image',
        createdAt: '2026-08-01T00:00:00Z',
      }],
      page: 0,
      size: 100,
      totalElements: 1,
      totalPages: 1,
    })
  })

  it('retrieves a fresh preview URL from Java and renders message content as text', async () => {
    vi.mocked(imagesApi.get).mockResolvedValue({
      imageId: 'owned-image',
      url: 'https://signed.example/fresh',
      originalFilename: 'food.jpg',
      contentType: 'image/jpeg',
      size: 10,
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createAppRouter(createMemoryHistory())
    await router.push('/chat')
    await router.isReady()
    const wrapper = mount(ChatView, { global: { plugins: [pinia, router] } })
    const store = (await import('../stores/chat')).useChatStore()

    await store.selectConversation('conversation-1')
    await flushPromises()

    expect(imagesApi.get).toHaveBeenCalledWith('owned-image')
    expect(wrapper.get('.message-image').attributes('src')).toBe('https://signed.example/fresh')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.get('.message-content').text()).toContain('<script>unsafe()</script>')
  })

  it('keeps the text conversation usable when the image object is missing', async () => {
    vi.mocked(imagesApi.get).mockRejectedValue(new Error('missing'))
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createAppRouter(createMemoryHistory())
    await router.push('/chat')
    await router.isReady()
    const wrapper = mount(ChatView, { global: { plugins: [pinia, router] } })
    const store = (await import('../stores/chat')).useChatStore()

    await store.selectConversation('conversation-1')
    await flushPromises()

    expect(wrapper.get('.message-image-placeholder').text()).toContain('暂不可用')
    expect(wrapper.get('.message-content').text()).toContain('Second line')
  })

  it('shows the model selector and disables images for DeepSeek', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createAppRouter(createMemoryHistory())
    await router.push('/chat')
    await router.isReady()
    const wrapper = mount(ChatView, { global: { plugins: [pinia, router] } })
    await flushPromises()

    const selector = wrapper.get<HTMLSelectElement>('.model-selector select')
    expect(selector.findAll('option')).toHaveLength(2)
    await selector.setValue('DEEPSEEK_V4_PRO')
    await flushPromises()

    expect(wrapper.get('.model-notice').text()).toContain('仅支持文字对话')
    expect(wrapper.get<HTMLButtonElement>('.composer__attach').element.disabled).toBe(true)
  })
})
