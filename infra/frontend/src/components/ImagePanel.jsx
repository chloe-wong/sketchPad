import { useRef, useState } from 'react'

export default function ImagePanel({ currentImage, onUpload }) {
  const inputRef = useRef()
  const [dragOver, setDragOver] = useState(false)

  const handleFile = (file) => {
    if (file && file.type.startsWith('image/')) onUpload(file)
  }

  const onDragOver = (e) => { e.preventDefault(); setDragOver(true) }
  const onDragLeave = () => setDragOver(false)
  const onDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    handleFile(e.dataTransfer.files[0])
  }

  return (
    <div className="image-panel">
      <div className="image-panel-header">Canvas</div>

      {currentImage ? (
        <>
          <div className="image-display">
            <img src={currentImage} alt="Current canvas" />
          </div>
          <button className="upload-replace-btn" onClick={() => inputRef.current.click()}>
            Replace image
          </button>
        </>
      ) : (
        <div
          className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
          onClick={() => inputRef.current.click()}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
        >
          <span className="upload-zone-icon">🖼</span>
          <span>Upload your artwork</span>
          <span style={{ fontSize: 12, color: '#ccc' }}>Click or drag &amp; drop</span>
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={e => handleFile(e.target.files[0])}
      />
    </div>
  )
}
