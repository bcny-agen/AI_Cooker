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
  <aside class="forum-header" aria-label="Application navigation">
    <div class="forum-header__top">
      <RouterLink class="forum-header__brand" to="/chat" aria-label="AI Cooker chat">
        <AppLogo compact />
      </RouterLink>
    </div>

    <nav class="sidebar-nav forum-header__navigation" aria-label="Main navigation">
      <RouterLink to="/chat">Chat</RouterLink>
      <RouterLink to="/forum">Forum</RouterLink>
      <RouterLink to="/settings/memory">Memory</RouterLink>
    </nav>

    <div class="forum-header__context">
      <div class="sidebar__label">{{ isMemory ? 'Personalization' : 'Forum' }}</div>

      <template v-if="!isMemory">
        <RouterLink class="new-chat-button forum-share-link" to="/forum/new">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          Share a dish
        </RouterLink>
        <p class="forum-header__hint">Move naturally from recipe ideas to dishes shared by the community.</p>
        <nav class="forum-section-nav" aria-label="Forum navigation">
          <RouterLink to="/forum" exact-active-class="forum-section-nav__active">Community table</RouterLink>
          <RouterLink to="/forum/mine" exact-active-class="forum-section-nav__active">My shared dishes</RouterLink>
        </nav>
      </template>

      <template v-else>
        <p class="forum-header__hint">Review the preferences AI Cooker carries between conversations.</p>
        <nav class="forum-section-nav" aria-label="Memory navigation">
          <RouterLink to="/settings/memory" class="forum-section-nav__active">Saved preferences</RouterLink>
        </nav>
      </template>
    </div>

    <button class="logout-button forum-header__logout" type="button" @click="logout">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" />
      </svg>
      Log out
    </button>
  </aside>
</template>
