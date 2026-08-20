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
  return new Date(value).toLocaleString('zh-CN', {
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
    errorMessage.value = getApiErrorMessage(error, '社区内容加载失败。')
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
          <span class="eyebrow">社区里的烹饪成果</span>
          <h1>{{ mine ? '我分享的菜品' : 'AI Cooker 美食社区' }}</h1>
          <p>{{ mine ? '查看和管理你分享过的菜品。' : '看看其他家庭厨师做了什么，也分享你的烹饪成果。' }}</p>
        </div>
        <RouterLink class="primary-link" to="/forum/new">分享菜品</RouterLink>
      </div>

      <nav class="forum-tabs" aria-label="社区内容分类">
        <RouterLink to="/forum" exact-active-class="forum-tabs__active">社区动态</RouterLink>
        <RouterLink to="/forum/mine" exact-active-class="forum-tabs__active">我的帖子</RouterLink>
      </nav>

      <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>
      <div v-if="loading && posts.length === 0" class="forum-state"><span class="spinner" /> 正在加载菜品…</div>
      <div v-else-if="posts.length === 0" class="forum-state forum-state--empty">
        <span>🍽️</span>
        <h2>还没有人分享菜品</h2>
        <p>来分享社区里的第一道菜吧。</p>
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
      >{{ loading ? '正在加载…' : '加载更多' }}</button>
    </section>
  </main>
</template>
