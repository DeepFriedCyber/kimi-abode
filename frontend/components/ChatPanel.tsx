/**
 * ChatPanel — floating chat widget for AI assistance.
 * Connects to the API server via Socket.io for real-time streaming responses.
 */

"use client";

import { useState, useRef, useEffect } from "react";
import { io, Socket } from "socket.io-client";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function ChatPanel() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const socketRef = useRef<Socket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Connect on mount
  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";
    socketRef.current = io(apiUrl, { path: "/api/chat/socket" });

    socketRef.current.on("connect", () => setConnected(true));
    socketRef.current.on("disconnect", () => setConnected(false));

    socketRef.current.on("chat:response", (data: { chunk: string }) => {
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === "assistant") {
          return [...prev.slice(0, -1), { ...last, content: last.content + data.chunk }];
        }
        return [...prev, { role: "assistant", content: data.chunk }];
      });
    });

    socketRef.current.on("chat:done", () => setStreaming(false));
    socketRef.current.on("chat:error", (data: { message: string }) => {
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${data.message}` }]);
      setStreaming(false);
    });

    return () => {
      socketRef.current?.disconnect();
    };
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || streaming) return;

    const userMsg: Message = { role: "user", content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setStreaming(true);

    // Send via Socket.io
    socketRef.current?.emit("chat:message", { messages: [...messages, userMsg] });
  };

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setOpen(!open)}
        className={`fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full shadow-lg flex items-center justify-center text-xl transition-colors ${
          open ? "bg-blue-700" : "bg-blue-600 hover:bg-blue-700"
        }`}
      >
        {open ? "✕" : "💬"}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-24 right-6 z-50 w-[380px] max-h-[600px] bg-white rounded-2xl shadow-xl border flex flex-col overflow-hidden">
          {/* Header */}
          <div className="bg-blue-600 text-white px-4 py-3 flex items-center justify-between">
            <span className="font-semibold text-sm">AI Assistant</span>
            <span className={`w-2 h-2 rounded-full ${connected ? "bg-green-400" : "bg-red-400"}`} />
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[300px] max-h-[400px]">
            {messages.length === 0 && (
              <p className="text-sm text-gray-400 text-center py-8">
                Ask me about properties, stamp duty, mortgages, or local areas.
              </p>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] px-3 py-2 rounded-xl text-sm ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 text-gray-900"
                  }`}
                >
                  {msg.content}
                  {msg.role === "assistant" && streaming && i === messages.length - 1 && (
                    <span className="animate-pulse">▌</span>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <form
            onSubmit={(e) => { e.preventDefault(); sendMessage(); }}
            className="border-t p-3 flex gap-2"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about property..."
              className="flex-1 px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="submit"
              disabled={!input.trim() || streaming}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50 hover:bg-blue-700"
            >
              Send
            </button>
          </form>
        </div>
      )}
    </>
  );
}
