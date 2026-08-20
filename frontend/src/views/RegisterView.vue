<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppLogo from '../components/AppLogo.vue'
import { useAuthStore } from '../stores/auth'
import { getApiErrorMessage } from '../utils/apiError'

const authStore = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const isSubmitting = ref(false)
const errorMessage = ref('')

const usernameValid = computed(() => /^[A-Za-z0-9][A-Za-z0-9_.-]{2,49}$/.test(username.value))

async function submit(): Promise<void> {
  if (!usernameValid.value) {
    errorMessage.value = '用户名需为 3–50 位，只能包含英文字母、数字、点、连字符或下划线。'
    return
  }
  if (password.value.length < 8 || password.value.length > 64) {
    errorMessage.value = '密码长度需为 8–64 个字符。'
    return
  }
  if (password.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的密码不一致。'
    return
  }

  isSubmitting.value = true
  errorMessage.value = ''
  try {
    await authStore.register({ username: username.value, password: password.value })
    await router.replace({ name: 'login', query: { registered: 'true' } })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '账号创建失败，请稍后重试。')
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
        <h1>根据手边食材，建立你的专属菜谱笔记。</h1>
        <p>创建账号，安全整理每一次烹饪对话与灵感。</p>
      </div>
      <div class="ingredient-orbit" aria-hidden="true">
        <span>🥦</span><span>🧅</span><span>🍋</span><span>🍄</span>
        <div>AI</div>
      </div>
    </section>

    <section class="auth-panel">
      <form class="auth-card" @submit.prevent="submit">
        <div class="auth-card__heading">
          <span class="eyebrow">开始使用</span>
          <h2>创建账号</h2>
          <p>保存菜谱，随时接着上次的对话继续。</p>
        </div>

        <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>

        <label class="field">
          <span>用户名</span>
          <input
            v-model="username"
            name="username"
            autocomplete="username"
            minlength="3"
            maxlength="50"
            required
            placeholder="请输入用户名"
          />
          <small>支持英文字母、数字、点、连字符和下划线。</small>
        </label>
        <label class="field">
          <span>密码</span>
          <input
            v-model="password"
            name="password"
            type="password"
            autocomplete="new-password"
            minlength="8"
            maxlength="64"
            required
            placeholder="至少 8 个字符"
          />
        </label>
        <label class="field">
          <span>确认密码</span>
          <input
            v-model="confirmPassword"
            name="confirmPassword"
            type="password"
            autocomplete="new-password"
            required
            placeholder="请再次输入密码"
          />
        </label>

        <button class="primary-button" type="submit" :disabled="isSubmitting">
          <span v-if="isSubmitting" class="spinner spinner--light" />
          {{ isSubmitting ? '正在创建…' : '创建账号' }}
        </button>

        <p class="auth-switch">已有账号？<RouterLink to="/login">立即登录</RouterLink></p>
      </form>
    </section>
  </main>
</template>
