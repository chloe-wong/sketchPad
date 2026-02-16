export default function MessageBubble({ message }) {
  return (
    <div className={`message ${message.role}`}>
      <div className="message-bubble">{message.text}</div>
      {message.image && (
        <img src={message.image} alt="Model output" className="message-image" />
      )}
    </div>
  )
}
