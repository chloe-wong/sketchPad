import { useState, useEffect, useCallback } from 'react'
import * as api from './api'
import ChatPanel from './components/ChatPanel'
import ImagePanel from './components/ImagePanel'
import ModelSelector from './components/ModelSelector'
import SessionTabs from './components/SessionTabs'
import './App.css'

function makeSession(index) {
  return { localId: Date.now() + index, backendId: null, name: `Canvas ${index + 1}`, currentImage: null, messages: [] }
}

export default function App() {
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState(null)
  const [sessions, setSessions] = useState(() => [makeSession(0)])
  const [activeLocalId, setActiveLocalId] = useState(() => makeSession(0).localId)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Derive active session
  const activeSession = sessions.find(s => s.localId === activeLocalId) || sessions[0]

  const GANmutplaceholder = "\'theta={degrees} rho={magnitude}\', where degrees is 0 to 360, magnitude is 0 to 1"
  let defaultplaceholder = "Describe what you want to do… (Enter to send, Shift+Enter for newline)"
  if(selectedModel == 'GANmut') {
    defaultplaceholder = GANmutplaceholder;
  }

  // Helper: update a single session by localId
  const updateSession = useCallback((localId, patch) => {
    setSessions(prev => prev.map(s => s.localId === localId ? { ...s, ...patch } : s))
  }, [])

  useEffect(() => {
    api.fetchModels()
      .then(data => {
        setModels(data)
        if (data.length > 0) setSelectedModel(data[0].id)
      })
      .catch(() => setError('Cannot connect to backend. Is it running on port 8000?'))
  }, [])

  const handleNewSession = () => {
    const s = makeSession(sessions.length)
    setSessions(prev => [...prev, s])
    setActiveLocalId(s.localId)
  }

  const handleCloseSession = (localId) => {
    setSessions(prev => {
      if (prev.length === 1) return prev // keep at least one
      const next = prev.filter(s => s.localId !== localId)
      if (localId === activeLocalId) setActiveLocalId(next[next.length - 1].localId)
      return next
    })
  }

  const handleImageUpload = async (file) => {
    setError(null)
    const previewUrl = URL.createObjectURL(file)
    updateSession(activeSession.localId, { currentImage: previewUrl })
    try {
      if (activeSession.backendId) {
        await api.updateImage(activeSession.backendId, file)
      } else {
        const data = await api.createSession(file)
        updateSession(activeSession.localId, { backendId: data.session_id })
      }
    } catch (e) {
      setError(e.message)
    }
  }

  const handleSend = async (prompt) => {
    if (!selectedModel) {
      setError('No models available. Add a model to models/ and restart the backend.')
      return
    }
    setError(null)

    const localId = activeSession.localId
    let sid = activeSession.backendId

    if (!sid) {
      try {
        const data = await api.createSession(null)
        sid = data.session_id
        updateSession(localId, { backendId: sid })
      } catch (e) {
        setError(e.message)
        return
      }
    }

    updateSession(localId, {
      messages: [...activeSession.messages, { role: 'user', text: prompt, image: null }]
    })
    setLoading(true)

    try {
      const result = await api.sendMessage(sid, selectedModel, prompt)
      const imageUrl = result.image ? `data:image/png;base64,${result.image}` : null
      setSessions(prev => prev.map(s => {
        if (s.localId !== localId) return s
        return {
          ...s,
          messages: [...s.messages, { role: 'assistant', text: result.text, image: imageUrl }],
          currentImage: imageUrl || s.currentImage,
        }
      }))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <span className="app-title">sketchPad</span>
        <ModelSelector models={models} selected={selectedModel} onChange={setSelectedModel} />
      </header>

      <SessionTabs
        sessions={sessions}
        activeLocalId={activeLocalId}
        onSwitch={setActiveLocalId}
        onNew={handleNewSession}
        onClose={handleCloseSession}
      />

      {error && (
        <div className="error-banner">
          {error}
          <button className="error-close" onClick={() => setError(null)}>×</button>
        </div>
      )}

      <main className="app-body">
        <ImagePanel currentImage={activeSession.currentImage} onUpload={handleImageUpload} selectedModel={selectedModel}/>
        <ChatPanel messages={activeSession.messages} onSend={handleSend} loading={loading} placeholder={defaultplaceholder} selectedModel={selectedModel} />
      </main>
    </div>
  )
}
