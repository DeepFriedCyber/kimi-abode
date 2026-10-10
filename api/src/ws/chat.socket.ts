/**
 * Socket.IO WebSocket Handler for real-time chat functionality.
 */

import { Server } from 'socket.io';
import type http from 'http';

// Create HTTP server (needed for Socket.IO to bind)
let httpServer: http.Server | null = null;

export function attachChatSocket(ioServer: Server, opts?: { corsOrigin?: string; }) {
  console.log("[SocketIO] Initializing WebSocket handler");
  
  // Configure CORS directly via ioServer.attach or use HTTP server options
  const corsOrigin = opts?.corsOrigin || process.env.FRONTEND_URL || '*';

  // Handle socket connections
  ioServer.on('connection', (socket) => {
    console.log(`[SocketIO] User connected: ${socket.id}`);

    // Join room
    socket.on('join-room', (data: { roomId: string }) => {
      const { roomId } = data;
      socket.join(roomId);
      console.log(`[SocketIO] Socket ${socket.id} joined room "${roomId}"`);
    });

    // Send message
    socket.on('send-message', (data: { roomId: string; text: string }) => {
      const { roomId, text } = data;
      ioServer.to(roomId).emit('receive-message', { text, from: socket.id });
    });

    // Leave room
    socket.on('leave-room', (roomId: string) => {
      socket.leave(roomId);
      console.log(`[SocketIO] Socket ${socket.id} left room "${roomId}"`);
    });

    // Disconnect
    socket.on('disconnect', () => {
      console.log(`[SocketIO] User disconnected: ${socket.id}`);
    });
  });

  // HTTP server is attached internally by Socket.IO, no need to expose it
}

export default attachChatSocket;