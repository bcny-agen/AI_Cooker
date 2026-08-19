import type { AxiosProgressEvent } from 'axios'

import type { ImageResponse } from '../types/api'
import { http } from './http'

export const imagesApi = {
  async upload(file: File, onProgress?: (percent: number) => void): Promise<ImageResponse> {
    const form = new FormData()
    form.append('file', file)

    const { data } = await http.post<ImageResponse>('/api/images', form, {
      onUploadProgress: (event: AxiosProgressEvent) => {
        if (event.total && onProgress) {
          onProgress(Math.round((event.loaded / event.total) * 100))
        }
      },
    })
    return data
  },

  async get(imageId: string): Promise<ImageResponse> {
    const { data } = await http.get<ImageResponse>(`/api/images/${imageId}`)
    return data
  },
}
