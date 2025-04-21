// File: components/StreamingMessage.tsx

import ReactMarkdown from 'react-markdown';

interface StreamingMessageProps {
  content: string;
}

function StreamingMessage({ content }: StreamingMessageProps) {
  return (
    <div className="message ai-message streaming-message">
      <div className="message-content">
        <ReactMarkdown>{content}</ReactMarkdown>
        <span className="typing-indicator"></span>
      </div>
      <div className="message-sender">AI</div>
    </div>
  );
}

export default StreamingMessage;