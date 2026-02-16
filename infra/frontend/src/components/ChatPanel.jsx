import { useState, useRef, useEffect } from 'react'
import MessageBubble from './MessageBubble'

export default function ChatPanel({ messages, onSend, loading }) {
  const [text, setText] = useState('')
  const bottomRef = useRef()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = () => {
    const trimmed = text.trim()
    if (!trimmed || loading) return
    onSend(trimmed)
    setText('')
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="chat-panel">
      <div className="messages">
        {messages.length === 0 && !loading && (
          <div className="messages-empty">
            Upload an image and describe what you want to do.<br />
            Switch models in the header to try different tools.
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        {loading && <div className="loading-indicator">Working on it…</div>}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          rows={2}
          placeholder="Describe what you want to do… (Enter to send, Shift+Enter for newline)"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button className="send-btn" onClick={send} disabled={loading || !text.trim()}>
          Send
        </button>
      </div>
    </div>
  )
}
