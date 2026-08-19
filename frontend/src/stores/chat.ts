import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { chatApi } from '../api/chat'
import { conversationsApi } from '../api/conversations'
import { modelsApi } from '../api/models'
import type { ChatMessage, ChatStreamStage, Conversation, ModelId, ModelInfo } from '../types/api'
import { getApiErrorMessage } from '../utils/apiError'

const STATUS_LABELS: Record<ChatStreamStage, string> = {
  thinking: 'Thinking…',
  analyzing_image: 'Analyzing your image…',
  summarizing_context: 'Compressing older conversation context…',
  searching_recipes: 'Searching recipes…',
  generating_image: 'Generating dish image…',
  generating_answer: 'Writing the answer…',
  completed: 'Completed',
}

const DEFAULT_MODEL_ID: ModelId = 'STEP_FLASH_3_7'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const availableModels = ref<ModelInfo[]>([])
  const selectedModelId = ref<ModelId>(DEFAULT_MODEL_ID)
  const activeConversationId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isLoadingConversations = ref(false)
  const isLoadingMessages = ref(false)
  const isSending = ref(false)
  const streamStatus = ref('')
  const errorMessage = ref('')
  const modelNotice = ref('')
  let messageRequestSequence = 0
  let temporaryMessageId = -1
  let activeStreamController: AbortController | null = null

  const selectedModel = computed(() =>
    availableModels.value.find((model) => model.id === selectedModelId.value) ?? null,
  )

  async function loadModels(): Promise<void> {
    try {
      availableModels.value = await modelsApi.list()
      const selected = availableModels.value.find((model) => model.id === selectedModelId.value)
      if (!selected?.available) {
        selectedModelId.value = availableModels.value.find((model) => model.available)?.id ?? DEFAULT_MODEL_ID
      }
    } catch (error) {
      errorMessage.value = getApiErrorMessage(error, 'Could not load available AI models.')
      throw error
    }
  }

  async function loadConversations(): Promise<void> {
    isLoadingConversations.value = true
    errorMessage.value = ''
    try {
      conversations.value = (await conversationsApi.list()).content
    } catch (error) {
      errorMessage.value = getApiErrorMessage(error, 'Could not load conversations.')
      throw error
    } finally {
      isLoadingConversations.value = false
    }
  }

  async function selectConversation(conversationId: string): Promise<void> {
    const requestSequence = ++messageRequestSequence
    activeConversationId.value = conversationId
    messages.value = []
    isLoadingMessages.value = true
    errorMessage.value = ''
    try {
      const knownConversation = conversations.value.find((item) => item.id === conversationId)
      const [response, conversation] = await Promise.all([
        conversationsApi.messages(conversationId),
        knownConversation ? Promise.resolve(knownConversation) : conversationsApi.get(conversationId),
      ])
      if (requestSequence === messageRequestSequence) {
        messages.value = response.content
        selectedModelId.value = conversation.modelId
        updateModelNotice()
      }
    } catch (error) {
      if (requestSequence === messageRequestSequence) {
        errorMessage.value = getApiErrorMessage(error, 'Could not load this conversation.')
      }
      throw error
    } finally {
      if (requestSequence === messageRequestSequence) {
        isLoadingMessages.value = false
      }
    }
  }

  function startNewConversation(): void {
    messageRequestSequence++
    activeConversationId.value = null
    messages.value = []
    selectedModelId.value = DEFAULT_MODEL_ID
    updateModelNotice()
    errorMessage.value = ''
  }

  function updateModelNotice(): void {
    const model = selectedModel.value
    modelNotice.value = model && !model.supportsImages
      ? `${model.displayName} supports text chat only; image upload is unavailable.`
      : ''
  }

  async function selectModel(modelId: ModelId): Promise<boolean> {
    if (isSending.value) return false
    const model = availableModels.value.find((item) => item.id === modelId)
    if (!model?.available) {
      modelNotice.value = 'That model is not configured on the AI service.'
      return false
    }

    if (activeConversationId.value) {
      try {
        const updated = await conversationsApi.changeModel(activeConversationId.value, modelId)
        conversations.value = conversations.value.map((item) => item.id === updated.id ? updated : item)
      } catch (error) {
        errorMessage.value = getApiErrorMessage(error, 'Could not change the conversation model.')
        return false
      }
    }
    selectedModelId.value = modelId
    updateModelNotice()
    return true
  }

  async function renameConversation(conversationId: string, title: string): Promise<boolean> {
    if (isSending.value) return false
    const normalizedTitle = title.trim()
    if (!normalizedTitle) return false
    try {
      const updated = await conversationsApi.rename(conversationId, normalizedTitle)
      conversations.value = conversations.value.map((item) => item.id === updated.id ? updated : item)
      return true
    } catch (error) {
      errorMessage.value = getApiErrorMessage(error, 'Could not rename this conversation.')
      return false
    }
  }

  async function deleteConversation(conversationId: string): Promise<boolean> {
    if (isSending.value) return false
    try {
      await conversationsApi.delete(conversationId)
      conversations.value = conversations.value.filter((item) => item.id !== conversationId)
      if (activeConversationId.value === conversationId) startNewConversation()
      return true
    } catch (error) {
      errorMessage.value = getApiErrorMessage(error, 'Could not delete this conversation.')
      return false
    }
  }

  async function refreshAfterStream(conversationId: string): Promise<boolean> {
    const [messagesResult, conversationsResult] = await Promise.allSettled([
      conversationsApi.messages(conversationId),
      conversationsApi.list(),
    ])
    if (messagesResult.status === 'fulfilled') messages.value = messagesResult.value.content
    if (conversationsResult.status === 'fulfilled') conversations.value = conversationsResult.value.content
    return messagesResult.status === 'fulfilled' && conversationsResult.status === 'fulfilled'
  }

  async function sendMessage(message: string, imageId?: string): Promise<boolean> {
    if (isSending.value) return false
    const normalizedMessage = message.trim()
    if (!normalizedMessage) return false

    const priorConversationId = activeConversationId.value
    const userMessageId = temporaryMessageId--
    const assistantMessageId = temporaryMessageId--
    const timestamp = new Date().toISOString()
    messages.value = [
      ...messages.value,
      { id: userMessageId, role: 'USER', content: normalizedMessage, imageId: imageId ?? null, createdAt: timestamp, temporary: true },
      { id: assistantMessageId, role: 'ASSISTANT', content: '', imageId: null, createdAt: timestamp, temporary: true, generatedImages: [] },
    ]

    isSending.value = true
    streamStatus.value = STATUS_LABELS.thinking
    errorMessage.value = ''
    const controller = new AbortController()
    activeStreamController = controller
    let resolvedConversationId = priorConversationId

    try {
      await chatApi.stream(
        {
          conversationId: priorConversationId ?? undefined,
          message: normalizedMessage,
          imageId,
          modelId: selectedModelId.value,
        },
        (event) => {
          resolvedConversationId = event.conversationId
          activeConversationId.value = event.conversationId
          if (event.type === 'status') {
            streamStatus.value = event.message || (event.stage ? STATUS_LABELS[event.stage] : '')
          } else if (event.type === 'token' && event.content) {
            messages.value = messages.value.map((item) =>
              item.id === assistantMessageId ? { ...item, content: item.content + event.content } : item,
            )
          } else if (event.type === 'generated_image' && event.generatedImage) {
            messages.value = messages.value.map((item) =>
              item.id === assistantMessageId
                ? { ...item, generatedImages: [event.generatedImage!] }
                : item,
            )
          } else if (event.type === 'image_error') {
            messages.value = messages.value.map((item) =>
              item.id === assistantMessageId
                ? { ...item, imageGenerationFailed: true, imageRetryPrompt: normalizedMessage }
                : item,
            )
          }
        },
        controller.signal,
      )

      messages.value = messages.value.map((item) =>
        item.id === userMessageId || item.id === assistantMessageId ? { ...item, temporary: false } : item,
      )
      const imageFailure = messages.value.find(
        (item) => item.id === assistantMessageId,
      )?.imageGenerationFailed === true
      if (resolvedConversationId && !(await refreshAfterStream(resolvedConversationId))) {
        errorMessage.value = 'Your answer was saved, but part of the history could not refresh.'
      }
      if (imageFailure) {
        const lastAssistant = [...messages.value].reverse().find(
          (item) => item.role === 'ASSISTANT',
        )
        if (lastAssistant) {
          lastAssistant.imageGenerationFailed = true
          lastAssistant.imageRetryPrompt = normalizedMessage
        }
      }
      return true
    } catch (error) {
      messages.value = messages.value.filter((item) => item.id !== assistantMessageId)
      if (resolvedConversationId) {
        activeConversationId.value = resolvedConversationId
        await refreshAfterStream(resolvedConversationId)
      } else {
        messages.value = messages.value.filter((item) => item.id !== userMessageId)
      }
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        errorMessage.value = getApiErrorMessage(
          error,
          'AI Cooker could not answer. Please try again.',
        )
      }
      return false
    } finally {
      if (activeStreamController === controller) activeStreamController = null
      isSending.value = false
      streamStatus.value = ''
    }
  }

  function cancelStream(): void {
    activeStreamController?.abort()
    activeStreamController = null
  }

  async function retryGeneratedImage(prompt: string): Promise<boolean> {
    return sendMessage(prompt)
  }

  function reset(): void {
    cancelStream()
    messageRequestSequence++
    conversations.value = []
    availableModels.value = []
    selectedModelId.value = DEFAULT_MODEL_ID
    activeConversationId.value = null
    messages.value = []
    streamStatus.value = ''
    modelNotice.value = ''
    errorMessage.value = ''
  }

  return {
    conversations, availableModels, selectedModelId, selectedModel, activeConversationId, messages,
    isLoadingConversations, isLoadingMessages, isSending, streamStatus, errorMessage, modelNotice,
    loadModels, loadConversations, selectConversation, selectModel, startNewConversation,
    renameConversation, deleteConversation, sendMessage, retryGeneratedImage, cancelStream, reset,
  }
})
