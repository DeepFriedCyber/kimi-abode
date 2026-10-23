/**
 * Process entry point: build the app, attach Socket.IO, listen, shut down
 * cleanly on SIGINT/SIGTERM.
 */

import { buildApp } from "./app";
import { config, validateConfig } from "./config";
import { attachChatSocket } from "./ws/chat.socket";

async function main(): Promise<void> {
  validateConfig();

  const app = await buildApp();
  await app.ready();

  attachChatSocket(app.server, {
    aiUrl: config.aiServiceUrl,
    corsOrigin: config.corsOrigins,
  });

  await app.listen({ port: config.port, host: config.host });
  app.log.info(
    { port: config.port, aiServiceUrl: config.aiServiceUrl },
    "Abode API listening",
  );

  let shuttingDown = false;
  const shutdown = async (signal: string): Promise<void> => {
    if (shuttingDown) return;
    shuttingDown = true;
    app.log.info({ signal }, "Shutting down");
    try {
      await app.close();
      process.exit(0);
    } catch (error) {
      app.log.error({ err: error }, "Error during shutdown");
      process.exit(1);
    }
  };

  process.on("SIGINT", () => void shutdown("SIGINT"));
  process.on("SIGTERM", () => void shutdown("SIGTERM"));
  process.on("unhandledRejection", (reason) => {
    app.log.error({ err: reason }, "Unhandled promise rejection");
  });
}

main().catch((error) => {
  console.error("Failed to start API server:", error);
  process.exit(1);
});
