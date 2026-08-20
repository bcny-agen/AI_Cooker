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
  if (imageUpload.image.value) return '你上传的图片'
  if (existingImageType.value === 'AI_GENERATED') return 'AI 生成图片'
  if (existingImageType.value === 'USER_UPLOAD') return '你上传的图片'
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
        errorMessage.value = '这份生成的草稿已失效，请返回对话重新生成。'
      }
    }
    return
  }
  loading.value = true
  try {
    const post = await forumApi.get(postId.value)
    if (!post.isOwner) {
      canEdit.value = false
      errorMessage.value = '只有作者本人可以编辑这篇帖子。'
      return
    }
    title.value = post.title
    content.value = post.content
    existingImageId.value = post.imageId
    existingImageType.value = post.imageType
  } catch (error) {
    canEdit.value = false
    errorMessage.value = getApiErrorMessage(error, '这篇社区帖子加载失败。')
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
    suggestedImageNotice.value = '对话中建议使用的图片已失效。'
  }
}

async function refreshSuggestedPreview(): Promise<void> {
  if (suggestedRefreshAttempted) {
    existingImageId.value = null
    existingImageType.value = null
    suggestedPreviewUrl.value = ''
    suggestedImageNotice.value = '无法加载对话中建议使用的图片。'
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
    errorMessage.value = '请填写菜品标题和烹饪分享。'
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
    errorMessage.value = getApiErrorMessage(error, '社区帖子保存失败。')
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
      <RouterLink class="back-link" :to="postId ? `/forum/${postId}` : '/forum'">← 取消</RouterLink>
      <div class="forum-editor-heading">
        <span class="eyebrow">{{ editing ? '更新你的菜品' : '端上你的拿手菜' }}</span>
        <h1>{{ editing ? '编辑社区帖子' : '分享烹饪成果' }}</h1>
        <p>告诉大家你做了什么。使用纯文本，让每篇帖子都安全、清晰、易读。</p>
      </div>

      <div v-if="generatedDraft" class="generated-draft-notice" role="status">
        <strong>AI 生成的草稿</strong>
        <span>发布前请检查并编辑全部内容<span v-if="draftDishName"> · 建议菜品：{{ draftDishName }}</span>。</span>
      </div>

      <div v-if="loading" class="forum-state"><span class="spinner" /> 正在加载帖子…</div>
      <div v-else-if="!canEdit" class="notice notice--error" role="alert">{{ errorMessage }}</div>
      <form v-else class="forum-editor" @submit.prevent="submit">
        <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>
        <label class="field">
          <span>菜品标题</span>
          <input v-model="title" maxlength="160" required placeholder="例如：家常番茄炒蛋">
          <small>{{ title.length }}/160</small>
        </label>
        <label class="field">
          <span>烹饪分享</span>
          <textarea
            v-model="content"
            maxlength="20000"
            required
            rows="10"
            placeholder="你做了什么？味道和成品怎么样？"
          />
          <small>{{ content.length }}/20000</small>
        </label>

        <div class="forum-editor__image">
          <div>
            <strong>菜品图片</strong>
            <p>选填 · 支持 JPEG、PNG 或 WebP</p>
          </div>
          <label class="secondary-button file-button">
            <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="imageUpload.isUploading.value" @change="selectImage">
            {{ imageUpload.isUploading.value ? `正在上传 ${imageUpload.progress.value}%` : '选择图片' }}
          </label>
        </div>
        <div v-if="imageUpload.errorMessage.value" class="notice notice--error">{{ imageUpload.errorMessage.value }}</div>
        <div v-if="suggestedImageNotice" class="notice">{{ suggestedImageNotice }}</div>
        <div
          v-if="imageUpload.previewUrl.value || existingImageId"
          class="forum-editor__image-source"
          role="status"
        >
          <strong>已选择的图片</strong>
          <span>{{ existingImageType === 'AI_GENERATED' && !imageUpload.image.value ? 'AI 生成的菜品图片' : '你上传的图片' }}</span>
          <small>来源：{{ selectedImageSourceLabel }}</small>
        </div>
        <div v-if="imageUpload.previewUrl.value || existingImageId" class="forum-editor__preview">
          <img v-if="imageUpload.previewUrl.value" :src="imageUpload.previewUrl.value" alt="新菜品预览图">
          <ForumImage
            v-else-if="existingImageId && postId"
            :post-id="postId"
            :image-id="existingImageId"
            alt="当前菜品图片"
          />
          <img
            v-else-if="existingImageId && suggestedPreviewUrl"
            :src="suggestedPreviewUrl"
            :alt="existingImageType === 'AI_GENERATED' ? 'AI 生成的菜品图片' : '建议使用的上传图片'"
            @error="refreshSuggestedPreview"
          >
          <button class="text-button" type="button" @click="removeImage">移除图片</button>
        </div>

        <div class="forum-editor__actions">
          <RouterLink class="secondary-button" :to="postId ? `/forum/${postId}` : '/forum'">取消</RouterLink>
          <button class="primary-link" type="submit" :disabled="submitting || imageUpload.isUploading.value">
            {{ submitting ? '正在保存…' : editing ? '保存修改' : '发布帖子' }}
          </button>
        </div>
      </form>
    </section>
  </main>
</template>
