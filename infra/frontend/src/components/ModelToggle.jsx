import React, { useRef, useState } from 'react';

export default function ModelSelector({ activeType, onChange }) {
  const windowRef = useRef(null);

  // Window Positioning State
  const [position, setPosition] = useState({ x: 400, y: 100 });
  const [isDraggingWindow, setIsDraggingWindow] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  // Minimize state
  const [isMinimized, setIsMinimized] = useState(false);

  // Moving the window
  const handleWindowPointerDown = (e) => {
    const rect = windowRef.current.getBoundingClientRect();
    setDragOffset({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    });
    setIsDraggingWindow(true);
    e.target.setPointerCapture(e.pointerId);
  };

  const handleWindowPointerMove = (e) => {
    if (!isDraggingWindow) return;
    setPosition({
      x: e.clientX - dragOffset.x,
      y: e.clientY - dragOffset.y
    });
  };

  const handleWindowPointerUp = (e) => {
    setIsDraggingWindow(false);
    e.target.releasePointerCapture(e.pointerId);
  };

  return (
    <div 
      ref={windowRef}
      style={{ 
        position: 'fixed',
        top: `${position.y}px`, 
        left: `${position.x}px`, 
        zIndex: 9998, 
        width: '160px', 
        backgroundColor: '#fff', 
        border: '1px solid #ccc',
        borderRadius: '8px',
        boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
        display: 'flex', 
        flexDirection: 'column', 
        overflow: 'hidden'
      }}
    >
      {/* Title bar */}
      <div 
        onPointerDown={handleWindowPointerDown}
        onPointerMove={handleWindowPointerMove}
        onPointerUp={handleWindowPointerUp}
        style={{
          backgroundColor: '#f1f1f1',
          padding: '6px 10px',
          borderBottom: isMinimized ? 'none' : '1px solid #ddd',
          cursor: isDraggingWindow ? 'grabbing' : 'grab',
          userSelect: 'none',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '12px',
          fontWeight: 'bold',
          color: '#333'
        }}
      >
        <span>Model Toggle</span>
        <button 
          onClick={() => setIsMinimized(!isMinimized)} 
          style={{ 
            background: 'none', 
            border: 'none', 
            cursor: 'pointer', 
            fontSize: '16px', 
            lineHeight: '1',
            padding: '0 4px'
          }}
        >
          {isMinimized ? '+' : '−'}
        </button>
      </div>

      {/* CONTENT AREA */}
      {!isMinimized && (
        <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <button 
            onClick={() => onChange('linear')}
            style={{ 
              padding: '8px',
              border: '1px solid',
              borderColor: activeType === 'linear' ? '#007bff' : '#eee',
              borderRadius: '6px',
              backgroundColor: activeType === 'linear' ? '#e6f2ff' : '#fafafa',
              cursor: 'pointer',
              fontWeight: activeType === 'linear' ? 'bold' : 'normal',
              color: activeType === 'linear' ? '#007bff' : '#555',
              transition: 'all 0.2s ease',
              fontSize: '13px'
            }}
          >
            Linear
          </button>
          
          <button 
            onClick={() => onChange('gaussian')}
            style={{ 
              padding: '8px',
              border: '1px solid',
              borderColor: activeType === 'gaussian' ? '#007bff' : '#eee',
              borderRadius: '6px',
              backgroundColor: activeType === 'gaussian' ? '#e6f2ff' : '#fafafa',
              cursor: 'pointer',
              fontWeight: activeType === 'gaussian' ? 'bold' : 'normal',
              color: activeType === 'gaussian' ? '#007bff' : '#555',
              transition: 'all 0.2s ease',
              fontSize: '13px'
            }}
          >
            Gaussian
          </button>
        </div>
      )}
    </div>
  );
}