<script setup lang="ts">
import { ref, watch } from 'vue'

import { forumApi } from '../api/forum'

const props = defineProps<{
  postId: string
  imageId: string
  alt: string
}>()

const url = ref('')
const loading = ref(false)
const failed = ref(false)
let refreshAttempted = false
let requestSequence = 0

async function load(): Promise<void> {
  const sequence = ++requestSequence
  loading.value = true
  failed.value = false
  try {
    const image = await forumApi.image(props.postId)
    if (sequence === requestSequence) url.value = image.url
  } catch {
    if (sequence === requestSequence) {
      url.value = ''
      failed.value = true
    }
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

async function handleError(): Promise<void> {
  if (!refreshAttempted) {
    refreshAttempted = true
    await load()
    return
  }
  failed.value = true
  url.value = ''
}

watch(
  () => [props.postId, props.imageId],
  () => {
    refreshAttempted = false
    url.value = ''
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <div class="forum-image" :class="{ 'forum-image--failed': failed }">
    <div v-if="loading && !url" class="forum-image__state" aria-label="正在加载图片">
      <span class="spinner" />
    </div>
    <img v-else-if="url && !failed" :src="url" :alt="alt" @error="handleError">
    <div v-else class="forum-image__state">图片暂不可用</div>
  </div>
</template>
