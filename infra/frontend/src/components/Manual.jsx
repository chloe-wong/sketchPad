import React, { useRef, useState } from 'react';
import GANmutWheel from '../images/GANmut_approximation.png';

export default function Manual() {
  const windowRef = useRef(null);

  // Window Dragging State
  // Offset slightly from the Emotion Wheel so they don't overlap
  const [position, setPosition] = useState({ x: 800, y: 100 }); 
  const [isDraggingWindow, setIsDraggingWindow] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  // Window Sizing State
  const [size, setSize] = useState({ width: 480, height: 450 });
  const [isResizing, setIsResizing] = useState(false);

  // Minimize state
  const [isMinimized, setIsMinimized] = useState(true);

  // Moving window handlers
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

  // --- RESIZING THE WINDOW ---
  const handleResizePointerDown = (e) => {
    e.stopPropagation(); // Prevents dragging the window while resizing
    setIsResizing(true);
    e.target.setPointerCapture(e.pointerId);
  };

  const handleResizePointerMove = (e) => {
    if (!isResizing) return;
    // Calculate new width/height based on mouse position relative to window's top-left corner
    const newWidth = e.clientX - position.x;
    const newHeight = e.clientY - position.y;
    
    setSize({
      width: Math.max(250, newWidth),   // Enforce a minimum width of 250px
      height: Math.max(200, newHeight)  // Enforce a minimum height of 200px
    });
  };

  const handleResizePointerUp = (e) => {
    setIsResizing(false);
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
        width: `${size.width}px`, 
        height: isMinimized ? 'auto' : `${size.height}px`, // Collapses to auto when minimized
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
          color: '#333',
          flexShrink: 0
        }}
      >
        <span>GANmut Manual</span>
        {/* Toggle Minimize Button */}
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

      {/* CONTENT AREA - Only renders if not minimized */}
      {!isMinimized && (
        <div style={{ 
            padding: '15px', 
            fontSize: '14px', 
            color: '#444', 
            lineHeight: '1.5',
            flexGrow: 1,       // Takes up all remaining height dynamically
            overflowY: 'auto', // Still scrolls if text overflows the dynamic height
            position: 'relative' 
        }}>
          
          <h4>Emotion Map:</h4>
          <p>
            Magnitude (rho) is between 0.0 and 1.0, where 1.0 is the greatest intensity.
            <br>
            </br>
            <br>
            </br>
            Angle (theta) is between 0 and 360 degrees, where the angle roughly matches to an emotion shown below.
            <br>
            </br>
            <br>
            </br>
            <img src={GANmutWheel} alt="GANmut wheel"
            style={{ 
              maxWidth: '100%', // fit window
              height: 'auto',   // aspect ratio
              borderRadius: '4px',
              marginBottom: '10px' 
            }}>
            </img>

          </p>
          
          {/* Example of adding more text structure */}
          {/* <ul>
            <li><strong>Click and drag</strong> on the wheel to select an emotion intensity.</li>
            <li><strong>Outer edge</strong> represents maximum intensity (1.0).</li>
            <li><strong>Center</strong> represents neutral (0.0).</li>
          </ul> 
          */}

        </div>
      )}

      {/* DIAGONAL RESIZE HANDLE (Bottom Right Corner) */}
      {!isMinimized && (
        <div
          onPointerDown={handleResizePointerDown}
          onPointerMove={handleResizePointerMove}
          onPointerUp={handleResizePointerUp}
          style={{
            position: 'absolute',
            bottom: 0,
            right: 0,
            width: '16px',
            height: '16px',
            cursor: 'nwse-resize',
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'flex-end',
            padding: '2px',
            zIndex: 10
          }}
        >
          {/* Visual triangle for the resize handle */}
          <svg viewBox="0 0 10 10" style={{ width: '10px', height: '10px', opacity: 0.4 }}>
            <polygon points="10,0 10,10 0,10" fill="currentColor" />
          </svg>
        </div>
      )}

    </div>
  );
}