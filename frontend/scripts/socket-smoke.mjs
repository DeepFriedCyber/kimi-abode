/**
 * Socket.IO smoke test.
 *
 * Connects to the gateway, sends one chat message and waits for the streamed
 * response. Run from the frontend directory so `socket.io-client` resolves.
 */

import { io } from "socket.io-client";

const socket = io("http://127.0.0.1:3001", {
  transports: ["websocket"],
  reconnection: false,
});

let received = "";

const timer = setTimeout(() => {
  console.error("FAIL: timed out", { received });
  socket.close();
  process.exit(1);
}, 20_000);

socket.on("connect", () => {
  socket.emit("chat:message", {
    messages: [{ role: "user", content: "hello from the socket smoke test" }],
  });
});

socket.on("chat:response", (payload) => {
  received += payload?.chunk ?? "";
});

socket.on("chat:done", () => {
  clearTimeout(timer);
  console.log(`OK: received ${received.length} chars: ${received.slice(0, 60).replace(/\n/g, " ")}`);
  socket.close();
  process.exit(received.length > 0 ? 0 : 1);
});

socket.on("chat:error", (payload) => {
  clearTimeout(timer);
  console.error("FAIL: chat error", payload);
  process.exit(1);
});

socket.on("connect_error", (error) => {
  clearTimeout(timer);
  console.error("FAIL: connect error", error.message);
  process.exit(1);
});
