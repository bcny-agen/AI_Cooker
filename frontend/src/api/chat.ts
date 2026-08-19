import type { ChatRequest, ChatResponse, ChatStreamEvent } from '../types/api'
import { getAccessToken, notifyUnauthorized } from '../utils/authSession'
import { API_BASE_URL, http } from './http'

function parseEvent(block: string): ChatStreamEvent | null {
  const data = block
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trimStart())
    .join('\n')
  if (!data) return null

  const event = JSON.parse(data) as Partial<ChatStreamEvent>
  if (!event.type || ![
    'status', 'token', 'generated_image', 'image_error', 'done', 'error',
  ].includes(event.type)) {
    throw new Error('AI Cooker returned an unsupported streaming event.')
  }
  if (!event.conversationId) {
    throw new Error('AI Cooker returned a streaming event without a conversation ID.')
  }
  return event as ChatStreamEvent
}

async function stream(
  request: ChatRequest,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getAccessToken()
  const response = await fetch(new URL('/api/chat/stream', API_BASE_URL), {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(request),
    signal,
  })

  if (response.status === 401) {
    notifyUnauthorized()
  }
  if (!response.ok) {
    let message = 'AI Cooker could not start the response stream.'
    try {
      const errorBody = await response.json() as { message?: unknown }
      if (typeof errorBody.message === 'string' && errorBody.message.trim()) {
        message = errorBody.message
      }
    } catch {
      // The upstream response was not JSON; keep the user-safe fallback.
    }
    throw new Error(message)
  }
  if (!response.body) {
    throw new Error('Streaming is not supported by this browser.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let terminal = false

  const consume = (block: string): void => {
    const event = parseEvent(block)
    if (!event) return
    onEvent(event)
    if (event.type === 'done') terminal = true
    if (event.type === 'error') {
      terminal = true
      throw new Error(event.message || 'AI Cooker could not complete the response.')
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    buffer = buffer.replace(/\r\n/g, '\n')

    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      consume(block)
      boundary = buffer.indexOf('\n\n')
    }

    if (done) break
  }

  if (buffer.trim()) consume(buffer)
  if (!terminal) {
    throw new Error('AI Cooker ended the response stream unexpectedly.')
  }
}

export const chatApi = {
  async send(request: ChatRequest): Promise<ChatResponse> {
    const { data } = await http.post<ChatResponse>('/api/chat', request)
    return data
  },
  stream,
}
