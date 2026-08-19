<script setup lang="ts">
import { computed } from 'vue'

import { renderAssistantMarkdown } from '../utils/markdown'

const props = defineProps<{
  content: string
  streaming?: boolean
}>()

const rendered = computed(() => renderAssistantMarkdown(props.content))
</script>

<template>
  <div
    class="message-content markdown-content"
    :class="{ 'message-content--streaming': streaming }"
    v-html="rendered"
  />
</template>
