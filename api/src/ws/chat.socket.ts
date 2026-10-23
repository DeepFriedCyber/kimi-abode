/**
 * Socket.IO bridge for chat.
 *
 * Attaches to Fastify's underlying HTTP server and forwards chat messages to
 * the AI service's SSE endpoint, re-emitting decoded chunks to the client.
 */

import type { Server as HttpServer } from "node:http";
import { Server as SocketIOServer, type Socket } from "socket.io";

export interface ChatSocketOptions {
  aiUrl: string;
  corsOrigin: string | string[];
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const MAX_MESSAGES = 50;

function isChatMessage(value: unknown): value is ChatMessage {
  if (typeof value !== "object" || value === null) return false;
  const message = value as Record<string, unknown>;
  return (
    (message.role === "user" || message.role === "assistant") &&
    typeof message.content === "string" &&
    message.content.length > 0 &&
    message.content.length <= 4_000
  );
}

export function attachChatSocket(server: HttpServer, opts: ChatSocketOptions): SocketIOServer {
  const io = new SocketIOServer(server, {
    cors: { origin: opts.corsOrigin, methods: ["GET", "POST"] },
    serveClient: false,
  });

  io.on("connection", (socket: Socket) => {
    let controller: AbortController | null = null;

    socket.on("chat:message", async (payload: unknown) => {
      const data = payload as { messages?: unknown };
      const messages = Array.isArray(data?.messages) ? data.messages : [];

      if (messages.length === 0 || messages.length > MAX_MESSAGES || !messages.every(isChatMessage)) {
        socket.emit("chat:error", { message: "Invalid message payload" });
        return;
      }

      controller?.abort();
      controller = new AbortController();

      try {
        const response = await fetch(`${opts.aiUrl}/chat/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({ messages }),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          socket.emit("chat:error", { message: "AI service unavailable" });
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;
            if (raw === "[DONE]") {
              socket.emit("chat:done");
              return;
            }
            try {
              const parsed = JSON.parse(raw) as { chunk?: string };
              if (typeof parsed.chunk === "string") {
                socket.emit("chat:response", { chunk: parsed.chunk });
              }
            } catch {
              // Ignore malformed frames rather than tearing down the stream.
              socket.emit("chat:response", { chunk: raw });
            }
          }
        }

        socket.emit("chat:done");
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          socket.emit("chat:error", { message: "Chat request failed" });
        }
      }
    });

    socket.on("disconnect", () => {
      controller?.abort();
      controller = null;
    });
  });

  return io;
}

export default attachChatSocket;
