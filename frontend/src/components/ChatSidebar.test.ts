import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import type { Conversation } from '../types/api'
import ChatSidebar from './ChatSidebar.vue'

const conversation: Conversation = {
  id: 'conversation-1',
  title: 'Eggs and tomatoes',
  modelId: 'STEP_FLASH_3_7',
  createdAt: '2026-08-01T00:00:00Z',
  updatedAt: '2026-08-01T00:01:00Z',
}

function mountSidebar() {
  return mount(ChatSidebar, {
    attachTo: document.body,
    props: {
      conversations: [conversation],
      activeConversationId: conversation.id,
      loading: false,
      open: true,
      busy: false,
    },
    global: {
      stubs: {
        RouterLink: { template: '<a><slot /></a>' },
        AppLogo: true,
      },
    },
  })
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('ChatSidebar conversation management', () => {
  it('opens the actions menu without selecting the conversation', async () => {
    const wrapper = mountSidebar()
    await wrapper.get(`[aria-label="Actions for ${conversation.title}"]`).trigger('click')

    expect(wrapper.emitted('select')).toBeUndefined()
    expect(wrapper.get('[role="menu"]').text()).toContain('Rename')
    expect(wrapper.get('[role="menu"]').text()).toContain('Delete')
  })

  it('prefills rename, submits on Enter, and preserves the conversation id', async () => {
    const wrapper = mountSidebar()
    await wrapper.get(`[aria-label="Actions for ${conversation.title}"]`).trigger('click')
    await wrapper.get('[role="menuitem"]').trigger('click')
    const input = document.body.querySelector<HTMLInputElement>('.conversation-dialog__field input')

    expect(input?.value).toBe(conversation.title)
    if (!input) throw new Error('Rename input was not rendered')
    input.value = 'Summer tomato dinner'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('rename')).toEqual([[conversation.id, 'Summer tomato dinner']])
  })

  it('cancels rename on Escape without emitting a change', async () => {
    const wrapper = mountSidebar()
    await wrapper.get(`[aria-label="Actions for ${conversation.title}"]`).trigger('click')
    await wrapper.get('[role="menuitem"]').trigger('click')
    const backdrop = document.body.querySelector<HTMLElement>('.conversation-dialog-backdrop')
    backdrop?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('rename')).toBeUndefined()
    expect(document.body.querySelector('.conversation-dialog')).toBeNull()
  })

  it('requires explicit confirmation before emitting delete', async () => {
    const wrapper = mountSidebar()
    await wrapper.get(`[aria-label="Actions for ${conversation.title}"]`).trigger('click')
    await wrapper.findAll('[role="menuitem"]')[1]!.trigger('click')

    expect(wrapper.emitted('delete')).toBeUndefined()
    const dialog = document.body.querySelector<HTMLElement>('[role="alertdialog"]')
    expect(dialog?.textContent).toContain('Published forum posts and uploaded images will remain')
    const confirm = [...(dialog?.querySelectorAll('button') ?? [])]
      .find((button) => button.textContent?.includes('Delete permanently'))
    confirm?.click()
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('delete')).toEqual([[conversation.id]])
  })
})
