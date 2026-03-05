---
name: streaming-patterns
description: SSE parsing edge cases, backpressure handling, reconnection logic, multi-provider streaming formats, and end-to-end streaming test patterns for React/TypeScript interview UI applications.
---

# Streaming Patterns Reference

Everything that goes wrong with streaming — and how to handle it properly.

---

## SSE Format Variations by Provider

Your stream parser must handle all of these. Real-world APIs are inconsistent.

```typescript
// Anthropic Claude format
// data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}
// data: {"type":"message_stop"}

// OpenAI / OpenAI-compatible format
// data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}
// data: [DONE]

// Generic text stream (some custom backends)
// data: Hello
// data:  world
// data: [DONE]

type StreamProvider = 'anthropic' | 'openai' | 'generic'

function extractToken(line: string, provider: StreamProvider): string | null {
  if (!line.startsWith('data: ')) return null

  const data = line.slice(6).trim()

  if (data === '[DONE]' || data === '') return null

  try {
    const parsed = JSON.parse(data)

    switch (provider) {
      case 'anthropic':
        if (parsed.type === 'content_block_delta') {
          return parsed.delta?.text ?? null
        }
        return null

      case 'openai':
        return parsed.choices?.[0]?.delta?.content ?? null

      case 'generic':
        return data  // Raw text

      default:
        return null
    }
  } catch {
    // Not JSON — treat as raw text token
    return data === '[DONE]' ? null : data
  }
}
```

---

## Robust SSE Parser

Real streams don't always deliver complete lines in each chunk. Buffer accordingly.

```typescript
export async function* parseSSEStream(
  response: Response,
  provider: StreamProvider = 'openai'
): AsyncGenerator<string, void, unknown> {
  const reader = response.body?.getReader()
  const decoder = new TextDecoder()

  if (!reader) throw new Error('Response has no readable body')

  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()

      if (done) {
        // Flush any remaining buffer content
        if (buffer.trim()) {
          const token = extractToken(buffer.trim(), provider)
          if (token) yield token
        }
        break
      }

      // Decode chunk and add to buffer
      buffer += decoder.decode(value, { stream: true })

      // Process complete lines (split on \n\n for SSE events, \n for lines)
      const lines = buffer.split('\n')

      // Keep the last (potentially incomplete) line in the buffer
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) continue  // Skip empty lines (SSE event separators)

        const token = extractToken(trimmed, provider)
        if (token !== null) yield token
      }
    }
  } finally {
    reader.releaseLock()
  }
}
```

---

## Backpressure Handling

When tokens arrive faster than React can render, batch them.

```typescript
import { useRef, useState, useCallback, useEffect } from 'react'

const BATCH_INTERVAL_MS = 16  // ~60fps — one render per frame max

export function useBatchedStreaming() {
  const [displayContent, setDisplayContent] = useState('')
  const pendingRef = useRef('')
  const frameRef = useRef<number | null>(null)

  const flush = useCallback(() => {
    if (pendingRef.current) {
      setDisplayContent(prev => prev + pendingRef.current)
      pendingRef.current = ''
    }
    frameRef.current = null
  }, [])

  const addToken = useCallback((token: string) => {
    pendingRef.current += token

    // Schedule a flush if not already scheduled
    if (frameRef.current === null) {
      frameRef.current = requestAnimationFrame(flush)
    }
  }, [flush])

  const reset = useCallback(() => {
    pendingRef.current = ''
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current)
      frameRef.current = null
    }
    setDisplayContent('')
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    }
  }, [])

  return { displayContent, addToken, reset }
}
```

---

## Reconnection Logic

For long interview sessions, network blips happen. Reconnect transparently.

```typescript
interface StreamWithRetryOptions {
  endpoint: string
  payload: Record<string, unknown>
  onToken: (token: string) => void
  onComplete: (fullContent: string) => void
  onError: (error: Error, attempt: number) => void
  maxRetries?: number
  retryDelayMs?: number
  signal?: AbortSignal
}

export async function streamWithRetry({
  endpoint,
  payload,
  onToken,
  onComplete,
  onError,
  maxRetries = 3,
  retryDelayMs = 1000,
  signal,
}: StreamWithRetryOptions): Promise<void> {
  let attempt = 0
  let accumulatedContent = ''

  while (attempt <= maxRetries) {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // Pass accumulated content so server can resume from offset if supported
          ...(accumulatedContent && { 'X-Resume-After': String(accumulatedContent.length) }),
        },
        body: JSON.stringify(payload),
        signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      // Stream successfully opened — reset retry count
      attempt = 0

      for await (const token of parseSSEStream(response)) {
        accumulatedContent += token
        onToken(token)
      }

      // Stream completed successfully
      onComplete(accumulatedContent)
      return

    } catch (error) {
      const err = error as Error

      // AbortError = user cancelled. Don't retry.
      if (err.name === 'AbortError') return

      attempt++
      onError(err, attempt)

      if (attempt > maxRetries) {
        throw new Error(`Stream failed after ${maxRetries} retries: ${err.message}`)
      }

      // Exponential backoff
      const delay = retryDelayMs * Math.pow(2, attempt - 1)
      await new Promise(resolve => setTimeout(resolve, delay))
    }
  }
}
```

---

## Complete useStreamingChat Hook

Production-ready hook combining all patterns — batching, retry, abort, error handling.

```typescript
import { useState, useCallback, useRef } from 'react'

interface Message {
  id: string
  role: 'interviewer' | 'candidate'
  content: string
  timestamp: number
}

interface UseStreamingChatOptions {
  endpoint: string
  onMessageComplete?: (message: Message) => void
}

export function useStreamingChat({ endpoint, onMessageComplete }: UseStreamingChatOptions) {
  const [messages, setMessages] = useState<Message[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const { addToken, reset: resetBatch } = useBatchedStreaming()

  const sendMessage = useCallback(async (userContent: string) => {
    if (isStreaming) return

    // Cancel any in-flight stream
    abortRef.current?.abort()
    abortRef.current = new AbortController()

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'candidate',
      content: userContent,
      timestamp: Date.now(),
    }

    setMessages(prev => [...prev, userMessage])
    setStreamingContent('')
    setIsStreaming(true)
    setError(null)
    resetBatch()

    const streamingId = crypto.randomUUID()

    try {
      await streamWithRetry({
        endpoint,
        payload: {
          messages: [...messages, userMessage].map(m => ({
            role: m.role === 'interviewer' ? 'assistant' : 'user',
            content: m.content,
          })),
        },
        onToken: (token) => {
          addToken(token)
          setStreamingContent(prev => prev + token)
        },
        onComplete: (fullContent) => {
          const interviewerMessage: Message = {
            id: streamingId,
            role: 'interviewer',
            content: fullContent,
            timestamp: Date.now(),
          }
          setMessages(prev => [...prev, interviewerMessage])
          setStreamingContent('')
          setIsStreaming(false)
          onMessageComplete?.(interviewerMessage)
        },
        onError: (err, attempt) => {
          console.warn(`Stream error (attempt ${attempt}):`, err.message)
        },
        signal: abortRef.current.signal,
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Stream failed'
      setError(message)
      setIsStreaming(false)
      setStreamingContent('')
    }
  }, [messages, isStreaming, endpoint, addToken, resetBatch, onMessageComplete])

  const cancelStream = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
    // Keep whatever content was streamed so far as a partial message
    if (streamingContent) {
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'interviewer',
        content: streamingContent + ' [interrupted]',
        timestamp: Date.now(),
      }])
    }
    setStreamingContent('')
  }, [streamingContent])

  return {
    messages,
    streamingContent,
    isStreaming,
    error,
    sendMessage,
    cancelStream,
  }
}
```

---

## Testing Streaming Components

Testing streaming UIs requires mocking the fetch stream.

```typescript
// test-utils/mockStream.ts
export function createMockStreamResponse(tokens: string[], delayMs = 10): Response {
  const encoder = new TextEncoder()

  const stream = new ReadableStream({
    async start(controller) {
      for (const token of tokens) {
        await new Promise(r => setTimeout(r, delayMs))
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({
            choices: [{ delta: { content: token } }]
          })}\n\n`)
        )
      }
      controller.enqueue(encoder.encode('data: [DONE]\n\n'))
      controller.close()
    }
  })

  return new Response(stream, {
    headers: { 'Content-Type': 'text/event-stream' }
  })
}


// ChatInterface.test.tsx
import { render, screen, waitFor, userEvent } from '@testing-library/react'
import { vi } from 'vitest'
import { ChatInterface } from './ChatInterface'
import { createMockStreamResponse } from '../test-utils/mockStream'

describe('ChatInterface streaming', () => {
  it('renders tokens progressively as they arrive', async () => {
    const tokens = ['Hello', ' candidate', ',', ' how', ' are', ' you?']

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      createMockStreamResponse(tokens, 20)
    )

    render(<ChatInterface endpoint="/api/interview" />)

    const input = screen.getByLabelText('Your answer')
    const send = screen.getByLabelText(/send/i)

    await userEvent.type(input, 'Hi!')
    await userEvent.click(send)

    // Should show streaming content progressively
    await waitFor(() => {
      expect(screen.getByText(/Hello candidate/)).toBeInTheDocument()
    }, { timeout: 5000 })

    // Final complete message
    await waitFor(() => {
      expect(screen.getByText('Hello candidate, how are you?')).toBeInTheDocument()
    }, { timeout: 5000 })
  })

  it('handles stream abort gracefully', async () => {
    vi.spyOn(global, 'fetch').mockImplementationOnce(() =>
      new Promise((_, reject) =>
        setTimeout(() => reject(new DOMException('Aborted', 'AbortError')), 100)
      )
    )

    render(<ChatInterface endpoint="/api/interview" />)

    const input = screen.getByLabelText('Your answer')
    await userEvent.type(input, 'Test message')
    await userEvent.click(screen.getByLabelText(/send/i))

    const cancelButton = await screen.findByLabelText(/stop/i)
    await userEvent.click(cancelButton)

    // Should not show an error — abort is intentional
    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })

  it('retries on network error', async () => {
    const tokens = ['Retry', ' worked']

    vi.spyOn(global, 'fetch')
      .mockRejectedValueOnce(new Error('Network error'))  // First attempt fails
      .mockResolvedValueOnce(createMockStreamResponse(tokens))  // Retry succeeds

    render(<ChatInterface endpoint="/api/interview" />)

    const input = screen.getByLabelText('Your answer')
    await userEvent.type(input, 'Test')
    await userEvent.click(screen.getByLabelText(/send/i))

    await waitFor(() => {
      expect(screen.getByText('Retry worked')).toBeInTheDocument()
    }, { timeout: 5000 })
  })
})
```

---

## Common Streaming Bugs & Fixes

| Bug | Root Cause | Fix |
|---|---|---|
| State update on unmounted component | No abort on unmount | `AbortController` in `useEffect` cleanup |
| Tokens appear out of order | Async state batching | Use `useRef` to accumulate, `setState` to display |
| Stream hangs on Firefox | `fetch` stream support differences | Add `keepalive: true` to fetch options |
| "Maximum update depth exceeded" | `useEffect` dependency causes loop | Stabilise handlers with `useCallback` |
| Partial last chunk lost | Buffer not flushed on stream end | Flush buffer when `done === true` |
| Double tokens on React StrictMode | Effect runs twice in dev | Check — effects should be idempotent |
| Memory leak with long sessions | Accumulated message state | Virtualise list; consider trimming old messages |
