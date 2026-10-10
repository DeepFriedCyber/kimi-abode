/**
 * Fastify application builder with Zod validation and OpenAPI documentation.
 */

import { z } from 'zod';
import fastifySwagger from '@fastify/swagger';
import fastifySwaggerUi from '@fastify/swagger-ui';
import type { Property } from './db/types';

export async function buildApp() {
  const Fastify = (await import('fastify')).default;
  const app = Fastify({
    logger: true,
    trustProxy: true,
  });

  // ---- Register OpenAPI/Swagger plugin --------------------------------------
  await app.register(fastifySwagger, {
    openapi: {
      openapi: '3.0.0',
      info: {
        title: 'Abode API',
        description: 'Property search, AI parsing, authentication endpoints for Kimi Abode',
        version: '1.0.0',
        contact: {
          name: 'API Support',
        },
      },
      servers: [
        { url: process.env.API_URL || 'http://localhost:3001', description: 'Development server' },
      ],
      components: {
        securitySchemes: {
          BearerAuth: {
            type: 'http',
            scheme: 'bearer',
            bearerFormat: 'JWT',
            description: 'Enter your JWT token obtained from /api/auth/login',
          },
        },
      },
      security: [{ BearerAuth: [] }],
    },
  });

  await app.register(fastifySwaggerUi, {
    routePrefix: '/docs',
    uiConfig: {
      docExpansion: 'list',
      deepLinking: true,
    },
    staticCSP: false,
  });

  // ---- Middleware -----------------------------------------------------------
  
  // Request size limits
  app.addHook('onRequest', async (request, reply) => {
    const contentType = request.headers['content-type'];
    
    if (contentType && contentType.includes('application/json')) {
      const contentLength = parseInt(request.headers['content-length'] || '0', 10);
      
      // Reject oversized payloads (1MB limit for POST requests)
      if (contentLength > 1_000_000) {
        throw new Error('Payload too large. Maximum size is 1MB');
      }
    }

    // Log request ID for tracing
    const requestId = request.headers['x-request-id'] || crypto.randomUUID();
    console.log(`[${requestId}] ${request.method} ${request.url}`);
  });

  // ---- Health check routes --------------------------------------------------
  app.get("/", async (request, reply) => {
    return { 
      status: "ok", 
      version: "1.0.0",
      services: {
        ai_service: process.env.AI_SERVICE_URL || "http://localhost:8001",
      },
    };
  });

  app.get("/health", async (request, reply) => ({ 
    status: "healthy",
    timestamp: new Date().toISOString(),
  }));

  // ---- Schemas for request validation ----------------------------------------
  const aiServiceUrl = process.env.AI_SERVICE_URL || "http://localhost:8001/api/parse";

  // Schema for /api/parse endpoint
  export interface ParseQuery {
    query: string;
  }

  const parseSchema = z.object({
    query: z.string().min(1, "Query must not be empty"),
  });

  // Schema for /api/search endpoint
  export interface SearchQuery {
    q: string;
    min_beds?: number;
    max_price?: number;
    property_type?: string;
  }

  const searchSchema = z.object({
    q: z.string().min(1, "Search query must not be empty").max(500, "Query too long (max 500 chars)"),
    min_beds: z.coerce.number().optional(),
    max_price: z.coerce.number().optional(),
    property_type: z.string().optional(),
  });

  // Schema for registration
  export interface RegisterRequest {
    email: string;
    password: string;
    name: string;
  }

  const registerSchema = z.object({
    email: z.string().email(),
    password: z.string().min(12, "Password must be at least 12 characters"),
    name: z.string().min(2),
  });

  // Schema for login
  export interface LoginRequest {
    email: string;
    password: string;
  }

  const loginSchema = z.object({
    email: z.string().email(),
    password: z.string().min(1),
  });

  /**
   * Search endpoint with AI Service proxy
   * @openapi
   * /api/search:
   *   get:
   *     summary: Search for properties
   *     description: Proxy search query to AI service, returns matching properties with filters. Supports natural language queries and structured parameters.
   *     tags: [Search]
   *     parameters:
   *       - name: q
   *         in: query
   *         required: true
   *         description: Natural language search query (e.g., "detached house", "3 bed under 300k")
   *         schema: { type: string, minLength: 1, maxLength: 500 }
   *       - name: min_beds
   *         in: query
   *         description: Minimum number of bedrooms (filter)
   *         schema: { type: integer }
   *       - name: max_price
   *         in: query
   *         description: Maximum price in GBP (filter)
   *         schema: { type: number }
   *       - name: property_type
   *         in: query
   *         description: Property type filter (e.g., "detached", "terraced", "flat")
   *         schema: { type: string }
   *     responses:
   *       '200':
   *         description: Search results with matching properties
   *         content:
   *           application/json:
   *             schema:
   *               $ref: '#/components/schemas/SearchResult'
   */
  app.get("/api/search", async (request, reply) => {
    try {
      const query = searchSchema.parse(request.query);
      
      const params = new URLSearchParams();
      params.set('q', query.q);
      if (query.min_beds) params.set('min_beds', String(query.min_beds));
      if (query.max_price) params.set('max_price', String(query.max_price));
      if (query.property_type) params.set('property_type', query.property_type);

      // Proxy to AI service with timeout
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 30_000); // 30s timeout
      
      const response = await fetch(`${aiServiceUrl}?${params}`, { signal: controller.signal });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'AI Service unavailable' }));
        
        return reply.status(503).send({ 
          error: errorData.message || "AI Service unavailable",
          properties: [] as Property[],
          total_matches: 0,
          tier_used: "keyword",
          timestamp: new Date().toISOString(),
        });
      }
      
      const data = await response.json();
      
      // Validate response structure
      if (!data.properties && !Array.isArray(data.properties)) {
        console.warn("AI Service returned unexpected response format");
      }
      
      return data;
    } catch (error) {
      console.error("Search error:", error);
      
      // Handle validation errors from Zod
      if ('errors' in error && Array.isArray(error.errors)) {
        return reply.status(400).send({ 
          error: error.errors[0].message,
          properties: [] as Property[],
          total_matches: 0,
          tier_used: "keyword",
          timestamp: new Date().toISOString(),
        });
      }
      
      // Handle timeout or other errors
      if (error instanceof Error && error.name === 'AbortError') {
        return reply.status(408).send({ 
          error: "Request timed out. Please try again.",
          properties: [] as Property[],
          total_matches: 0,
          tier_used: "keyword",
          timestamp: new Date().toISOString(),
        });
      }
      
      return reply.status(500).send({ 
        error: error instanceof Error ? error.message : "Search failed",
        properties: [] as Property[],
        total_matches: 0,
        tier_used: "keyword",
        timestamp: new Date().toISOString(),
      });
    }
  });

  /**
   * Parse endpoint with AI Service proxy
   * @openapi
   * /api/parse:
   *   post:
   *     summary: Parse natural language query
   *     description: Converts user's search query to structured fields (min_beds, max_price, location, property types, etc.) using AI/LLM. This is the core search functionality that enables natural language queries like "detached house in Sandbach".
   *     tags: [Search]
   *     requestBody:
   *       required: true
   *       content:
   *         application/json:
   *           schema:
   *             type: object
   *             required: [query]
   *             properties:
   *               query: { 
   *                 type: string, 
   *                 description: "Natural language search query (e.g., '3 bed detached house under 400k')",
   *                 minLength: 1 
   *               }
   *     responses:
   *       '200':
   *         description: Parsed query with structured entities
   *         content:
   *           application/json:
   *             schema:
   *               type: object
   *               properties:
   *                 tier: { 
   *                   type: string, 
   *                   description: "Processing tier used (semantic, keyword)" 
   *                 }
   *                 min_beds: { type: number, nullable: true }
   *                 max_price: { type: number, nullable: true }
   *                 property_types: { 
   *                   type: array, 
   *                   items: { type: string },
   *                   description: "e.g., ['detached', 'semi']"
   *                 }
   *                 location: { type: string, nullable: true }
   *                 district: { type: string, nullable: true }
   */
  app.post("/api/parse", async (request, reply) => {
    try {
      const body = parseSchema.parse(request.body);
      
      const params = new URLSearchParams({ q: body.query });
      
      // Proxy to AI service with timeout
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 30_000); // 30s timeout
      
      const response = await fetch(`${aiServiceUrl}?${params}`, { 
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json' },
      });
      
      if (!response.ok) {
        return reply.status(503).send({ error: "AI Service unavailable", timestamp: new Date().toISOString() });
      }
      
      const data = await response.json();
      
      // Validate response structure
      if (!data && typeof data !== 'object') {
        console.warn("AI Service returned unexpected response format");
      }
      
      return data;
    } catch (error) {
      console.error("Parse error:", error);
      
      // Handle validation errors from Zod
      if ('errors' in error && Array.isArray(error.errors)) {
        return reply.status(400).send({ 
          error: error.errors[0].message,
          timestamp: new Date().toISOString(),
        });
      }
      
      // Handle timeout or other errors
      if (error instanceof Error && error.name === 'AbortError') {
        return reply.status(408).send({ 
          error: "Request timed out. Please try again.",
          timestamp: new Date().toISOString(),
        });
      }
      
      return reply.status(500).send({ 
        error: error instanceof Error ? error.message : "Parse failed",
        timestamp: new Date().toISOString(),
      });
    }
  });

}

export default buildApp;