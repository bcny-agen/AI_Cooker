<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { forumApi } from '../api/forum'
import ForumHeader from '../components/ForumHeader.vue'
import ForumImage from '../components/ForumImage.vue'
import type { ForumPost } from '../types/api'
import { getApiErrorMessage } from '../utils/apiError'

const props = withDefaults(defineProps<{ mine?: boolean }>(), { mine: false })

const posts = ref<ForumPost[]>([])
const page = ref(0)
const totalPages = ref(0)
const loading = ref(false)
const errorMessage = ref('')

function formatDate(value: string): string {
  return new Date(value).toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function load(reset = false): Promise<void> {
  if (loading.value) return
  loading.value = true
  errorMessage.value = ''
  const requestedPage = reset ? 0 : page.value
  try {
    const response = props.mine
      ? await forumApi.mine(requestedPage)
      : await forumApi.list(requestedPage)
    posts.value = reset ? response.content : [...posts.value, ...response.content]
    page.value = response.page + 1
    totalPages.value = response.totalPages
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, 'The forum could not be loaded.')
  } finally {
    loading.value = false
  }
}

watch(() => props.mine, () => {
  posts.value = []
  page.value = 0
  totalPages.value = 0
  void load(true)
})

onMounted(() => load(true))
</script>

<template>
  <main class="forum-shell">
    <ForumHeader />
    <section class="forum-page">
      <div class="forum-hero">
        <div>
          <span class="eyebrow">Cooked by the community</span>
          <h1>{{ mine ? 'My shared dishes' : 'The AI Cooker table' }}</h1>
          <p>{{ mine ? 'Review and manage the dishes you have shared.' : 'See what other home cooks made and share your own result.' }}</p>
        </div>
        <RouterLink class="primary-link" to="/forum/new">Share a dish</RouterLink>
      </div>

      <nav class="forum-tabs" aria-label="Forum feeds">
        <RouterLink to="/forum" exact-active-class="forum-tabs__active">Community</RouterLink>
        <RouterLink to="/forum/mine" exact-active-class="forum-tabs__active">My posts</RouterLink>
      </nav>

      <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>
      <div v-if="loading && posts.length === 0" class="forum-state"><span class="spinner" /> Loading dishes…</div>
      <div v-else-if="posts.length === 0" class="forum-state forum-state--empty">
        <span>🍽️</span>
        <h2>No dishes shared yet</h2>
        <p>Be the first to bring something to the table.</p>
      </div>

      <div v-else class="forum-grid">
        <RouterLink
          v-for="post in posts"
          :key="post.id"
          class="forum-card"
          :to="`/forum/${post.id}`"
        >
          <ForumImage
            v-if="post.imageId"
            :post-id="post.id"
            :image-id="post.imageId"
            :alt="post.title"
          />
          <div v-else class="forum-card__no-image" aria-hidden="true">🍲</div>
          <div class="forum-card__body">
            <div class="forum-card__meta">
              <span class="forum-card__author">
                <i aria-hidden="true">{{ post.author.username.charAt(0) }}</i>
                @{{ post.author.username }}
              </span>
              <time :datetime="post.createdAt">{{ formatDate(post.createdAt) }}</time>
            </div>
            <h2>{{ post.title }}</h2>
            <p>{{ post.content }}</p>
          </div>
        </RouterLink>
      </div>

      <button
        v-if="page < totalPages"
        class="secondary-button forum-load-more"
        type="button"
        :disabled="loading"
        @click="load()"
      >{{ loading ? 'Loading…' : 'Load more' }}</button>
    </section>
  </main>
</template>
