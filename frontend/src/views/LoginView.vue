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
    errorMessage.value = 'Enter your username and password.'
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
    errorMessage.value = getApiErrorMessage(error, 'Login failed. Check your credentials.')
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
        <h1>Cook something wonderful with what you already have.</h1>
        <p>
          Share your ingredients, add a photo, and get practical recipes tailored to your kitchen.
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
          <span class="eyebrow">Welcome back</span>
          <h2>Sign in to your kitchen</h2>
          <p>Continue your recipe conversations.</p>
        </div>

        <div v-if="route.query.registered" class="notice notice--success">
          Account created. You can sign in now.
        </div>
        <div v-if="route.query.reason === 'expired'" class="notice">
          Your session expired. Please sign in again.
        </div>
        <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>

        <label class="field">
          <span>Username</span>
          <input
            v-model="username"
            name="username"
            autocomplete="username"
            maxlength="50"
            required
            placeholder="your_username"
          />
        </label>
        <label class="field">
          <span>Password</span>
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
          {{ isSubmitting ? 'Signing in…' : 'Sign in' }}
        </button>

        <p class="auth-switch">New to AI Cooker? <RouterLink to="/register">Create an account</RouterLink></p>
      </form>
    </section>
  </main>
</template>
