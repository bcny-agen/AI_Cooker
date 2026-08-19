import type { GeneratedImage } from '../types/api'
import { http } from './http'

export const generatedImagesApi = {
  async get(imageId: string): Promise<GeneratedImage> {
    const { data } = await http.get<GeneratedImage>(`/api/generated-images/${imageId}`)
    return data
  },
}
