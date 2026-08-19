import { afterEach, describe, expect, it, vi } from 'vitest'

import { chatApi } from './chat'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('chat streaming errors', () => {
  it('uses the safe Java API error message when the stream cannot start', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ message: 'The selected model is temporarily unavailable.' }),
      {
        status: 502,
        headers: { 'Content-Type': 'application/json' },
      },
    )))

    await expect(chatApi.stream(
      { message: 'What can I cook?' },
      vi.fn(),
    )).rejects.toThrow('The selected model is temporarily unavailable.')
  })

  it('keeps a safe fallback for a non-JSON failure response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      'Bad gateway',
      { status: 502, headers: { 'Content-Type': 'text/plain' } },
    )))

    await expect(chatApi.stream(
      { message: 'What can I cook?' },
      vi.fn(),
    )).rejects.toThrow('AI Cooker could not start the response stream.')
  })
})
