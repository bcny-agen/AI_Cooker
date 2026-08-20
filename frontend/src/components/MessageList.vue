<script setup lang="ts">
import type { ChatMessage } from '../types/api'
import AssistantMarkdown from './AssistantMarkdown.vue'

defineProps<{
  messages: ChatMessage[]
  loading: boolean
  sending: boolean
  streamStatus: string
  imageUrls: Record<string, string>
}>()

const emit = defineEmits<{
  imageError: [imageId: string]
  generatedImageError: [imageId: string]
  retryImage: [prompt: string]
}>()
</script>

<template>
  <div class="messages" aria-live="polite">
    <div v-if="loading" class="messages__state">
      <span class="spinner" /> 正在加载对话…
    </div>

    <template v-else>
      <article
        v-for="message in messages"
        :key="message.id"
        class="message-row"
        :class="`message-row--${message.role.toLowerCase()}`"
      >
      <div class="message-avatar" aria-hidden="true">
        <svg v-if="message.role === 'ASSISTANT'" viewBox="0 0 24 24">
          <path d="M5 13h14v2a7 7 0 0 1-14 0v-2ZM8 10c0-2 1.5-4 4-4 1-2 4-2 5 0 2 0 3 1 3 3 0 1-.3 2-1 2H6c-.5-.5-1-1.3-1-2 0-1.7 1.3-3 3-3" />
        </svg>
        <svg v-else viewBox="0 0 24 24">
          <circle cx="12" cy="8" r="4" /><path d="M5 21a7 7 0 0 1 14 0" />
        </svg>
      </div>
      <div class="message-body">
        <div class="message-name">{{ message.role === 'USER' ? '你' : 'AI Cooker' }}</div>
        <img
          v-if="message.imageId && imageUrls[message.imageId]"
          class="message-image"
          :src="imageUrls[message.imageId]"
          alt="这条消息附带的食材图片"
          @error="emit('imageError', message.imageId)"
        />
        <div v-else-if="message.imageId" class="message-image-placeholder">图片预览暂不可用</div>
        <div v-if="message.temporary && sending && streamStatus" class="agent-progress" role="status">
          <span class="agent-progress__dots" aria-hidden="true">
            <span class="agent-progress__dot" /><span class="agent-progress__dot" /><span class="agent-progress__dot" />
          </span>
          {{ streamStatus }}
        </div>
        <div v-if="message.temporary && sending && !streamStatus && !message.content" class="thinking" role="status" aria-label="AI Cooker 正在思考">
          <span /><span /><span />
        </div>
        <AssistantMarkdown
          v-if="message.content && message.role === 'ASSISTANT'"
          :content="message.content"
          :streaming="message.temporary && sending"
        />
        <p
          v-else-if="message.content"
          class="message-content"
          :class="{ 'message-content--streaming': message.temporary && sending }"
        >{{ message.content }}</p>
        <div
          v-if="message.role === 'ASSISTANT' && message.generatedImages?.length"
          class="generated-image-list"
        >
          <figure
            v-for="image in message.generatedImages"
            :key="image.imageId"
            class="generated-dish-image"
          >
            <img
              :src="image.url"
              alt="AI 生成的菜品预览图"
              loading="lazy"
              @error="emit('generatedImageError', image.imageId)"
            />
            <figcaption>AI 生成的菜品预览</figcaption>
          </figure>
        </div>
        <div
          v-if="message.role === 'ASSISTANT' && message.imageGenerationFailed"
          class="generated-image-error"
          role="alert"
        >
          <span>图片生成失败。</span>
          <button
            v-if="message.imageRetryPrompt"
            type="button"
            :disabled="sending"
            @click="emit('retryImage', message.imageRetryPrompt)"
          >重试</button>
        </div>
      </div>
      </article>
    </template>
  </div>
</template>
