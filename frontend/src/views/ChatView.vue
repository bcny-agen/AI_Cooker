<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { imagesApi } from '../api/images'
import { generatedImagesApi } from '../api/generatedImages'
import { forumApi } from '../api/forum'
import ChatComposer from '../components/ChatComposer.vue'
import ChatSidebar from '../components/ChatSidebar.vue'
import MessageList from '../components/MessageList.vue'
import { useImageUpload } from '../composables/useImageUpload'
import { useAuthStore } from '../stores/auth'
import { useChatStore } from '../stores/chat'
import { useForumDraftStore } from '../stores/forumDraft'
import { getApiErrorMessage } from '../utils/apiError'

const authStore = useAuthStore()
const chatStore = useChatStore()
const forumDraftStore = useForumDraftStore()
const router = useRouter()
const imageUpload = useImageUpload()

const draft = ref('')
const sidebarOpen = ref(false)
const messageScroller = ref<HTMLElement | null>(null)
const imageUrls = ref<Record<string, string>>({})
const isGeneratingDraft = ref(false)
const shareError = ref('')
const canGenerateForumDraft = computed(() => {
  const hasUserMessage = chatStore.messages.some(
    (message) => message.role === 'USER' && message.content.trim(),
  )
  const hasAssistantMessage = chatStore.messages.some(
    (message) => message.role === 'ASSISTANT' && message.content.trim(),
  )
  return hasUserMessage && hasAssistantMessage
})

async function initialize(): Promise<void> {
  const results = await Promise.allSettled([
    chatStore.loadModels(),
    chatStore.loadConversations(),
  ])
  if (results.some((result) => result.status === 'rejected')) {
    // The store exposes a user-safe error message.
  }
}

async function selectConversation(conversationId: string): Promise<void> {
  if (chatStore.isSending) return
  sidebarOpen.value = false
  imageUrls.value = {}
  try {
    await chatStore.selectConversation(conversationId)
  } catch {
    // The store exposes a user-safe error message.
  }
}

function newConversation(): void {
  if (chatStore.isSending) return
  chatStore.startNewConversation()
  imageUpload.clear()
  draft.value = ''
  sidebarOpen.value = false
}

async function renameConversation(conversationId: string, title: string): Promise<void> {
  await chatStore.renameConversation(conversationId, title)
}

async function deleteConversation(conversationId: string): Promise<void> {
  const deletedActiveConversation = chatStore.activeConversationId === conversationId
  const deleted = await chatStore.deleteConversation(conversationId)
  if (deleted && deletedActiveConversation) {
    imageUpload.clear()
    imageUrls.value = {}
    draft.value = ''
    sidebarOpen.value = false
  }
}

async function handleFile(file: File): Promise<void> {
  if (chatStore.selectedModel?.supportsImages === false) return
  await imageUpload.upload(file)
}

async function changeModel(event: Event): Promise<void> {
  const modelId = (event.target as HTMLSelectElement).value as import('../types/api').ModelId
  const changed = await chatStore.selectModel(modelId)
  if (changed && chatStore.selectedModel?.supportsImages === false) imageUpload.clear()
}

async function send(): Promise<void> {
  if (chatStore.isSending || !draft.value.trim()) return
  const message = draft.value
  const imageId = imageUpload.image.value?.imageId
  draft.value = ''
  imageUpload.clear()
  await chatStore.sendMessage(message, imageId)
}

async function logout(): Promise<void> {
  authStore.clearSession()
  chatStore.reset()
  await router.replace('/login')
}

async function shareAsPost(): Promise<void> {
  if (!chatStore.activeConversationId
    || !canGenerateForumDraft.value
    || chatStore.isSending
    || isGeneratingDraft.value) return
  isGeneratingDraft.value = true
  shareError.value = ''
  try {
    const draft = await forumApi.generateDraft(chatStore.activeConversationId)
    forumDraftStore.setDraft(draft)
    await router.push({ name: 'forum-new', query: { draft: 'generated' } })
  } catch (error) {
    shareError.value = getApiErrorMessage(error, 'The forum draft could not be generated.')
  } finally {
    isGeneratingDraft.value = false
  }
}

async function refreshImagePreview(id: string): Promise<void> {
  try {
    const image = await imagesApi.get(id)
    imageUrls.value = { ...imageUrls.value, [id]: image.url }
  } catch {
    const nextUrls = { ...imageUrls.value }
    delete nextUrls[id]
    imageUrls.value = nextUrls
  }
}

async function refreshGeneratedImagePreview(id: string): Promise<void> {
  try {
    const refreshed = await generatedImagesApi.get(id)
    chatStore.messages = chatStore.messages.map((message) => ({
      ...message,
      generatedImages: message.generatedImages?.map((image) =>
        image.imageId === id ? refreshed : image,
      ),
    }))
  } catch {
    // Keep the assistant text visible if the private preview is unavailable.
  }
}

async function loadImagePreviews(): Promise<void> {
  const ids = [...new Set(chatStore.messages.map((message) => message.imageId).filter(Boolean))] as string[]
  await Promise.all(
    ids.map(async (id) => {
      if (imageUrls.value[id]) return
      await refreshImagePreview(id)
    }),
  )
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (messageScroller.value) {
    messageScroller.value.scrollTop = messageScroller.value.scrollHeight
  }
}

watch(() => chatStore.messages, loadImagePreviews, { deep: true })
watch(
  () => [chatStore.messages.map((message) => message.content).join('\u0000'), chatStore.streamStatus, chatStore.isSending],
  scrollToBottom,
)

onMounted(initialize)
onBeforeUnmount(chatStore.cancelStream)
</script>

<template>
  <main class="chat-shell">
    <ChatSidebar
      :conversations="chatStore.conversations"
      :active-conversation-id="chatStore.activeConversationId"
      :loading="chatStore.isLoadingConversations"
      :open="sidebarOpen"
      :busy="chatStore.isSending"
      @new-conversation="newConversation"
      @select="selectConversation"
      @rename="renameConversation"
      @delete="deleteConversation"
      @logout="logout"
      @close="sidebarOpen = false"
    />

    <section class="chat-main">
      <header class="chat-header">
        <button class="icon-button menu-button" type="button" aria-label="Open conversations" @click="sidebarOpen = true">
          <svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <div>
          <span class="chat-header__eyebrow">Your cooking assistant</span>
          <h1>
            {{ chatStore.activeConversationId
              ? chatStore.conversations.find((item) => item.id === chatStore.activeConversationId)?.title || 'Conversation'
              : 'New conversation' }}
          </h1>
        </div>
        <label class="model-selector">
          <span class="visually-hidden">Conversation model</span>
          <select
            :value="chatStore.selectedModelId"
            :disabled="chatStore.isSending || chatStore.availableModels.length === 0"
            @change="changeModel"
          >
            <option
              v-for="model in chatStore.availableModels"
              :key="model.id"
              :value="model.id"
              :disabled="!model.available"
            >{{ model.displayName }}{{ model.available ? '' : ' (not configured)' }}</option>
          </select>
        </label>
        <button
          v-if="chatStore.activeConversationId"
          class="share-post-button"
          type="button"
          :disabled="chatStore.isSending || isGeneratingDraft || !canGenerateForumDraft"
          :title="canGenerateForumDraft
            ? 'Generate a forum draft from this conversation'
            : 'Wait for a complete AI answer before sharing'"
          @click="shareAsPost"
        >{{ isGeneratingDraft ? 'Generating draft…' : 'Share as Post' }}</button>
        <span class="status-pill"><i /> Online</span>
      </header>

      <div ref="messageScroller" class="chat-scroll">
        <div v-if="!chatStore.activeConversationId && chatStore.messages.length === 0" class="empty-chat">
          <div class="empty-chat__icon">🍲</div>
          <span class="eyebrow">Let’s cook</span>
          <h2>What ingredients are in your kitchen?</h2>
          <p>Describe them below, or add a photo, and I’ll help turn them into a meal.</p>
          <div class="suggestion-grid">
            <button type="button" @click="draft = 'I have eggs, tomatoes, and spinach. What can I make?'">
              <span>🥚</span> Use what I have
            </button>
            <button type="button" @click="draft = 'Suggest a quick and healthy dinner for tonight.'">
              <span>⏱️</span> Quick healthy dinner
            </button>
            <button type="button" @click="draft = 'Help me understand the nutrition of this recipe.'">
              <span>🥗</span> Ask about nutrition
            </button>
          </div>
        </div>

        <MessageList
          v-else
          :messages="chatStore.messages"
          :loading="chatStore.isLoadingMessages"
          :sending="chatStore.isSending"
          :stream-status="chatStore.streamStatus"
          :image-urls="imageUrls"
          @image-error="refreshImagePreview"
          @generated-image-error="refreshGeneratedImagePreview"
          @retry-image="chatStore.retryGeneratedImage"
        />
      </div>

      <div class="chat-footer">
        <div v-if="shareError || chatStore.errorMessage || imageUpload.errorMessage.value" class="inline-error" role="alert">
          {{ shareError || imageUpload.errorMessage.value || chatStore.errorMessage }}
        </div>
        <div v-else-if="chatStore.modelNotice" class="model-notice" role="status">
          {{ chatStore.modelNotice }}
        </div>
        <ChatComposer
          v-model="draft"
          :disabled="chatStore.isSending"
          :send-blocked="imageUpload.hasUploadError.value"
          :uploading="imageUpload.isUploading.value"
          :upload-progress="imageUpload.progress.value"
          :image-url="imageUpload.previewUrl.value"
          :image-name="imageUpload.image.value?.originalFilename || 'Ingredient image'"
          :upload-error="imageUpload.errorMessage.value"
          :image-supported="chatStore.selectedModel?.supportsImages !== false"
          @send="send"
          @file-selected="handleFile"
          @clear-image="imageUpload.clear"
        />
      </div>
    </section>
  </main>
</template>
