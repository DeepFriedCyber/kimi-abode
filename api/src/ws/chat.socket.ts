/**
 * WebSocket bridge — forwards Socket.io connections to SSE streams from the AI service.
 * Keeps a single connection to the FastAPI backend per client session.
 */

import { Server as HttpServer } from "http";
import { Server as SocketIOServer, Socket } from "socket.io";

export function attachChatSocket(
  app: any,
  opts: { aiUrl: string; corsOrigin: string },
) {
  const io = new SocketIOServer({
    cors: { origin: opts.corsOrigin },
  });

  // Attach to Fastify's underlying HTTP server
  const server = (app.server as HttpServer);
  if (server) {
    io.attach(server);
  }

  io.on("connection", (socket: Socket) => {
    console.log("Chat socket connected:", socket.id);

    let abortController: AbortController | null = null;

    socket.on("chat:message", async (data: { messages: Array<{ role: string; content: string }> }) => {
      abortController = new AbortController();
      try {
        // Forward to AI service via SSE stream
        const res = await fetch(`${opts.aiUrl}/chat/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
          signal: abortController?.signal,
        });

        if (!res.body) {
          socket.emit("chat:error", { message: "No response from AI service" });
          return;
        }

        // Stream chunks back to the client
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          // Parse SSE lines
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const dataStr = line.slice(6).trim();
              if (dataStr) {
                socket.emit("chat:response", { chunk: dataStr });
              }
            }
          }
        }

        // Send final marker
        socket.emit("chat:done");
      } catch (err) {
        socket.emit("chat:error", { message: String(err) });
      }
    });

    socket.on("disconnect", () => {
      if (abortController) abortController.abort();
    });
  });

  // Store io for later access if needed
  (app as any).io = io;
}
