// File: components/Message.tsx

import ReactMarkdown from 'react-markdown';

interface MessageProps {
  message: {
    id: number;
    text: string;
    sender: 'user' | 'ai';
    timestamp: string;
  };
}

function Message({ message }: MessageProps) {
  const { text, sender } = message;
  
  return (
    <div className={`message ${sender}-message`}>
      <div className="message-content">
        {sender === 'ai' ? (
          <ReactMarkdown>{text}</ReactMarkdown>
        ) : (
          <p>{text}</p>
        )}
      </div>
      <div className="message-sender">
        {sender === 'user' ? 'You' : 'AI'}
      </div>
    </div>
  );
}

export default Message;