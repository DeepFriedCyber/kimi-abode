/**
 * Fastify application builder with Zod validation.
 */

import { z } from 'zod';

export async function buildApp(): Promise<any> {
  const Fastify = (await import("fastify")).default;
  const app = Fastify({
    logger: true,
    trustProxy: true,
  });

  // ---- Health check routes -------------------------------------------------
  app.get("/", async () => ({ status: "ok" }));
  app.get("/health", async () => ({ status: "healthy" }));

  // ---- Schemas for request validation --------------------------------------------
  const aiServiceUrl = process.env.AI_SERVICE_URL || "http://localhost:8001/api/parse";

  // Schema for /api/parse endpoint
  const parseSchema = z.object({
    query: z.string().min(1, "Query must not be empty"),
  });

  // Schema for /api/search endpoint
  const searchSchema = z.object({
    q: z.string().min(1, "Search query must not be empty"),
    min_beds: z.coerce.number().optional(),
    max_price: z.coerce.number().optional(),
    property_type: z.string().optional(),
  });

  // Schema for registration
  const registerSchema = z.object({
    email: z.string().email(),
    password: z.string().min(8, "Password must be at least 8 characters"),
    name: z.string().min(2),
  });

  // Schema for login
  const loginSchema = z.object({
    email: z.string().email(),
    password: z.string().min(8),
  });

  // ---- Search endpoint with AI Service proxy --------------------------------
  app.get("/api/search", async (request, reply) => {
    try {
      const query = searchSchema.parse(request.query);
      
      const params = new URLSearchParams();
      params.set('q', query.q);
      if (query.min_beds) params.set('min_beds', String(query.min_beds));
      if (query.max_price) params.set('max_price', String(query.max_price));
      if (query.property_type) params.set('property_type', query.property_type);

      const response = await fetch(`${aiServiceUrl}?${params}`);
      
      if (!response.ok) {
        return reply.status(503).send({ error: "AI Service unavailable" });
      }
      
      return await response.json();
    } catch (error: any) {
      console.error("Search error:", error.message);
      return reply.status(500).send({ 
        error: error.errors ? error.errors[0].message : "Search failed",
        properties: [],
        total_matches: 0,
        tier_used: "keyword",
      });
    }
  });

  // ---- Parse endpoint with AI Service proxy --------------------------------
  app.post("/api/parse", async (request, reply) => {
    try {
      const body = parseSchema.parse(request.body);
      
      const params = new URLSearchParams({ q: body.query });
      const response = await fetch(`${aiServiceUrl}?${params}`);
      
      if (!response.ok) {
        return reply.status(503).send({ error: "AI Service unavailable" });
      }
      
      return await response.json();
    } catch (error: any) {
      console.error("Parse error:", error.message);
      return reply.status(400).send({ 
        error: error.errors ? error.errors[0].message : "Parse failed",
      });
    }
  });

  // ---- Auth routes with Zod validation --------------------------------------
  app.post("/api/auth/register", async (request, reply) => {
    try {
      const body = registerSchema.parse(request.body);
      
      // Placeholder for registration logic
      return reply.status(201).send({ 
        id: 1, 
        email: body.email,
        name: body.name,
        message: "User registered successfully",
      });
    } catch (error: any) {
      console.error("Registration error:", error.message);
      return reply.status(400).send({ 
        error: error.errors ? error.errors[0].message : "Registration failed",
      });
    }
  });

  app.post("/api/auth/login", async (request, reply) => {
    try {
      const body = loginSchema.parse(request.body);
      
      // Placeholder for login logic
      return reply.status(200).send({ 
        access_token: "test-token-" + Date.now(),
        token_type: "Bearer",
        user: { id: 1, email: body.email },
      });
    } catch (error: any) {
      console.error("Login error:", error.message);
      return reply.status(401).send({ 
        error: error.errors ? error.errors[0].message : "Invalid credentials",
      });
    }
  });

  // ---- Metrics endpoint (Prometheus format) --------------------------------
  app.get("/metrics", async () => "# HELP requests_total\n# TYPE requests_total counter\n");

  return app;
}
