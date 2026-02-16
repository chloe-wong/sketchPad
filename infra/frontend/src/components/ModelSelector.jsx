export default function ModelSelector({ models, selected, onChange }) {
  return (
    <div className="model-selector">
      <span>Model</span>
      <select
        value={selected || ''}
        onChange={e => onChange(e.target.value)}
        disabled={models.length === 0}
      >
        {models.length === 0 ? (
          <option value="">No models found</option>
        ) : (
          models.map(m => (
            <option key={m.id} value={m.id} title={m.description}>
              {m.name}
            </option>
          ))
        )}
      </select>
    </div>
  )
}
