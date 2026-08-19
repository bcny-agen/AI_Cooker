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
      <img v-if="imageUrl" :src="imageUrl" :alt="imageName || 'Uploaded ingredient preview'" />
      <div v-else class="upload-card__placeholder"><span class="spinner" /></div>
      <div class="upload-card__details">
        <strong>{{ uploading ? 'Uploading image…' : imageName }}</strong>
        <div v-if="uploading" class="progress-track">
          <span :style="{ width: `${uploadProgress}%` }" />
        </div>
        <span v-else-if="uploadError" class="upload-card__error">Upload failed — choose another image</span>
        <span v-else>Ready to send</span>
      </div>
      <button
        v-if="!uploading"
        class="icon-button"
        type="button"
        aria-label="Remove image"
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
        aria-label="Upload an ingredient image"
        :disabled="disabled || uploading || !imageSupported"
        :title="imageSupported ? 'Upload an ingredient image' : 'The selected model does not support images'"
        @click="fileInput?.click()"
      >
        <svg viewBox="0 0 24 24"><path d="M12 5v10a4 4 0 0 1-8 0V7a6 6 0 0 1 12 0v10a2 2 0 0 1-4 0V8" /></svg>
      </button>
      <textarea
        :value="modelValue"
        rows="1"
        maxlength="20000"
        placeholder="Describe your ingredients or ask about a recipe…"
        :disabled="disabled"
        @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
        @keydown="onKeydown"
      />
      <button
        class="send-button"
        type="button"
        :disabled="cannotSend"
        aria-label="Send message"
        @click="emit('send')"
      >
        <svg viewBox="0 0 24 24"><path d="m5 12 14-7-4 14-3-5-7-2Zm7 2 7-9" /></svg>
      </button>
    </div>
    <p class="composer-hint">
      {{ imageSupported ? 'Enter to send · Shift + Enter for a new line' : 'This model accepts text only.' }}
    </p>
  </div>
</template>
