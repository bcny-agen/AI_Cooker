import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { chatApi } from '../api/chat'
import { conversationsApi } from '../api/conversations'
import { modelsApi } from '../api/models'
import type { ChatMessage, ChatStreamEvent, Conversation, ModelInfo, PageResponse } from '../types/api'
import { useChatStore } from './chat'

vi.mock('../api/chat', () => ({ chatApi: { send: vi.fn(), stream: vi.fn() } }))
vi.mock('../api/conversations', () => ({
  conversationsApi: {
    list: vi.fn(), messages: vi.fn(), get: vi.fn(), changeModel: vi.fn(),
    rename: vi.fn(), delete: vi.fn(),
  },
}))
vi.mock('../api/models', () => ({ modelsApi: { list: vi.fn() } }))

const models: ModelInfo[] = [
  { id: 'STEP_FLASH_3_7', displayName: 'Step 3.7 Flash', supportsText: true, supportsTools: true, supportsStreaming: true, supportsImages: true, available: true },
  { id: 'DEEPSEEK_V4_PRO', displayName: 'DeepSeek V4 Pro', supportsText: true, supportsTools: true, supportsStreaming: true, supportsImages: false, available: true },
]

const conversation: Conversation = {
  id: 'conversation-1',
  title: 'Eggs and tomatoes',
  modelId: 'STEP_FLASH_3_7',
  createdAt: '2026-08-01T00:00:00Z',
  updatedAt: '2026-08-01T00:01:00Z',
}

const message: ChatMessage = {
  id: 1,
  role: 'USER',
  content: 'I have eggs',
  imageId: null,
  createdAt: '2026-08-01T00:00:00Z',
}

function page<T>(content: T[]): PageResponse<T> {
  return { content, page: 0, size: 100, totalElements: content.length, totalPages: content.length ? 1 : 0 }
}

function completedStream(conversationId: string): void {
  vi.mocked(chatApi.stream).mockImplementation(async (_request, onEvent) => {
    onEvent({ type: 'status', conversationId, stage: 'thinking', message: 'Thinking…' })
    onEvent({ type: 'token', conversationId, content: 'Try an omelette.' })
    onEvent({ type: 'done', conversationId })
  })
}

describe('chat store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.mocked(conversationsApi.list).mockResolvedValue(page([conversation]))
    vi.mocked(conversationsApi.messages).mockResolvedValue(page([message]))
    vi.mocked(conversationsApi.get).mockResolvedValue(conversation)
    vi.mocked(conversationsApi.changeModel).mockImplementation(async (_id, modelId) => ({ ...conversation, modelId }))
    vi.mocked(conversationsApi.rename).mockImplementation(async (_id, title) => ({ ...conversation, title }))
    vi.mocked(conversationsApi.delete).mockResolvedValue(undefined)
    vi.mocked(modelsApi.list).mockResolvedValue(models)
  })

  it('loads the conversation list and selects message history', async () => {
    const store = useChatStore()
    await store.loadConversations()
    await store.selectConversation(conversation.id)

    expect(store.conversations).toEqual([conversation])
    expect(store.activeConversationId).toBe(conversation.id)
    expect(store.messages).toEqual([message])
  })

  it('starts a new chat without creating an empty conversation', async () => {
    const store = useChatStore()
    await store.selectConversation(conversation.id)
    store.startNewConversation()

    expect(store.activeConversationId).toBeNull()
    expect(store.messages).toEqual([])
    expect(chatApi.stream).not.toHaveBeenCalled()
  })

  it('renames a conversation without changing its id or messages', async () => {
    const store = useChatStore()
    await store.loadConversations()
    await store.selectConversation(conversation.id)

    expect(await store.renameConversation(conversation.id, '  Weeknight shakshuka  ')).toBe(true)
    expect(conversationsApi.rename).toHaveBeenCalledWith(conversation.id, 'Weeknight shakshuka')
    expect(store.conversations[0]?.id).toBe(conversation.id)
    expect(store.conversations[0]?.title).toBe('Weeknight shakshuka')
    expect(store.messages).toEqual([message])
  })

  it('deletes the active conversation and returns to a clean new chat', async () => {
    const store = useChatStore()
    await store.loadConversations()
    await store.selectConversation(conversation.id)

    expect(await store.deleteConversation(conversation.id)).toBe(true)
    expect(conversationsApi.delete).toHaveBeenCalledWith(conversation.id)
    expect(store.conversations).toEqual([])
    expect(store.activeConversationId).toBeNull()
    expect(store.messages).toEqual([])
  })

  it('deletes a different conversation without disturbing the active chat', async () => {
    const other = { ...conversation, id: 'conversation-2', title: 'Soup' }
    vi.mocked(conversationsApi.list).mockResolvedValue(page([conversation, other]))
    const store = useChatStore()
    await store.loadConversations()
    await store.selectConversation(conversation.id)

    expect(await store.deleteConversation(other.id)).toBe(true)
    expect(store.activeConversationId).toBe(conversation.id)
    expect(store.messages).toEqual([message])
    expect(store.conversations.map((item) => item.id)).toEqual([conversation.id])
  })

  it('omits conversationId on the first message and activates Java generated id', async () => {
    completedStream('generated-id')
    const store = useChatStore()
    expect(await store.sendMessage('  I have eggs  ')).toBe(true)

    expect(vi.mocked(chatApi.stream).mock.calls[0]?.[0]).toEqual({
      conversationId: undefined,
      message: 'I have eggs',
      imageId: undefined,
      modelId: 'STEP_FLASH_3_7',
    })
    expect(store.activeConversationId).toBe('generated-id')
  })

  it('reuses the active conversation and forwards an owned imageId', async () => {
    completedStream(conversation.id)
    const store = useChatStore()
    await store.selectConversation(conversation.id)
    await store.sendMessage('What is in this photo?', 'image-123')

    expect(vi.mocked(chatApi.stream).mock.calls[0]?.[0]).toEqual({
      conversationId: conversation.id,
      message: 'What is in this photo?',
      imageId: 'image-123',
      modelId: 'STEP_FLASH_3_7',
    })
  })

  it('renders status and tokens incrementally and prevents duplicate sends', async () => {
    let emit: ((event: ChatStreamEvent) => void) | undefined
    let finish: (() => void) | undefined
    vi.mocked(chatApi.stream).mockImplementation((_request, onEvent) => new Promise<void>((resolve) => {
      emit = onEvent
      finish = resolve
    }))
    const store = useChatStore()

    const first = store.sendMessage('One request')
    expect(store.messages.map((item) => item.role)).toEqual(['USER', 'ASSISTANT'])
    expect(store.isSending).toBe(true)
    expect(await store.sendMessage('Duplicate')).toBe(false)
    expect(chatApi.stream).toHaveBeenCalledOnce()

    emit?.({ type: 'status', conversationId: 'generated-id', stage: 'summarizing_context' })
    expect(store.streamStatus).toBe('正在整理较早的对话内容…')
    emit?.({ type: 'status', conversationId: 'generated-id', stage: 'searching_recipes', message: 'Searching recipes…' })
    emit?.({ type: 'token', conversationId: 'generated-id', content: 'First ' })
    expect(store.streamStatus).toBe('正在搜索菜谱…')
    expect(store.messages.at(-1)?.content).toBe('First ')

    emit?.({ type: 'token', conversationId: 'generated-id', content: 'answer.' })
    emit?.({ type: 'done', conversationId: 'generated-id' })
    finish?.()
    expect(await first).toBe(true)
    expect(store.isSending).toBe(false)
  })

  it('shows real image-generation status and receives the persisted preview event', async () => {
    let emit: ((event: ChatStreamEvent) => void) | undefined
    let finish: (() => void) | undefined
    vi.mocked(chatApi.stream).mockImplementation((_request, onEvent) => new Promise<void>((resolve) => {
      emit = onEvent
      finish = resolve
    }))
    const store = useChatStore()
    const request = store.sendMessage('Generate an image of the second dish')

    emit?.({ type: 'status', conversationId: 'image-thread', stage: 'generating_image' })
    expect(store.streamStatus).toBe('正在生成菜品图片…')
    emit?.({ type: 'token', conversationId: 'image-thread', content: 'Here it is.' })
    emit?.({
      type: 'generated_image',
      conversationId: 'image-thread',
      generatedImage: {
        imageId: 'generated-1',
        url: 'https://signed.example/generated',
        imageModel: 'step-image-edit-2',
        createdAt: '2026-08-09T12:00:00Z',
      },
    })

    expect(store.messages.at(-1)?.generatedImages?.[0]?.imageId).toBe('generated-1')
    emit?.({ type: 'done', conversationId: 'image-thread' })
    finish?.()
    await request
  })

  it('keeps assistant text and offers retry when image generation fails', async () => {
    const savedAssistant: ChatMessage = {
      id: 2,
      role: 'ASSISTANT',
      content: 'The recipe is still available.',
      imageId: null,
      createdAt: '2026-08-09T12:00:00Z',
      generatedImages: [],
    }
    vi.mocked(conversationsApi.messages).mockResolvedValue(
      page([message, savedAssistant]),
    )
    vi.mocked(chatApi.stream).mockImplementation(async (_request, onEvent) => {
      onEvent({ type: 'token', conversationId: conversation.id, content: savedAssistant.content })
      onEvent({ type: 'image_error', conversationId: conversation.id, message: 'Image generation failed.' })
      onEvent({ type: 'done', conversationId: conversation.id })
    })
    const store = useChatStore()

    expect(await store.sendMessage('Show the plated dish')).toBe(true)
    const assistant = store.messages.at(-1)
    expect(assistant?.content).toBe(savedAssistant.content)
    expect(assistant?.imageGenerationFailed).toBe(true)
    expect(assistant?.imageRetryPrompt).toBe('Show the plated dish')
    expect(await store.retryGeneratedImage('Show the plated dish')).toBe(true)
    expect(chatApi.stream).toHaveBeenCalledTimes(2)
  })

  it('removes a partial assistant response after a stream error', async () => {
    vi.mocked(chatApi.stream).mockImplementation(async (_request, onEvent) => {
      onEvent({ type: 'token', conversationId: conversation.id, content: 'Partial' })
      throw new Error('safe upstream error')
    })
    const store = useChatStore()

    expect(await store.sendMessage('Question')).toBe(false)
    expect(store.messages.some((item) => item.role === 'ASSISTANT')).toBe(false)
    expect(store.errorMessage).toBe('AI Cooker 暂时无法回答，请重试。')
  })

  it('selects DeepSeek for a new conversation and exposes its image limitation', async () => {
    completedStream('deep-conversation')
    const store = useChatStore()
    await store.loadModels()

    expect(await store.selectModel('DEEPSEEK_V4_PRO')).toBe(true)
    expect(store.selectedModelId).toBe('DEEPSEEK_V4_PRO')
    expect(store.selectedModel?.supportsImages).toBe(false)
    expect(store.modelNotice).toContain('仅支持文字对话')
    await store.sendMessage('I have tofu')
    expect(vi.mocked(chatApi.stream).mock.calls[0]?.[0].modelId).toBe('DEEPSEEK_V4_PRO')
    expect(conversationsApi.changeModel).not.toHaveBeenCalled()
  })

  it('restores and explicitly switches the persisted conversation model', async () => {
    const deepConversation = { ...conversation, modelId: 'DEEPSEEK_V4_PRO' as const }
    vi.mocked(conversationsApi.get).mockResolvedValue(deepConversation)
    const store = useChatStore()
    await store.loadModels()
    await store.selectConversation(deepConversation.id)

    expect(store.selectedModelId).toBe('DEEPSEEK_V4_PRO')
    expect(await store.selectModel('STEP_FLASH_3_7')).toBe(true)
    expect(conversationsApi.changeModel).toHaveBeenCalledWith(
      deepConversation.id,
      'STEP_FLASH_3_7',
    )
    expect(store.selectedModelId).toBe('STEP_FLASH_3_7')
  })
})
