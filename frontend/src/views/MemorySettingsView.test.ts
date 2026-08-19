import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { memoriesApi } from '../api/memories'
import type { Memory } from '../types/api'
import MemorySettingsView from './MemorySettingsView.vue'

vi.mock('../api/memories', () => ({
  memoriesApi: {
    list: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  },
}))

const coriander: Memory = {
  id: 'memory-1',
  memoryType: 'DIETARY_RESTRICTION',
  key: 'coriander',
  value: 'avoid',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
}

describe('MemorySettingsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(memoriesApi.list).mockResolvedValue([coriander])
  })

  it('loads and groups understandable memory records', async () => {
    const wrapper = mount(MemorySettingsView, {
      global: { stubs: { ForumHeader: true } },
    })
    await flushPromises()

    expect(memoriesApi.list).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Dietary restrictions')
    expect(wrapper.text()).toContain('coriander')
    expect(wrapper.text()).toContain('avoid')
    expect(wrapper.text()).not.toContain('confidence')
  })

  it('edits a memory through the authenticated API', async () => {
    vi.mocked(memoriesApi.update).mockResolvedValue({
      ...coriander,
      value: 'strongly avoid',
      updatedAt: '2026-01-02T00:00:00Z',
    })
    const wrapper = mount(MemorySettingsView, {
      global: { stubs: { ForumHeader: true } },
    })
    await flushPromises()

    await wrapper.get('button.text-button').trigger('click')
    const inputs = wrapper.findAll('input')
    await inputs[1].setValue('strongly avoid')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(memoriesApi.update).toHaveBeenCalledWith('memory-1', {
      memoryType: 'DIETARY_RESTRICTION',
      key: 'coriander',
      value: 'strongly avoid',
    })
    expect(wrapper.text()).toContain('strongly avoid')
  })

  it('deletes a memory so it no longer appears', async () => {
    vi.mocked(memoriesApi.remove).mockResolvedValue()
    const wrapper = mount(MemorySettingsView, {
      global: { stubs: { ForumHeader: true } },
    })
    await flushPromises()

    await wrapper.get('button.danger-button').trigger('click')
    await flushPromises()

    expect(memoriesApi.remove).toHaveBeenCalledWith('memory-1')
    expect(wrapper.text()).toContain('Nothing saved yet')
    expect(wrapper.text()).not.toContain('coriander')
  })
})
