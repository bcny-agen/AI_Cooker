<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { forumApi } from '../api/forum'
import ForumHeader from '../components/ForumHeader.vue'
import ForumImage from '../components/ForumImage.vue'
import type { ForumPost } from '../types/api'
import { getApiErrorMessage } from '../utils/apiError'

const route = useRoute()
const router = useRouter()
const post = ref<ForumPost | null>(null)
const loading = ref(true)
const deleting = ref(false)
const errorMessage = ref('')

function formatDate(value: string): string {
  return new Date(value).toLocaleString([], { dateStyle: 'long', timeStyle: 'short' })
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  post.value = null
  try {
    post.value = await forumApi.get(String(route.params.postId))
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, 'This forum post could not be loaded.')
  } finally {
    loading.value = false
  }
}

async function remove(): Promise<void> {
  if (!post.value || !window.confirm('Delete this forum post? This cannot be undone.')) return
  deleting.value = true
  errorMessage.value = ''
  try {
    await forumApi.remove(post.value.id)
    await router.replace('/forum/mine')
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, 'The post could not be deleted.')
  } finally {
    deleting.value = false
  }
}

watch(() => route.params.postId, load)
onMounted(load)
</script>

<template>
  <main class="forum-shell">
    <ForumHeader />
    <article class="forum-detail">
      <RouterLink class="back-link" to="/forum">← Back to forum</RouterLink>
      <div v-if="loading" class="forum-state"><span class="spinner" /> Loading post…</div>
      <div v-else-if="errorMessage && !post" class="notice notice--error" role="alert">{{ errorMessage }}</div>
      <template v-else-if="post">
        <ForumImage
          v-if="post.imageId"
          class="forum-detail__image"
          :post-id="post.id"
          :image-id="post.imageId"
          :alt="post.title"
        />
        <div class="forum-detail__content">
          <span class="eyebrow">Shared dish</span>
          <h1>{{ post.title }}</h1>
          <div class="forum-detail__meta">
            <span>By @{{ post.author.username }}</span>
            <time :datetime="post.createdAt">{{ formatDate(post.createdAt) }}</time>
          </div>
          <p class="forum-detail__text">{{ post.content }}</p>
          <div v-if="post.isOwner" class="forum-owner-actions">
            <RouterLink class="secondary-button" :to="`/forum/${post.id}/edit`">Edit post</RouterLink>
            <button class="danger-button" type="button" :disabled="deleting" @click="remove">
              {{ deleting ? 'Deleting…' : 'Delete post' }}
            </button>
          </div>
          <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>
        </div>
      </template>
    </article>
  </main>
</template>
