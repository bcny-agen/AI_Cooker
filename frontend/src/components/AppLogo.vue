<script setup lang="ts">
defineProps<{ compact?: boolean }>()
</script>

<template>
  <div class="brand" :class="{ 'brand--compact': compact }" aria-label="AI Cooker">
    <span class="brand__mark" aria-hidden="true">
      <svg viewBox="0 0 32 32" role="img">
        <path d="M7 17h18v2a9 9 0 0 1-18 0v-2Z" />
        <path d="M10 14c0-3 2-5 5-5 1-3 5-4 7-1 3 0 5 2 5 5 0 1-.3 2-1 3H8c-.7-.8-1-1.7-1-2.8 0-2.2 1.5-4 3-4.2" />
      </svg>
    </span>
    <span class="brand__text">AI Cooker</span>
  </div>
</template>
