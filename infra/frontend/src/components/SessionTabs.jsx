export default function SessionTabs({ sessions, activeLocalId, onSwitch, onNew, onClose }) {
  return (
    <div className="session-tabs">
      {sessions.map(s => (
        <div
          key={s.localId}
          className={`session-tab ${s.localId === activeLocalId ? 'active' : ''}`}
          onClick={() => onSwitch(s.localId)}
        >
          <span className="session-tab-name">{s.name}</span>
          {sessions.length > 1 && (
            <button
              className="session-tab-close"
              onClick={e => { e.stopPropagation(); onClose(s.localId) }}
            >×</button>
          )}
        </div>
      ))}
      <button className="session-tab-new" onClick={onNew} title="New canvas">+</button>
    </div>
  )
}
