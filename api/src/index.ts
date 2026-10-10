/**
 * Entry point — bootstraps the Fastify server with WebSocket support.
 */

import { config, validateConfig, validateDatabaseUrl } from "./config";
import { buildApp } from "./app";
import { attachChatSocket } from "./ws/chat.socket";


async function main() {
  console.log("[API] Environment variables loaded");
  validateConfig();
  validateDatabaseUrl();

  const app = await buildApp();

  // Ensure the Fastify app is ready before attaching Socket.IO
  await app.ready();

  // Attach WebSocket bridge for real-time chat - pass HTTP server directly
  attachChatSocket(app.server, { corsOrigin: config.corsOrigin });

  const port = config.port;
  await app.listen({ port, host: "0.0.0.0" });
  console.log(`Abode API server listening on http://localhost:${port}`);
}

main().catch((err) => {
  console.error("Failed to start API server:", err);
  process.exit(1);
});