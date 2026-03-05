---
name: component-patterns
description: Full component implementations for the interview UI — virtualised MessageList, auto-resize InputArea, keyboard shortcut system, CSS design tokens, and PhaseProgress indicator with accessibility patterns.
---

# Component Patterns Reference

Production-ready component implementations for the interview agent UI.

---

## MessageList — Virtualised

For any interview session longer than ~30 exchanges, a non-virtualised list will lag.
Use `@tanstack/react-virtual` to render only what's visible.

```typescript
import { useRef, useEffect } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Message, StreamingMessage as StreamingMessageType } from '../types'
import { MessageBubble } from './MessageBubble'
import { StreamingMessage } from './StreamingMessage'

interface MessageListProps {
  messages: Message[]
  streamingMessage: StreamingMessageType | null
}

export function MessageList({ messages, streamingMessage }: MessageListProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const virtualiser = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 80,      // Estimated px height per message
    overscan: 5,                  // Render 5 items above/below viewport
  })

  // Scroll to bottom when new completed messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  return (
    <div
      ref={parentRef}
      className="message-list"
      role="log"
      aria-label="Interview conversation"
      aria-live="polite"
      aria-relevant="additions"
    >
      {/* Virtualised completed messages */}
      <div
        style={{ height: `${virtualiser.getTotalSize()}px`, position: 'relative' }}
      >
        {virtualiser.getVirtualItems().map(virtualItem => (
          <div
            key={virtualItem.key}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${virtualItem.start}px)`,
            }}
          >
            <MessageBubble
              message={messages[virtualItem.index]}
              index={virtualItem.index}
            />
          </div>
        ))}
      </div>

      {/* Streaming message — always rendered outside virtualiser */}
      {streamingMessage && (
        <StreamingMessage
          content={streamingMessage.content}
          isStreaming={streamingMessage.isStreaming}
          role={streamingMessage.role}
        />
      )}

      {/* Scroll anchor */}
      <div ref={bottomRef} />
    </div>
  )
}
```

---

## MessageBubble — Completed Messages

```typescript
import { memo } from 'react'
import { Message } from '../types'
import { formatTimestamp } from '../utils/time'

interface MessageBubbleProps {
  message: Message
  index: number
}

// memo() is critical — completed messages must NEVER re-render
export const MessageBubble = memo(function MessageBubble({
  message,
}: MessageBubbleProps) {
  const isInterviewer = message.role === 'interviewer'

  return (
    <article
      className={`message-bubble message-bubble--${message.role}`}
      aria-label={`${isInterviewer ? 'Interviewer' : 'You'} said`}
    >
      <div className="message-bubble__avatar" aria-hidden="true">
        {isInterviewer ? <InterviewerAvatar /> : <CandidateAvatar />}
      </div>

      <div className="message-bubble__content">
        <p className="message-bubble__text">{message.content}</p>
        <time
          className="message-bubble__time"
          dateTime={new Date(message.timestamp).toISOString()}
          aria-label={`Sent at ${formatTimestamp(message.timestamp)}`}
        >
          {formatTimestamp(message.timestamp)}
        </time>
      </div>
    </article>
  )
}, (prev, next) => prev.message.id === next.message.id)
// Custom comparator: only re-render if message ID changes (i.e., never for completed msgs)
```

---

## InputArea — Auto-resize Textarea with Send/Voice

```typescript
import { useState, useRef, useEffect, useCallback, KeyboardEvent } from 'react'
import { VoiceButton } from './VoiceButton'

interface InputAreaProps {
  onSubmit: (text: string) => void
  disabled?: boolean
  placeholder?: string
  maxLength?: number
}

export function InputArea({
  onSubmit,
  disabled = false,
  placeholder = 'Type your answer...',
  maxLength = 2000,
}: InputAreaProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return

    // Reset height to recalculate
    textarea.style.height = 'auto'
    const newHeight = Math.min(textarea.scrollHeight, 200) // Max 200px
    textarea.style.height = `${newHeight}px`
  }, [value])

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
    setValue('')
    textareaRef.current?.focus()
  }, [value, disabled, onSubmit])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Enter (not Shift+Enter)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleVoiceTranscript = useCallback((transcript: string) => {
    setValue(prev => prev ? `${prev} ${transcript}` : transcript)
    textareaRef.current?.focus()
  }, [])

  const charCount = value.length
  const isOverLimit = charCount > maxLength
  const canSubmit = value.trim().length > 0 && !disabled && !isOverLimit

  return (
    <div className="input-area">
      <div className="input-area__field">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          rows={1}
          maxLength={maxLength + 100}  // Soft limit — hard limit shown via UI
          aria-label="Your answer"
          aria-describedby="input-char-count"
          className={`input-area__textarea ${isOverLimit ? 'input-area__textarea--overlimit' : ''}`}
        />
      </div>

      <div className="input-area__controls">
        <VoiceButton
          onTranscript={handleVoiceTranscript}
          disabled={disabled}
        />

        <span
          id="input-char-count"
          className={`input-area__char-count ${isOverLimit ? 'input-area__char-count--over' : ''}`}
          aria-live="polite"
          aria-label={`${charCount} of ${maxLength} characters`}
        >
          {charCount}/{maxLength}
        </span>

        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          aria-label="Send answer (Enter)"
          className="input-area__send button--primary"
        >
          Send
          <span aria-hidden="true"> ↵</span>
        </button>
      </div>
    </div>
  )
}
```

---

## PhaseProgress Indicator

Shows which phase of the interview the candidate is in.

```typescript
type Phase = 'intro' | 'background' | 'technical' | 'behavioral' | 'debrief'

const PHASES: { key: Phase; label: string; shortLabel: string }[] = [
  { key: 'intro',      label: 'Introduction', shortLabel: 'Intro'     },
  { key: 'background', label: 'Background',   shortLabel: 'Bg'        },
  { key: 'technical',  label: 'Technical',    shortLabel: 'Tech'      },
  { key: 'behavioral', label: 'Behavioural',  shortLabel: 'Behav'     },
  { key: 'debrief',    label: 'Debrief',      shortLabel: 'Debrief'   },
]

interface PhaseProgressProps {
  currentPhase: Phase
  completedPhases: Phase[]
}

export function PhaseProgress({ currentPhase, completedPhases }: PhaseProgressProps) {
  const currentIndex = PHASES.findIndex(p => p.key === currentPhase)

  return (
    <nav aria-label="Interview phases" className="phase-progress">
      <ol className="phase-progress__list">
        {PHASES.map((phase, index) => {
          const isComplete = completedPhases.includes(phase.key)
          const isCurrent = phase.key === currentPhase
          const isUpcoming = index > currentIndex

          return (
            <li
              key={phase.key}
              className={`phase-progress__item ${
                isComplete ? 'phase-progress__item--complete' :
                isCurrent  ? 'phase-progress__item--current'  :
                             'phase-progress__item--upcoming'
              }`}
              aria-current={isCurrent ? 'step' : undefined}
            >
              <span className="phase-progress__dot" aria-hidden="true">
                {isComplete ? '✓' : index + 1}
              </span>
              <span className="phase-progress__label">
                <span className="phase-progress__label--full">{phase.label}</span>
                <span className="phase-progress__label--short" aria-hidden="true">
                  {phase.shortLabel}
                </span>
              </span>
              {isUpcoming && (
                <span className="sr-only"> (upcoming)</span>
              )}
              {isComplete && (
                <span className="sr-only"> (complete)</span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
```

---

## CSS Design Tokens

Define these once. Reference everywhere. Never hard-code colours or spacing.

```css
:root {
  /* ── Colours ── */
  --color-bg:               #0f1117;
  --color-surface:          #1a1d27;
  --color-surface-raised:   #222534;
  --color-border:           #2e3148;
  --color-text-primary:     #e8eaf6;
  --color-text-secondary:   #8b90b8;
  --color-text-muted:       #555a7a;

  --color-accent:           #6c63ff;
  --color-accent-hover:     #7b73ff;
  --color-accent-muted:     rgba(108, 99, 255, 0.15);

  --color-interviewer:      #1e2a3a;
  --color-interviewer-text: #a8d4f5;
  --color-candidate:        #1a2a1a;
  --color-candidate-text:   #a8f5b8;

  --color-warning:          #f0b429;
  --color-critical:         #e53e3e;
  --color-success:          #38a169;

  /* ── Timer urgency ── */
  --timer-normal:           var(--color-accent);
  --timer-warning:          var(--color-warning);
  --timer-critical:         var(--color-critical);

  /* ── Spacing ── */
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  20px;
  --space-6:  24px;
  --space-8:  32px;
  --space-10: 40px;

  /* ── Typography ── */
  --font-sans:  'Inter', system-ui, -apple-system, sans-serif;
  --font-mono:  'JetBrains Mono', 'Fira Code', monospace;

  --text-xs:    0.75rem;
  --text-sm:    0.875rem;
  --text-base:  1rem;
  --text-lg:    1.125rem;
  --text-xl:    1.25rem;

  --weight-normal:   400;
  --weight-medium:   500;
  --weight-semibold: 600;

  /* ── Radii ── */
  --radius-sm:   4px;
  --radius-md:   8px;
  --radius-lg:   12px;
  --radius-full: 9999px;

  /* ── Shadows ── */
  --shadow-sm:  0 1px 3px rgba(0,0,0,0.3);
  --shadow-md:  0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg:  0 8px 24px rgba(0,0,0,0.5);

  /* ── Transitions ── */
  --transition-fast:   120ms ease;
  --transition-normal: 200ms ease;
  --transition-slow:   350ms ease;

  /* ── Layout ── */
  --header-height:  56px;
  --sidebar-width:  280px;
  --input-height:   56px;
  --max-content-w:  760px;
}

/* Urgency overrides for timer */
.interview-timer--warning  { --timer-color: var(--timer-warning);  }
.interview-timer--critical { --timer-color: var(--timer-critical); }
.interview-timer--normal   { --timer-color: var(--timer-normal);   }

/* Utility: screen-reader only */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

---

## Keyboard Shortcut System

```typescript
import { useEffect, useCallback } from 'react'

type ShortcutHandler = (e: KeyboardEvent) => void

interface Shortcut {
  key: string
  alt?: boolean
  ctrl?: boolean
  shift?: boolean
  handler: ShortcutHandler
  description: string
}

export function useKeyboardShortcuts(shortcuts: Shortcut[]) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Don't fire shortcuts when typing in an input
    const target = e.target as HTMLElement
    if (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT') {
      // Exception: allow Alt+ shortcuts even in inputs
      if (!e.altKey) return
    }

    for (const shortcut of shortcuts) {
      const keyMatch   = e.key === shortcut.key
      const altMatch   = !!shortcut.alt   === e.altKey
      const ctrlMatch  = !!shortcut.ctrl  === e.ctrlKey
      const shiftMatch = !!shortcut.shift === e.shiftKey

      if (keyMatch && altMatch && ctrlMatch && shiftMatch) {
        e.preventDefault()
        shortcut.handler(e)
        return
      }
    }
  }, [shortcuts])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])
}

// Usage in InterviewSession:
// useKeyboardShortcuts([
//   { key: 'ArrowRight', alt: true, handler: handleNext,     description: 'Next question'     },
//   { key: 'ArrowLeft',  alt: true, handler: handlePrevious, description: 'Previous question' },
//   { key: 'p',          alt: true, handler: handlePause,    description: 'Pause timer'        },
//   { key: 'Escape',     handler: handleCancelStream,        description: 'Stop response'     },
// ])
```

---

## Loading & Empty States

```typescript
// Typing indicator — shown while interviewer response is pending (before stream starts)
export function TypingIndicator() {
  return (
    <div
      className="typing-indicator"
      role="status"
      aria-label="Interviewer is composing a response"
    >
      <div className="message-bubble message-bubble--interviewer">
        <div className="typing-indicator__dots" aria-hidden="true">
          <span /><span /><span />
        </div>
      </div>
    </div>
  )
}

// Empty state — start of session
export function ConversationEmpty() {
  return (
    <div className="conversation-empty" role="status">
      <p className="conversation-empty__hint">
        The interview will begin shortly.
      </p>
    </div>
  )
}
```

```css
.typing-indicator__dots {
  display: flex;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
}

.typing-indicator__dots span {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--color-text-secondary);
  animation: typing-bounce 1.2s ease infinite;
}

.typing-indicator__dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator__dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0);    opacity: 0.4; }
  30%           { transform: translateY(-6px); opacity: 1;   }
}
```
