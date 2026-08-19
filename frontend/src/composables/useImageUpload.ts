import { computed, onScopeDispose, ref } from 'vue'

import { imagesApi } from '../api/images'
import type { ImageResponse } from '../types/api'
import { getApiErrorMessage } from '../utils/apiError'

export function useImageUpload() {
  const image = ref<ImageResponse | null>(null)
  const isUploading = ref(false)
  const progress = ref(0)
  const errorMessage = ref('')
  const previewUrl = ref('')
  const hasUploadError = computed(() => Boolean(errorMessage.value))
  let requestSequence = 0

  function revokePreview(): void {
    if (previewUrl.value) {
      URL.revokeObjectURL(previewUrl.value)
      previewUrl.value = ''
    }
  }

  async function upload(file: File): Promise<ImageResponse | null> {
    const sequence = ++requestSequence
    revokePreview()
    previewUrl.value = URL.createObjectURL(file)
    isUploading.value = true
    progress.value = 0
    errorMessage.value = ''
    image.value = null
    try {
      const response = await imagesApi.upload(file, (value) => {
        if (sequence === requestSequence) progress.value = value
      })
      if (sequence !== requestSequence) return null
      image.value = response
      progress.value = 100
      return image.value
    } catch (error) {
      if (sequence !== requestSequence) return null
      errorMessage.value = getApiErrorMessage(error, 'The image could not be uploaded.')
      return null
    } finally {
      if (sequence === requestSequence) isUploading.value = false
    }
  }

  function clear(): void {
    requestSequence++
    revokePreview()
    image.value = null
    isUploading.value = false
    progress.value = 0
    errorMessage.value = ''
  }

  onScopeDispose(revokePreview)

  return {
    image,
    previewUrl,
    isUploading,
    progress,
    errorMessage,
    hasUploadError,
    upload,
    clear,
  }
}
