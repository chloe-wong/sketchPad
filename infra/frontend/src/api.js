const BASE = 'http://localhost:8000'

export async function fetchModels() {
  const res = await fetch(`${BASE}/models`)
  if (!res.ok) throw new Error('Could not fetch models')
  return res.json()
}

export async function createSession(imageFile) {
  const form = new FormData()
  if (imageFile) form.append('file', imageFile)
  const res = await fetch(`${BASE}/session`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Could not create session')
  return res.json()
}

export async function updateImage(sessionId, imageFile) {
  const form = new FormData()
  form.append('file', imageFile)
  const res = await fetch(`${BASE}/session/${sessionId}/image`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error('Could not update image')
  return res.json()
}

export async function sendMessage(sessionId, modelId, prompt) {
  const res = await fetch(`${BASE}/session/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, prompt }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Server error ${res.status}`)
  }
  return res.json()
}
