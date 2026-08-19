import type { ChatMessage, Conversation, PageResponse } from '../types/api'
import { http } from './http'

export const conversationsApi = {
  async list(page = 0, size = 100): Promise<PageResponse<Conversation>> {
    const { data } = await http.get<PageResponse<Conversation>>('/api/conversations', {
      params: { page, size },
    })
    return data
  },

  async messages(conversationId: string, page = 0, size = 100): Promise<PageResponse<ChatMessage>> {
    const { data } = await http.get<PageResponse<ChatMessage>>(
      `/api/conversations/${conversationId}/messages`,
      { params: { page, size } },
    )
    return data
  },

  async get(conversationId: string): Promise<Conversation> {
    const { data } = await http.get<Conversation>(`/api/conversations/${conversationId}`)
    return data
  },

  async changeModel(conversationId: string, modelId: Conversation['modelId']): Promise<Conversation> {
    const { data } = await http.patch<Conversation>(`/api/conversations/${conversationId}/model`, { modelId })
    return data
  },

  async rename(conversationId: string, title: string): Promise<Conversation> {
    const { data } = await http.patch<Conversation>(`/api/conversations/${conversationId}`, { title })
    return data
  },

  async delete(conversationId: string): Promise<void> {
    await http.delete(`/api/conversations/${conversationId}`)
  },
}
