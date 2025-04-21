// File: components/MessageList.tsx

import Message from './Message';

interface MessageListProps {
  messages: Array<{
    id: number;
    text: string;
    sender: 'user' | 'ai';
    timestamp: string;
  }>;
}

function MessageList({ messages }: MessageListProps) {
  // The scrolling is now handled in the parent component
  return (
    <div className="message-list">
      {messages.length === 0 ? (
        <div className="welcome-message">
          <h2>Welcome to the AI Chat</h2>
          <p>How can I help you today?</p>
        </div>
      ) : (
        messages.map((message) => (
          <Message key={message.id} message={message} />
        ))
      )}
    </div>
  );
}

export default MessageList;