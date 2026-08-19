import type { ModelInfo } from '../types/api'
import { http } from './http'

export const modelsApi = {
  async list(): Promise<ModelInfo[]> {
    const { data } = await http.get<ModelInfo[]>('/api/models')
    return data
  },
}
