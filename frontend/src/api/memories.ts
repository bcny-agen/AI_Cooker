import type { Memory, UpdateMemoryRequest } from '../types/api'
import { http } from './http'

export const memoriesApi = {
  async list(): Promise<Memory[]> {
    const { data } = await http.get<Memory[]>('/api/memories')
    return data
  },

  async update(memoryId: string, request: UpdateMemoryRequest): Promise<Memory> {
    const { data } = await http.patch<Memory>(`/api/memories/${memoryId}`, request)
    return data
  },

  async remove(memoryId: string): Promise<void> {
    await http.delete(`/api/memories/${memoryId}`)
  },
}
