import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { conversationsApi } from '../api/conversations'
import { forumApi } from '../api/forum'
import { modelsApi } from '../api/models'
import { createAppRouter, createMemoryHistory } from '../router'
import { useChatStore } from '../stores/chat'
import { useForumDraftStore } from '../stores/forumDraft'
import type { ForumDraft } from '../types/api'
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
vi.mock('../api/images', () => ({ imagesApi: { upload: vi.fn(), get: vi.fn() } }))
vi.mock('../api/forum', () => ({
  forumApi: {
    generateDraft: vi.fn(),
    create: vi.fn(),
  },
}))

const generatedDraft: ForumDraft = {
  sourceConversationId: 'conversation-1',
  title: 'Tomato and Egg Stir-Fry',
  content: 'A grounded cooking recommendation.',
  dishName: 'Tomato and Egg Stir-Fry',
  suggestedImageId: 'image-1',
  suggestedImageType: 'USER_UPLOAD',
  modelId: 'STEP_FLASH_3_7',
}

async function mountConversation() {
  saveAccessToken('jwt')
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createAppRouter(createMemoryHistory())
  await router.push('/chat')
  await router.isReady()
  const wrapper = mount(ChatView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  const chatStore = useChatStore()
  await chatStore.selectConversation('conversation-1')
  await flushPromises()
  return { wrapper, router, draftStore: useForumDraftStore() }
}

describe('conversation forum draft flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(conversationsApi.list).mockResolvedValue({
      content: [{
        id: 'conversation-1',
        title: 'Tomato dinner',
        modelId: 'STEP_FLASH_3_7',
        createdAt: '2026-08-08T00:00:00Z',
        updatedAt: '2026-08-08T00:00:00Z',
      }],
      page: 0,
      size: 100,
      totalElements: 1,
      totalPages: 1,
    })
    vi.mocked(conversationsApi.messages).mockResolvedValue({
      content: [
        { id: 1, role: 'USER', content: 'I have eggs.', imageId: 'image-1', createdAt: '2026-08-08T00:00:00Z' },
        { id: 2, role: 'ASSISTANT', content: 'Make a stir-fry.', imageId: null, createdAt: '2026-08-08T00:00:01Z' },
      ],
      page: 0,
      size: 100,
      totalElements: 2,
      totalPages: 1,
    })
    vi.mocked(modelsApi.list).mockResolvedValue([{
      id: 'STEP_FLASH_3_7',
      displayName: 'Step 3.7 Flash',
      supportsText: true,
      supportsTools: true,
      supportsStreaming: true,
      supportsImages: true,
      available: true,
    }])
  })

  it('shows generation state and opens the existing editor without publishing', async () => {
    let resolveDraft!: (draft: ForumDraft) => void
    vi.mocked(forumApi.generateDraft).mockReturnValue(new Promise((resolve) => {
      resolveDraft = resolve
    }))
    const { wrapper, router, draftStore } = await mountConversation()

    wrapper.get<HTMLButtonElement>('.share-post-button').element.click()
    await flushPromises()
    expect(wrapper.get('.share-post-button').text()).toContain('正在生成草稿')
    expect(wrapper.get<HTMLButtonElement>('.share-post-button').element.disabled).toBe(true)

    resolveDraft(generatedDraft)
    await flushPromises()

    expect(forumApi.generateDraft).toHaveBeenCalledWith('conversation-1')
    expect(draftStore.draft).toEqual(generatedDraft)
    expect(router.currentRoute.value.name).toBe('forum-new')
    expect(router.currentRoute.value.query.draft).toBe('generated')
    expect(forumApi.create).not.toHaveBeenCalled()
  })

  it('shows generation failure without navigating or publishing', async () => {
    vi.mocked(forumApi.generateDraft).mockRejectedValue(new Error('model failed'))
    const { wrapper, router } = await mountConversation()

    wrapper.get<HTMLButtonElement>('.share-post-button').element.click()
    await flushPromises()

    expect(wrapper.get('.inline-error').text()).toContain('社区帖子草稿生成失败')
    expect(router.currentRoute.value.path).toBe('/chat')
    expect(forumApi.create).not.toHaveBeenCalled()
  })

  it('does not generate a draft before the conversation has an assistant answer', async () => {
    vi.mocked(conversationsApi.messages).mockResolvedValue({
      content: [
        { id: 1, role: 'USER', content: 'I have eggs.', imageId: null, createdAt: '2026-08-08T00:00:00Z' },
      ],
      page: 0,
      size: 100,
      totalElements: 1,
      totalPages: 1,
    })
    const { wrapper } = await mountConversation()
    const shareButton = wrapper.get<HTMLButtonElement>('.share-post-button')

    expect(shareButton.element.disabled).toBe(true)
    expect(shareButton.attributes('title')).toContain('AI 完整回答')
    await shareButton.trigger('click')
    expect(forumApi.generateDraft).not.toHaveBeenCalled()
  })
})
