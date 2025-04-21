// File: App.tsx

import { useState, useEffect, useRef } from 'react';
import './App.css';
import MessageList from './components/MessageList';
import MessageInput from './components/MessageInput';
import StreamingMessage from './components/StreamingMessage';
import { flushSync } from 'react-dom';

// Define types for our messages
interface Message {
  id: number;
  text: string;
  sender: 'user' | 'ai';
  timestamp: string;
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [streamingContent, setStreamingContent] = useState<string>("");
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const sendMessage = async (messageText: string) => {
    if (!messageText.trim()) return;

    // Add user message to the chat
    const userMessage: Message = {
      id: Date.now(),
      text: messageText,
      sender: 'user',
      timestamp: new Date().toISOString(),
    };
    
    // Use flushSync to ensure the UI updates immediately
    flushSync(() => {
      setMessages(prevMessages => [...prevMessages, userMessage]);
      setIsLoading(true);
      setIsStreaming(true);
      setStreamingContent("");
    });
    
    // Scroll to the new message immediately
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

    try {
      // Make a request to your streaming endpoint
      const response = await fetch('http://localhost:9000/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content: messageText,
          model_code: '2c',
          input_type: 'text',
          output_format: 'code',
          priority: 2,
          format: 'complete'
        }),
      });

      if (!response.ok) {
        throw new Error(`Error: ${response.status}`);
      }

      // Get the response as a readable stream
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let accumulatedText = '';
      
      // Process the stream
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          console.log('Stream complete');
          break;
        }
        
        // Decode the chunk
        const chunk = decoder.decode(value, { stream: true });
        
        // Process SSE format: each line starting with "data: "
        const lines = chunk.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const content = line.substring(6);
            
            // Check if it's JSON completion data
            try {
              const jsonData = JSON.parse(content);
              if (jsonData.text) {
                // Full formatted response in final JSON
                accumulatedText = jsonData.text;
                
                // Update the streaming content
                setStreamingContent(accumulatedText);
              }
            } catch (e) {
              // Not JSON, just regular content
              accumulatedText += content;
              
              // Update the streaming content
              setStreamingContent(accumulatedText);
            }
            
            // Scroll to ensure latest content is visible
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
          } else if (line.startsWith('event: complete')) {
            // This indicates the response is complete
            console.log('Received complete event');
          }
        }
      }
      
      // Once streaming is complete, add the message to the history
      const aiMessage: Message = {
        id: Date.now(),
        text: accumulatedText,
        sender: 'ai',
        timestamp: new Date().toISOString(),
      };
      
      // Use flushSync to ensure UI updates immediately and in order
      flushSync(() => {
        setMessages(prevMessages => [...prevMessages, aiMessage]);
        setIsStreaming(false);
        setStreamingContent("");
        setIsLoading(false);
      });
      
    } catch (error) {
      console.error('Error sending message:', error);
      
      // Add error message
      const errorMessage: Message = {
        id: Date.now(),
        text: `Error: ${(error as Error).message}`,
        sender: 'ai',
        timestamp: new Date().toISOString(),
      };
      
      flushSync(() => {
        setMessages(prevMessages => [...prevMessages, errorMessage]);
        setIsStreaming(false);
        setStreamingContent("");
        setIsLoading(false);
      });
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>AI Chat with Streaming</h1>
      </header>
      <main className="chat-container">
        {/* Regular message history */}
        <MessageList messages={messages} />
        
        {/* Streaming message - only shown during streaming */}
        {isStreaming && <StreamingMessage content={streamingContent} />}
        
        {/* Invisible element for scrolling */}
        <div ref={messagesEndRef} />
        
        {/* Message input area */}
        <MessageInput 
          onSendMessage={sendMessage} 
          disabled={isLoading} 
        />
      </main>
    </div>
  );
}

export default App;