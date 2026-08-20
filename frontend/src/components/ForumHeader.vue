<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import AppLogo from './AppLogo.vue'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const isMemory = computed(() => route.path.startsWith('/settings/'))

async function logout(): Promise<void> {
  authStore.clearSession()
  await router.replace('/login')
}
</script>

<template>
  <aside class="forum-header" aria-label="应用导航">
    <div class="forum-header__top">
      <RouterLink class="forum-header__brand" to="/chat" aria-label="AI Cooker 对话">
        <AppLogo compact />
      </RouterLink>
    </div>

    <nav class="sidebar-nav forum-header__navigation" aria-label="主导航">
      <RouterLink to="/chat">对话</RouterLink>
      <RouterLink to="/forum">社区</RouterLink>
      <RouterLink to="/settings/memory">记忆</RouterLink>
    </nav>

    <div class="forum-header__context">
      <div class="sidebar__label">{{ isMemory ? '个性化设置' : '美食社区' }}</div>

      <template v-if="!isMemory">
        <RouterLink class="new-chat-button forum-share-link" to="/forum/new">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          分享菜品
        </RouterLink>
        <p class="forum-header__hint">把菜谱灵感变成成果，与社区里的烹饪爱好者一起分享。</p>
        <nav class="forum-section-nav" aria-label="社区导航">
          <RouterLink to="/forum" exact-active-class="forum-section-nav__active">社区餐桌</RouterLink>
          <RouterLink to="/forum/mine" exact-active-class="forum-section-nav__active">我分享的菜品</RouterLink>
        </nav>
      </template>

      <template v-else>
        <p class="forum-header__hint">查看 AI Cooker 会在不同对话间持续使用的偏好。</p>
        <nav class="forum-section-nav" aria-label="长期记忆导航">
          <RouterLink to="/settings/memory" class="forum-section-nav__active">已保存的偏好</RouterLink>
        </nav>
      </template>
    </div>

    <button class="logout-button forum-header__logout" type="button" @click="logout">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" />
      </svg>
      退出登录
    </button>
  </aside>
</template>
