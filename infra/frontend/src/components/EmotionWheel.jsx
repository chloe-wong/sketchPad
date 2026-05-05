import React, { useRef, useState } from 'react';

export default function EmotionWheel({ onSelect }) {
  const svgRef = useRef(null);
  const windowRef = useRef(null);

  // Window Dragging State
  const [position, setPosition] = useState({ x: 500, y: 100 }); 
  const [isDraggingWindow, setIsDraggingWindow] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  // Minimize state
  const [isMinimized, setIsMinimized] = useState(true);

  // Wheel interaction state
  const [activePoint, setActivePoint] = useState(null);

  // Moving window
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

  // Clicking in emotion wheel
  const handleWheelInteraction = (e) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const dx = x - cx;
    const dy = cy - y; 
    const maxRadius = rect.width / 2;
    const distance = Math.sqrt(dx * dx + dy * dy);
    let rho = distance / maxRadius;
    if (rho > 1) rho = 1;

    let angleRad = Math.atan2(dy, dx);
    let degrees = angleRad * (180 / Math.PI);
    if (degrees < 0) degrees += 360;

    const finalTheta = Math.round(degrees);
    const finalRho = Number(rho.toFixed(2));

    setActivePoint({ 
      x: cx + (dx * (rho / (distance / maxRadius || 1))), 
      y: cy - (dy * (rho / (distance / maxRadius || 1))) 
    });

    onSelect(`theta=${finalTheta} rho=${finalRho}`);
  };

  return (
    <div 
      ref={windowRef}
      style={{ 
        position: 'fixed',
        top: `${position.y}px`, 
        left: `${position.x}px`, 
        zIndex: 9999,
        width: '180px',
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
        <span>Emotion Wheel</span>
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

      {/* WHEEL */}
      {!isMinimized && (
        <div style={{ padding: '15px', display: 'flex', justifyContent: 'center' }}>
          <svg 
            ref={svgRef}
            width="140" 
            height="140" 
            style={{ 
              background: '#fafafa', 
              borderRadius: '50%', 
              cursor: 'crosshair',
              touchAction: 'none' 
            }}
            onPointerDown={(e) => {
              e.target.setPointerCapture(e.pointerId); 
              handleWheelInteraction(e);
            }}
            onPointerMove={(e) => {
              if (e.buttons === 1) handleWheelInteraction(e); 
            }}
          >
            <circle cx="70" cy="70" r="70" fill="none" stroke="#ccc" strokeWidth="1" />
            <circle cx="70" cy="70" r="35" fill="none" stroke="#ccc" strokeWidth="1" />
            <line x1="0" y1="70" x2="140" y2="70" stroke="#ccc" strokeWidth="1" />
            <line x1="70" y1="0" x2="70" y2="140" stroke="#ccc" strokeWidth="1" />

            {/* Radial Labels (Rho) */}
            <text x="73" y="67" fontSize="10" fill="#888" style={{ pointerEvents: 'none', userSelect: 'none' }}>0</text>
            <text x="116" y="67" fontSize="10" fill="#888" style={{ pointerEvents: 'none', userSelect: 'none' }}>1.0</text>

            {/* Degree Labels (Theta) */}
            <text x="122" y="83" fontSize="10" fill="#aaa" style={{ pointerEvents: 'none', userSelect: 'none' }}>0°</text>
            <text x="74" y="14" fontSize="10" fill="#aaa" style={{ pointerEvents: 'none', userSelect: 'none' }}>90°</text>
            <text x="4" y="83" fontSize="10" fill="#aaa" style={{ pointerEvents: 'none', userSelect: 'none' }}>180°</text>
            <text x="74" y="135" fontSize="10" fill="#aaa" style={{ pointerEvents: 'none', userSelect: 'none' }}>270°</text>

            {/* Active Point Indicator */}
            {activePoint && (
              <circle cx={activePoint.x} cy={activePoint.y} r="6" fill="#007bff" style={{ pointerEvents: 'none' }} />
            )}
          </svg>
        </div>
      )}
    </div>
  );
}