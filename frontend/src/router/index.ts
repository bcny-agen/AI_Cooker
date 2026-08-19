import {
  createMemoryHistory,
  createRouter,
  createWebHistory,
  type RouterHistory,
} from 'vue-router'

import { getAccessToken } from '../utils/authSession'
import ChatView from '../views/ChatView.vue'
import ForumEditorView from '../views/ForumEditorView.vue'
import ForumFeedView from '../views/ForumFeedView.vue'
import ForumPostView from '../views/ForumPostView.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import MemorySettingsView from '../views/MemorySettingsView.vue'

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({
    history,
    routes: [
      { path: '/', redirect: '/chat' },
      { path: '/login', name: 'login', component: LoginView, meta: { guestOnly: true } },
      { path: '/register', name: 'register', component: RegisterView, meta: { guestOnly: true } },
      { path: '/chat', name: 'chat', component: ChatView, meta: { requiresAuth: true } },
      { path: '/settings/memory', name: 'memory-settings', component: MemorySettingsView, meta: { requiresAuth: true } },
      { path: '/forum', name: 'forum', component: ForumFeedView, meta: { requiresAuth: true } },
      { path: '/forum/mine', name: 'forum-mine', component: ForumFeedView, props: { mine: true }, meta: { requiresAuth: true } },
      { path: '/forum/new', name: 'forum-new', component: ForumEditorView, meta: { requiresAuth: true } },
      { path: '/forum/:postId/edit', name: 'forum-edit', component: ForumEditorView, meta: { requiresAuth: true } },
      { path: '/forum/:postId', name: 'forum-post', component: ForumPostView, meta: { requiresAuth: true } },
    ],
  })

  router.beforeEach((to) => {
    const authenticated = Boolean(getAccessToken())
    if (to.meta.requiresAuth && !authenticated) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    if (to.meta.guestOnly && authenticated) {
      return { name: 'chat' }
    }
    return true
  })

  return router
}

export { createMemoryHistory }

export const router = createAppRouter()
