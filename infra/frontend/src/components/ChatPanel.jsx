import { useState, useRef, useEffect } from 'react'
import MessageBubble from './MessageBubble'
import EmotionWheel from './EmotionWheel'
import ModelToggle from './ModelToggle';
import Manual from './Manual'

export default function ChatPanel({ messages, onSend, loading, placeholder, selectedModel }) {
  const [text, setText] = useState('')
  const bottomRef = useRef()
  const [ganmutType, setGanmutType] = useState('linear');

  const linearplaceholder = "\'theta={degrees} rho={magnitude} model=linear\', where degrees is 0 to 360, magnitude is 0 to 1"
  const gausplaceholder = "\'x={x} y={y} model=gaussian\', where x and y are both between -1.0 and 1.0. x^2 + y^2 <= 1"
  placeholder = linearplaceholder
  if(selectedModel == 'GANmut') {
    if(ganmutType == 'gaussian') {
      placeholder = gausplaceholder
    } else {
      placeholder = linearplaceholder
    }
  }

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

      {selectedModel === 'GANmut' && (
        <div 
          className="emotion-wheel-wrapper" 
          style={{ 
            display: 'flex', 
            justifyContent: 'flex-end', /* clinch right */
            padding: '0 10px 10px 0'
          }}
        >

          <ModelToggle activeType={ganmutType} onChange={setGanmutType} />
          <EmotionWheel 
          onSelect={(formattedString) => {
            // appends model type to theta/rho string
            const finalPrompt = `${formattedString} model=${ganmutType}`;
            setText(finalPrompt);
          }}
          ganmutType={ganmutType}
        />
          
          {/* manual added */}
          <Manual />
          
        </div>
      )}

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          rows={2}
          placeholder={placeholder}
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
