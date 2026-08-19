import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MessageList from './MessageList.vue'

describe('MessageList generated dish images', () => {
  it('renders a generated image card from assistant history', () => {
    const wrapper = mount(MessageList, {
      props: {
        messages: [{
          id: 5,
          role: 'ASSISTANT',
          content: 'Here is the plated dish.',
          imageId: null,
          createdAt: '2026-08-09T12:00:00Z',
          generatedImages: [{
            imageId: 'generated-1',
            url: 'https://signed.example/generated',
            imageModel: 'step-image-edit-2',
            createdAt: '2026-08-09T12:00:00Z',
          }],
        }],
        loading: false,
        sending: false,
        streamStatus: '',
        imageUrls: {},
      },
    })

    expect(wrapper.get('.generated-dish-image img').attributes('src'))
      .toBe('https://signed.example/generated')
    expect(wrapper.text()).toContain('Generated dish preview')
  })

  it('emits retry with the original explicit image request', async () => {
    const wrapper = mount(MessageList, {
      props: {
        messages: [{
          id: 6,
          role: 'ASSISTANT',
          content: 'The text answer remains available.',
          imageId: null,
          createdAt: '2026-08-09T12:00:00Z',
          imageGenerationFailed: true,
          imageRetryPrompt: 'Generate an image of the second dish',
        }],
        loading: false,
        sending: false,
        streamStatus: '',
        imageUrls: {},
      },
    })

    await wrapper.get('.generated-image-error button').trigger('click')

    expect(wrapper.emitted('retryImage')).toEqual([
      ['Generate an image of the second dish'],
    ])
  })
})
