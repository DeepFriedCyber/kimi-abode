/**
 * Entry point — bootstraps the Fastify server with WebSocket support.
 */

import { config, validateConfig } from "./config";
import buildApp from "./app";
import { attachChatSocket } from "./ws/chat.socket";

async function main() {
  validateConfig();

  const app = await buildApp();

  // Attach WebSocket bridge for real-time chat
  attachChatSocket(app, { aiUrl: config.aiServiceUrl, corsOrigin: config.corsOrigin });

  const port = config.port;
  await app.listen({ port, host: "0.0.0.0" });
  console.log(`Abode API server listening on http://localhost:${port}`);
}

main().catch((err) => {
  console.error("Failed to start API server:", err);
  process.exit(1);
});
