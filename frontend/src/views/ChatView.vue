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
    shareError.value = getApiErrorMessage(error, '社区帖子草稿生成失败。')
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
        <button class="icon-button menu-button" type="button" aria-label="打开对话列表" @click="sidebarOpen = true">
          <svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <div>
          <span class="chat-header__eyebrow">你的智能烹饪助手</span>
          <h1>
            {{ chatStore.activeConversationId
              ? chatStore.conversations.find((item) => item.id === chatStore.activeConversationId)?.title || '对话'
              : '新对话' }}
          </h1>
        </div>
        <label class="model-selector">
          <span class="visually-hidden">对话模型</span>
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
            >{{ model.displayName }}{{ model.available ? '' : '（未配置）' }}</option>
          </select>
        </label>
        <button
          v-if="chatStore.activeConversationId"
          class="share-post-button"
          type="button"
          :disabled="chatStore.isSending || isGeneratingDraft || !canGenerateForumDraft"
          :title="canGenerateForumDraft
            ? '根据当前对话生成社区帖子草稿'
            : '请等待 AI 完整回答后再分享'"
          @click="shareAsPost"
        >{{ isGeneratingDraft ? '正在生成草稿…' : '分享为帖子' }}</button>
        <span class="status-pill"><i /> 在线</span>
      </header>

      <div ref="messageScroller" class="chat-scroll">
        <div v-if="!chatStore.activeConversationId && chatStore.messages.length === 0" class="empty-chat">
          <div class="empty-chat__icon">🍲</div>
          <span class="eyebrow">一起做饭吧</span>
          <h2>你的厨房里有哪些食材？</h2>
          <p>在下方描述食材，或者添加照片，我会帮你把它们变成美味的一餐。</p>
          <div class="suggestion-grid">
            <button type="button" @click="draft = '我有鸡蛋、番茄和菠菜，可以做什么？'">
              <span>🥚</span> 用现有食材做菜
            </button>
            <button type="button" @click="draft = '请推荐一道适合今晚的快手健康晚餐。'">
              <span>⏱️</span> 快手健康晚餐
            </button>
            <button type="button" @click="draft = '请帮我分析这份菜谱的营养成分。'">
              <span>🥗</span> 询问营养信息
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
          :image-name="imageUpload.image.value?.originalFilename || '食材图片'"
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
