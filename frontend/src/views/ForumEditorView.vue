<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { forumApi } from '../api/forum'
import { generatedImagesApi } from '../api/generatedImages'
import { imagesApi } from '../api/images'
import ForumHeader from '../components/ForumHeader.vue'
import ForumImage from '../components/ForumImage.vue'
import { useImageUpload } from '../composables/useImageUpload'
import { getApiErrorMessage } from '../utils/apiError'
import { useForumDraftStore } from '../stores/forumDraft'
import type { ForumImageType, ForumPostRequest } from '../types/api'

const route = useRoute()
const router = useRouter()
const imageUpload = useImageUpload()
const forumDraftStore = useForumDraftStore()

const postId = computed(() => typeof route.params.postId === 'string' ? route.params.postId : null)
const editing = computed(() => Boolean(postId.value))
const title = ref('')
const content = ref('')
const existingImageId = ref<string | null>(null)
const existingImageType = ref<ForumImageType | null>(null)
const loading = ref(false)
const submitting = ref(false)
const errorMessage = ref('')
const canEdit = ref(true)
const generatedDraft = ref(false)
const sourceConversationId = ref<string | null>(null)
const draftDishName = ref('')
const suggestedPreviewUrl = ref('')
const suggestedImageNotice = ref('')
let suggestedRefreshAttempted = false
const selectedImageSourceLabel = computed(() => {
  if (imageUpload.image.value) return 'Your uploaded image'
  if (existingImageType.value === 'AI_GENERATED') return 'AI Generated'
  if (existingImageType.value === 'USER_UPLOAD') return 'Your uploaded image'
  return ''
})

async function initialize(): Promise<void> {
  if (!postId.value) {
    if (route.query.draft === 'generated' && forumDraftStore.draft) {
      const draft = forumDraftStore.draft
      generatedDraft.value = true
      sourceConversationId.value = draft.sourceConversationId
      draftDishName.value = draft.dishName
      title.value = draft.title
      content.value = draft.content
      existingImageId.value = draft.suggestedImageId
      existingImageType.value = draft.suggestedImageType
      if (existingImageId.value) await loadSuggestedPreview()
    } else {
      forumDraftStore.clear()
      if (route.query.draft === 'generated') {
        errorMessage.value = 'This generated draft is no longer available. Generate it again from the conversation.'
      }
    }
    return
  }
  loading.value = true
  try {
    const post = await forumApi.get(postId.value)
    if (!post.isOwner) {
      canEdit.value = false
      errorMessage.value = 'Only the author can edit this post.'
      return
    }
    title.value = post.title
    content.value = post.content
    existingImageId.value = post.imageId
    existingImageType.value = post.imageType
  } catch (error) {
    canEdit.value = false
    errorMessage.value = getApiErrorMessage(error, 'This forum post could not be loaded.')
  } finally {
    loading.value = false
  }
}

async function loadSuggestedPreview(): Promise<void> {
  if (!existingImageId.value) return
  try {
    const image = existingImageType.value === 'AI_GENERATED'
      ? await generatedImagesApi.get(existingImageId.value)
      : await imagesApi.get(existingImageId.value)
    suggestedPreviewUrl.value = image.url
    suggestedImageNotice.value = ''
  } catch {
    existingImageId.value = null
    existingImageType.value = null
    suggestedPreviewUrl.value = ''
    suggestedImageNotice.value = 'The suggested conversation image is no longer available.'
  }
}

async function refreshSuggestedPreview(): Promise<void> {
  if (suggestedRefreshAttempted) {
    existingImageId.value = null
    existingImageType.value = null
    suggestedPreviewUrl.value = ''
    suggestedImageNotice.value = 'The suggested conversation image could not be loaded.'
    return
  }
  suggestedRefreshAttempted = true
  await loadSuggestedPreview()
}

async function selectImage(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const uploaded = await imageUpload.upload(file)
  if (uploaded) {
    existingImageId.value = null
    existingImageType.value = null
    suggestedPreviewUrl.value = ''
  }
}

function removeImage(): void {
  imageUpload.clear()
  existingImageId.value = null
  existingImageType.value = null
  suggestedPreviewUrl.value = ''
}

async function submit(): Promise<void> {
  if (!title.value.trim() || !content.value.trim() || submitting.value) {
    errorMessage.value = 'Add both a title and a description.'
    return
  }
  submitting.value = true
  errorMessage.value = ''
  const selectedImageId = imageUpload.image.value?.imageId ?? existingImageId.value
  const selectedImageType: ForumImageType | null = imageUpload.image.value
    ? 'USER_UPLOAD'
    : selectedImageId
      ? existingImageType.value
      : null
  const request: ForumPostRequest = {
    title: title.value.trim(),
    content: content.value.trim(),
    imageId: selectedImageId,
    imageType: selectedImageType,
    ...(!editing.value && sourceConversationId.value
      ? { sourceConversationId: sourceConversationId.value }
      : {}),
  }
  try {
    const saved = editing.value && postId.value
      ? await forumApi.update(postId.value, request)
      : await forumApi.create(request)
    forumDraftStore.clear()
    await router.replace(`/forum/${saved.id}`)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, 'The forum post could not be saved.')
  } finally {
    submitting.value = false
  }
}

onMounted(initialize)
</script>

<template>
  <main class="forum-shell">
    <ForumHeader />
    <section class="forum-editor-page">
      <RouterLink class="back-link" :to="postId ? `/forum/${postId}` : '/forum'">← Cancel</RouterLink>
      <div class="forum-editor-heading">
        <span class="eyebrow">{{ editing ? 'Update your dish' : 'Bring something to the table' }}</span>
        <h1>{{ editing ? 'Edit forum post' : 'Share a cooked dish' }}</h1>
        <p>Tell the community what you made. Plain text keeps every post safe and easy to read.</p>
      </div>

      <div v-if="generatedDraft" class="generated-draft-notice" role="status">
        <strong>AI-generated draft</strong>
        <span>Review and edit everything before publishing<span v-if="draftDishName"> · Suggested dish: {{ draftDishName }}</span>.</span>
      </div>

      <div v-if="loading" class="forum-state"><span class="spinner" /> Loading post…</div>
      <div v-else-if="!canEdit" class="notice notice--error" role="alert">{{ errorMessage }}</div>
      <form v-else class="forum-editor" @submit.prevent="submit">
        <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>
        <label class="field">
          <span>Dish title</span>
          <input v-model="title" maxlength="160" required placeholder="My tomato and egg dish">
          <small>{{ title.length }}/160</small>
        </label>
        <label class="field">
          <span>Your cooking story</span>
          <textarea
            v-model="content"
            maxlength="20000"
            required
            rows="10"
            placeholder="What did you make, and how did it turn out?"
          />
          <small>{{ content.length }}/20000</small>
        </label>

        <div class="forum-editor__image">
          <div>
            <strong>Dish image</strong>
            <p>Optional · JPEG, PNG, or WebP</p>
          </div>
          <label class="secondary-button file-button">
            <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="imageUpload.isUploading.value" @change="selectImage">
            {{ imageUpload.isUploading.value ? `Uploading ${imageUpload.progress.value}%` : 'Choose image' }}
          </label>
        </div>
        <div v-if="imageUpload.errorMessage.value" class="notice notice--error">{{ imageUpload.errorMessage.value }}</div>
        <div v-if="suggestedImageNotice" class="notice">{{ suggestedImageNotice }}</div>
        <div
          v-if="imageUpload.previewUrl.value || existingImageId"
          class="forum-editor__image-source"
          role="status"
        >
          <strong>Selected image</strong>
          <span>{{ existingImageType === 'AI_GENERATED' && !imageUpload.image.value ? 'AI Generated Dish Image' : 'Your uploaded image' }}</span>
          <small>Source: {{ selectedImageSourceLabel }}</small>
        </div>
        <div v-if="imageUpload.previewUrl.value || existingImageId" class="forum-editor__preview">
          <img v-if="imageUpload.previewUrl.value" :src="imageUpload.previewUrl.value" alt="New dish preview">
          <ForumImage
            v-else-if="existingImageId && postId"
            :post-id="postId"
            :image-id="existingImageId"
            alt="Current dish image"
          />
          <img
            v-else-if="existingImageId && suggestedPreviewUrl"
            :src="suggestedPreviewUrl"
            :alt="existingImageType === 'AI_GENERATED' ? 'AI generated dish image' : 'Suggested uploaded image'"
            @error="refreshSuggestedPreview"
          >
          <button class="text-button" type="button" @click="removeImage">Remove image</button>
        </div>

        <div class="forum-editor__actions">
          <RouterLink class="secondary-button" :to="postId ? `/forum/${postId}` : '/forum'">Cancel</RouterLink>
          <button class="primary-link" type="submit" :disabled="submitting || imageUpload.isUploading.value">
            {{ submitting ? 'Saving…' : editing ? 'Save changes' : 'Publish post' }}
          </button>
        </div>
      </form>
    </section>
  </main>
</template>
