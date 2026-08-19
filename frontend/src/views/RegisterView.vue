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
    errorMessage.value = 'Use 3–50 letters, numbers, dots, hyphens, or underscores.'
    return
  }
  if (password.value.length < 8 || password.value.length > 64) {
    errorMessage.value = 'Password must contain 8–64 characters.'
    return
  }
  if (password.value !== confirmPassword.value) {
    errorMessage.value = 'Passwords do not match.'
    return
  }

  isSubmitting.value = true
  errorMessage.value = ''
  try {
    await authStore.register({ username: username.value, password: password.value })
    await router.replace({ name: 'login', query: { registered: 'true' } })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, 'Your account could not be created.')
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
        <h1>Your personal recipe notebook, powered by your ingredients.</h1>
        <p>Create an account to keep every cooking conversation organized and private.</p>
      </div>
      <div class="ingredient-orbit" aria-hidden="true">
        <span>🥦</span><span>🧅</span><span>🍋</span><span>🍄</span>
        <div>AI</div>
      </div>
    </section>

    <section class="auth-panel">
      <form class="auth-card" @submit.prevent="submit">
        <div class="auth-card__heading">
          <span class="eyebrow">Get started</span>
          <h2>Create your account</h2>
          <p>Save recipes and pick up where you left off.</p>
        </div>

        <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>

        <label class="field">
          <span>Username</span>
          <input
            v-model="username"
            name="username"
            autocomplete="username"
            minlength="3"
            maxlength="50"
            required
            placeholder="your_username"
          />
          <small>Letters, numbers, dots, hyphens, and underscores.</small>
        </label>
        <label class="field">
          <span>Password</span>
          <input
            v-model="password"
            name="password"
            type="password"
            autocomplete="new-password"
            minlength="8"
            maxlength="64"
            required
            placeholder="At least 8 characters"
          />
        </label>
        <label class="field">
          <span>Confirm password</span>
          <input
            v-model="confirmPassword"
            name="confirmPassword"
            type="password"
            autocomplete="new-password"
            required
            placeholder="Repeat your password"
          />
        </label>

        <button class="primary-button" type="submit" :disabled="isSubmitting">
          <span v-if="isSubmitting" class="spinner spinner--light" />
          {{ isSubmitting ? 'Creating account…' : 'Create account' }}
        </button>

        <p class="auth-switch">Already have an account? <RouterLink to="/login">Sign in</RouterLink></p>
      </form>
    </section>
  </main>
</template>
