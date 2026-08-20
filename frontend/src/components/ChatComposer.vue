<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  disabled: boolean
  sendBlocked: boolean
  uploading: boolean
  uploadProgress: number
  imageUrl?: string
  imageName?: string
  uploadError?: string
  imageSupported?: boolean
}>(), {
  imageSupported: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  fileSelected: [file: File]
  clearImage: []
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const cannotSend = computed(
  () => props.disabled || props.sendBlocked || props.uploading || !props.modelValue.trim(),
)

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (!cannotSend.value) emit('send')
  }
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('fileSelected', file)
  input.value = ''
}
</script>

<template>
  <div class="composer-wrap">
    <div v-if="imageUrl || uploading" class="upload-card">
      <img v-if="imageUrl" :src="imageUrl" :alt="imageName || '已上传的食材图片预览'" />
      <div v-else class="upload-card__placeholder"><span class="spinner" /></div>
      <div class="upload-card__details">
        <strong>{{ uploading ? '正在上传图片…' : imageName }}</strong>
        <div v-if="uploading" class="progress-track">
          <span :style="{ width: `${uploadProgress}%` }" />
        </div>
        <span v-else-if="uploadError" class="upload-card__error">上传失败，请选择其他图片</span>
        <span v-else>可以发送</span>
      </div>
      <button
        v-if="!uploading"
        class="icon-button"
        type="button"
        aria-label="移除图片"
        @click="emit('clearImage')"
      >
        <svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18" /></svg>
      </button>
    </div>

    <div class="composer">
      <input
        ref="fileInput"
        class="visually-hidden"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        :disabled="disabled || uploading || !imageSupported"
        @change="onFileChange"
      />
      <button
        class="composer__attach icon-button"
        type="button"
        aria-label="上传食材图片"
        :disabled="disabled || uploading || !imageSupported"
        :title="imageSupported ? '上传食材图片' : '当前模型不支持图片'"
        @click="fileInput?.click()"
      >
        <svg viewBox="0 0 24 24"><path d="M12 5v10a4 4 0 0 1-8 0V7a6 6 0 0 1 12 0v10a2 2 0 0 1-4 0V8" /></svg>
      </button>
      <textarea
        :value="modelValue"
        rows="1"
        maxlength="20000"
        placeholder="描述你的食材，或者询问菜谱…"
        :disabled="disabled"
        @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
        @keydown="onKeydown"
      />
      <button
        class="send-button"
        type="button"
        :disabled="cannotSend"
        aria-label="发送消息"
        @click="emit('send')"
      >
        <svg viewBox="0 0 24 24"><path d="m5 12 14-7-4 14-3-5-7-2Zm7 2 7-9" /></svg>
      </button>
    </div>
    <p class="composer-hint">
      {{ imageSupported ? '按 Enter 发送 · 按 Shift + Enter 换行' : '当前模型仅支持文字对话。' }}
    </p>
  </div>
</template>
