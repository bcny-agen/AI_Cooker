<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppLogo from '../components/AppLogo.vue'
import { useAuthStore } from '../stores/auth'
import { getApiErrorMessage } from '../utils/apiError'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const isSubmitting = ref(false)
const errorMessage = ref('')

async function submit(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    errorMessage.value = '请输入用户名和密码。'
    return
  }
  isSubmitting.value = true
  errorMessage.value = ''
  try {
    await authStore.login({ username: username.value.trim(), password: password.value })
    const requestedRedirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/chat'
    const redirect = requestedRedirect.startsWith('/') && !requestedRedirect.startsWith('//')
      ? requestedRedirect
      : '/chat'
    await router.replace(redirect)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '登录失败，请检查用户名和密码。')
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-intro">
      <div>
        <AppLogo />
        <h1>用手边已有的食材，做出令人惊喜的一餐。</h1>
        <p>
          告诉我们你有哪些食材，也可以上传照片，获取适合你家厨房的实用菜谱。
        </p>
      </div>
      <div class="ingredient-orbit" aria-hidden="true">
        <span>🍅</span><span>🥕</span><span>🥚</span><span>🌿</span>
        <div>AI</div>
      </div>
    </section>

    <section class="auth-panel">
      <form class="auth-card" @submit.prevent="submit">
        <div class="auth-card__heading">
          <span class="eyebrow">欢迎回来</span>
          <h2>登录你的厨房</h2>
          <p>继续之前的菜谱对话。</p>
        </div>

        <div v-if="route.query.registered" class="notice notice--success">
          账号已创建，现在可以登录了。
        </div>
        <div v-if="route.query.reason === 'expired'" class="notice">
          登录状态已过期，请重新登录。
        </div>
        <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>

        <label class="field">
          <span>用户名</span>
          <input
            v-model="username"
            name="username"
            autocomplete="username"
            maxlength="50"
            required
            placeholder="请输入用户名"
          />
        </label>
        <label class="field">
          <span>密码</span>
          <input
            v-model="password"
            name="password"
            type="password"
            autocomplete="current-password"
            maxlength="64"
            required
            placeholder="••••••••"
          />
        </label>

        <button class="primary-button" type="submit" :disabled="isSubmitting">
          <span v-if="isSubmitting" class="spinner spinner--light" />
          {{ isSubmitting ? '正在登录…' : '登录' }}
        </button>

        <p class="auth-switch">第一次使用 AI Cooker？<RouterLink to="/register">创建账号</RouterLink></p>
      </form>
    </section>
  </main>
</template>
