import type { ForumDraft, ForumPost, ForumPostRequest, ImageResponse, PageResponse } from '../types/api'
import { http } from './http'

export const forumApi = {
  async list(page = 0, size = 12): Promise<PageResponse<ForumPost>> {
    const { data } = await http.get<PageResponse<ForumPost>>('/api/forum/posts', {
      params: { page, size },
    })
    return data
  },

  async mine(page = 0, size = 12): Promise<PageResponse<ForumPost>> {
    const { data } = await http.get<PageResponse<ForumPost>>('/api/forum/posts/mine', {
      params: { page, size },
    })
    return data
  },

  async get(postId: string): Promise<ForumPost> {
    const { data } = await http.get<ForumPost>(`/api/forum/posts/${postId}`)
    return data
  },

  async create(request: ForumPostRequest): Promise<ForumPost> {
    const { data } = await http.post<ForumPost>('/api/forum/posts', request)
    return data
  },

  async update(postId: string, request: ForumPostRequest): Promise<ForumPost> {
    const { data } = await http.patch<ForumPost>(`/api/forum/posts/${postId}`, request)
    return data
  },

  async remove(postId: string): Promise<void> {
    await http.delete(`/api/forum/posts/${postId}`)
  },

  async image(postId: string): Promise<ImageResponse> {
    const { data } = await http.get<ImageResponse>(`/api/forum/posts/${postId}/image`)
    return data
  },

  async generateDraft(conversationId: string): Promise<ForumDraft> {
    const { data } = await http.post<ForumDraft>(
      `/api/forum/drafts/from-conversation/${conversationId}`,
    )
    return data
  },
}
