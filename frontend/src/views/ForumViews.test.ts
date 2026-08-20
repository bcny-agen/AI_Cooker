import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { forumApi } from '../api/forum'
import { generatedImagesApi } from '../api/generatedImages'
import { imagesApi } from '../api/images'
import { createAppRouter, createMemoryHistory } from '../router'
import type { ForumPost } from '../types/api'
import { saveAccessToken } from '../utils/authSession'
import { useForumDraftStore } from '../stores/forumDraft'
import ForumEditorView from './ForumEditorView.vue'
import ForumFeedView from './ForumFeedView.vue'
import ForumPostView from './ForumPostView.vue'

vi.mock('../api/forum', () => ({
  forumApi: {
    list: vi.fn(),
    mine: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    image: vi.fn(),
    generateDraft: vi.fn(),
  },
}))
vi.mock('../api/images', () => ({
  imagesApi: {
    upload: vi.fn(),
    get: vi.fn(),
  },
}))
vi.mock('../api/generatedImages', () => ({
  generatedImagesApi: {
    get: vi.fn(),
  },
}))

const ownerPost: ForumPost = {
  id: 'post-1',
  title: 'Tomato and egg',
  content: 'A simple dinner.\n<script>unsafe()</script>',
  author: { id: 'user-1', username: 'alice' },
  imageId: 'image-1',
  imageType: 'USER_UPLOAD',
  createdAt: '2026-08-08T01:00:00Z',
  updatedAt: '2026-08-08T01:00:00Z',
  isOwner: true,
}

function page(content: ForumPost[]) {
  return { content, page: 0, size: 12, totalElements: content.length, totalPages: 1 }
}

async function mountAt(
  path: string,
  component: typeof ForumFeedView | typeof ForumPostView | typeof ForumEditorView,
): Promise<{ wrapper: VueWrapper; router: ReturnType<typeof createAppRouter> }> {
  saveAccessToken('jwt')
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('forum views', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(forumApi.list).mockResolvedValue(page([ownerPost]))
    vi.mocked(forumApi.mine).mockResolvedValue(page([ownerPost]))
    vi.mocked(forumApi.get).mockResolvedValue(ownerPost)
    vi.mocked(forumApi.image).mockResolvedValue({
      imageId: 'image-1',
      url: 'https://signed.example/forum-image',
      originalFilename: 'dish.jpg',
      contentType: 'image/jpeg',
      size: 123,
    })
    vi.mocked(forumApi.create).mockResolvedValue(ownerPost)
    vi.mocked(forumApi.update).mockResolvedValue(ownerPost)
    vi.mocked(forumApi.remove).mockResolvedValue()
  })

  it('loads the forum feed and obtains a post-scoped signed preview', async () => {
    const { wrapper } = await mountAt('/forum', ForumFeedView)

    expect(forumApi.list).toHaveBeenCalledWith(0)
    expect(wrapper.get('.forum-card h2').text()).toBe('Tomato and egg')
    expect(wrapper.get('.forum-card__body > p').text()).toContain('<script>unsafe()</script>')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(forumApi.image).toHaveBeenCalledWith('post-1')
    expect(wrapper.get('.forum-image img').attributes('src')).toBe('https://signed.example/forum-image')
  })

  it('shows owner controls, deletes an owned post, and hides controls from other users', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const owner = await mountAt('/forum/post-1', ForumPostView)

    expect(owner.wrapper.get('.forum-detail__text').text()).toContain('A simple dinner.')
    expect(owner.wrapper.find('script').exists()).toBe(false)
    expect(owner.wrapper.find('.forum-owner-actions').exists()).toBe(true)
    await owner.wrapper.get('.danger-button').trigger('click')
    await flushPromises()
    expect(forumApi.remove).toHaveBeenCalledWith('post-1')
    expect(owner.router.currentRoute.value.path).toBe('/forum/mine')
    owner.wrapper.unmount()

    vi.mocked(forumApi.get).mockResolvedValue({ ...ownerPost, isOwner: false })
    const viewer = await mountAt('/forum/post-1', ForumPostView)
    expect(viewer.wrapper.find('.forum-owner-actions').exists()).toBe(false)
  })

  it('uploads an image before creating a manual post and sends only its imageId', async () => {
    vi.mocked(imagesApi.upload).mockResolvedValue({
      imageId: 'uploaded-image',
      url: 'https://signed.example/owner-preview',
      originalFilename: 'dinner.jpg',
      contentType: 'image/jpeg',
      size: 42,
    })
    const { wrapper, router } = await mountAt('/forum/new', ForumEditorView)
    await wrapper.get('input[maxlength="160"]').setValue('My dinner')
    await wrapper.get('textarea').setValue('It turned out well.')
    const file = new File([new Uint8Array([0xff, 0xd8, 0xff])], 'dinner.jpg', { type: 'image/jpeg' })
    const input = wrapper.get<HTMLInputElement>('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(imagesApi.upload).toHaveBeenCalledWith(file, expect.any(Function))
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(forumApi.create).toHaveBeenCalledWith({
      title: 'My dinner',
      content: 'It turned out well.',
      imageId: 'uploaded-image',
      imageType: 'USER_UPLOAD',
    })
    expect(wrapper.get('.forum-editor__image-source').text())
      .toContain('来源：你上传的图片')
    expect(router.currentRoute.value.path).toBe('/forum/post-1')
  })

  it('loads and updates an owned post through the edit route', async () => {
    const updated = { ...ownerPost, title: 'Updated tomato and egg' }
    vi.mocked(forumApi.update).mockResolvedValue(updated)
    const { wrapper, router } = await mountAt('/forum/post-1/edit', ForumEditorView)

    expect(wrapper.get<HTMLInputElement>('input[maxlength="160"]').element.value)
      .toBe('Tomato and egg')
    await wrapper.get('input[maxlength="160"]').setValue(updated.title)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(forumApi.update).toHaveBeenCalledWith('post-1', {
      title: updated.title,
      content: ownerPost.content,
      imageId: 'image-1',
      imageType: 'USER_UPLOAD',
    })
    expect(router.currentRoute.value.path).toBe('/forum/post-1')
  })

  it('keeps the forum usable when a signed image preview fails', async () => {
    vi.mocked(forumApi.image).mockRejectedValue(new Error('missing object'))
    const { wrapper } = await mountAt('/forum', ForumFeedView)

    expect(wrapper.get('.forum-image__state').text()).toBe('图片暂不可用')
    expect(wrapper.get('.forum-card h2').text()).toBe('Tomato and egg')
  })

  it('prefills an editable generated draft and keeps its suggested image on explicit publish', async () => {
    saveAccessToken('jwt')
    const pinia = createPinia()
    setActivePinia(pinia)
    useForumDraftStore().setDraft({
      sourceConversationId: 'conversation-1',
      title: 'Generated tomato dish',
      content: 'Generated but fully editable content.',
      dishName: 'Tomato dish',
      suggestedImageId: 'suggested-image',
      suggestedImageType: 'AI_GENERATED',
      modelId: 'STEP_FLASH_3_7',
    })
    vi.mocked(generatedImagesApi.get).mockResolvedValue({
      imageId: 'suggested-image',
      url: 'https://signed.example/suggested',
      imageModel: 'step-image-edit-2',
      createdAt: '2026-08-09T00:00:00Z',
    })
    const router = createAppRouter(createMemoryHistory())
    await router.push('/forum/new?draft=generated')
    await router.isReady()
    const wrapper = mount(ForumEditorView, { global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.get('.generated-draft-notice').text()).toContain('AI 生成的草稿')
    expect(wrapper.get<HTMLInputElement>('input[maxlength="160"]').element.value)
      .toBe('Generated tomato dish')
    expect(wrapper.get<HTMLTextAreaElement>('textarea').element.value)
      .toBe('Generated but fully editable content.')
    expect(wrapper.get('img[alt="AI 生成的菜品图片"]').attributes('src'))
      .toBe('https://signed.example/suggested')
    expect(wrapper.get('.forum-editor__image-source').text())
      .toContain('来源：AI 生成图片')

    await wrapper.get('input[maxlength="160"]').setValue('User edited title')
    await wrapper.get('textarea').setValue('User edited content.')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(forumApi.create).toHaveBeenCalledWith({
      title: 'User edited title',
      content: 'User edited content.',
      imageId: 'suggested-image',
      imageType: 'AI_GENERATED',
      sourceConversationId: 'conversation-1',
    })
    expect(useForumDraftStore().draft).toBeNull()
  })

  it('lets the user remove or replace a suggested conversation image', async () => {
    saveAccessToken('jwt')
    const pinia = createPinia()
    setActivePinia(pinia)
    const draftStore = useForumDraftStore()
    draftStore.setDraft({
      sourceConversationId: 'conversation-1',
      title: 'Generated dish',
      content: 'Generated content.',
      dishName: 'Dish',
      suggestedImageId: 'suggested-image',
      suggestedImageType: 'AI_GENERATED',
      modelId: 'STEP_FLASH_3_7',
    })
    vi.mocked(generatedImagesApi.get).mockResolvedValue({
      imageId: 'suggested-image',
      url: 'https://signed.example/suggested',
      imageModel: 'step-image-edit-2',
      createdAt: '2026-08-09T00:00:00Z',
    })
    vi.mocked(imagesApi.upload).mockResolvedValue({
      imageId: 'replacement-image',
      url: 'https://signed.example/replacement',
      originalFilename: 'new.jpg',
      contentType: 'image/jpeg',
      size: 11,
    })
    const router = createAppRouter(createMemoryHistory())
    await router.push('/forum/new?draft=generated')
    await router.isReady()
    const wrapper = mount(ForumEditorView, { global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('.forum-editor__preview .text-button').trigger('click')
    expect(wrapper.find('.forum-editor__preview').exists()).toBe(false)

    const file = new File([new Uint8Array([0xff, 0xd8, 0xff])], 'new.jpg', { type: 'image/jpeg' })
    const fileInput = wrapper.get<HTMLInputElement>('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { configurable: true, value: [file] })
    await fileInput.trigger('change')
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(forumApi.create).toHaveBeenCalledWith(expect.objectContaining({
      imageId: 'replacement-image',
      imageType: 'USER_UPLOAD',
      sourceConversationId: 'conversation-1',
    }))
  })

  it('can remove an AI generated draft image before publishing', async () => {
    saveAccessToken('jwt')
    const pinia = createPinia()
    setActivePinia(pinia)
    useForumDraftStore().setDraft({
      sourceConversationId: 'conversation-1',
      title: 'Generated dish',
      content: 'Generated content.',
      dishName: 'Dish',
      suggestedImageId: 'generated-image',
      suggestedImageType: 'AI_GENERATED',
      modelId: 'STEP_FLASH_3_7',
    })
    vi.mocked(generatedImagesApi.get).mockResolvedValue({
      imageId: 'generated-image',
      url: 'https://signed.example/generated',
      imageModel: 'step-image-edit-2',
      createdAt: '2026-08-09T00:00:00Z',
    })
    const router = createAppRouter(createMemoryHistory())
    await router.push('/forum/new?draft=generated')
    await router.isReady()
    const wrapper = mount(ForumEditorView, { global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('.forum-editor__preview .text-button').trigger('click')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(forumApi.create).toHaveBeenCalledWith({
      title: 'Generated dish',
      content: 'Generated content.',
      imageId: null,
      imageType: null,
      sourceConversationId: 'conversation-1',
    })
  })
})
