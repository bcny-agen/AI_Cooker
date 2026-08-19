import { ref } from 'vue'
import { defineStore } from 'pinia'

import type { ForumDraft } from '../types/api'

export const useForumDraftStore = defineStore('forumDraft', () => {
  const draft = ref<ForumDraft | null>(null)

  function setDraft(value: ForumDraft): void {
    draft.value = value
  }

  function clear(): void {
    draft.value = null
  }

  return { draft, setDraft, clear }
})
