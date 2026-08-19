import { mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { imagesApi } from '../api/images'
import ChatComposer from '../components/ChatComposer.vue'
import { useImageUpload } from './useImageUpload'

vi.mock('../api/images', () => ({
  imagesApi: {
    upload: vi.fn(),
    get: vi.fn(),
  },
}))

describe('image upload UI state', () => {
  it('keeps a local preview and stores the Java-owned imageId', async () => {
    vi.mocked(imagesApi.upload).mockResolvedValue({
      imageId: 'image-42',
      url: 'https://signed.example/image',
      originalFilename: 'ingredients.jpg',
      contentType: 'image/jpeg',
      size: 3,
    })
    const scope = effectScope()
    const upload = scope.run(() => useImageUpload())!
    const file = new File([new Uint8Array([0xff, 0xd8, 0xff])], 'ingredients.jpg', { type: 'image/jpeg' })

    await upload.upload(file)

    expect(upload.previewUrl.value).toBe('blob:local-preview')
    expect(upload.image.value?.imageId).toBe('image-42')
    scope.stop()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:local-preview')
  })

  it('blocks chat submission after a failed upload', async () => {
    vi.mocked(imagesApi.upload).mockRejectedValue(new Error('OSS unavailable'))
    const scope = effectScope()
    const upload = scope.run(() => useImageUpload())!
    const file = new File(['image'], 'ingredients.jpg', { type: 'image/jpeg' })
    await upload.upload(file)

    const wrapper = mount(ChatComposer, {
      props: {
        modelValue: 'Use this image',
        disabled: false,
        sendBlocked: upload.hasUploadError.value,
        uploading: false,
        uploadProgress: 0,
        imageUrl: upload.previewUrl.value,
        uploadError: upload.errorMessage.value,
      },
    })
    await wrapper.get('.send-button').trigger('click')

    expect(upload.hasUploadError.value).toBe(true)
    expect(wrapper.emitted('send')).toBeUndefined()
    scope.stop()
  })
})
