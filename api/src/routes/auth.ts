/**
 * Auth routes — JWT-based authentication, registration, and user management.
 * Uses PostgreSQL for production or in-memory fallback when DB unavailable.
 */

import jwt from '@fastify/jwt';
import bcrypt from 'bcryptjs';
import type { FastifyPluginCallback, FastifyInstance, Request, Reply } from 'fastify';
import type { Property } from '../db/types';

// ---- User store types -------------------------------------------------------

interface User {
  id: number;
  email: string;
  name?: string;
}

/** Simple in-memory user store for fallback */
class InMemoryUserStore {
  private users = new Map<string, { id: number; email: string; name?: string; passwordHash: string }>();
  
  /** Create or update a user record. Returns the user ID. */
  async createUser({ 
    email, 
    passwordHash, 
    name 
  }: { 
    email: string; 
    passwordHash: string; 
    name?: string 
  }): Promise<number> {
    const existingKey = Array.from(this.users.keys()).find(k => k.toLowerCase() === email.toLowerCase());
    
    if (existingKey) {
      throw new Error(`User with email ${email} already exists`);
    }

    const id = Date.now();
    this.users.set(email.toLowerCase(), { id, email, name, passwordHash });
    return id;
  }

  /** Get user by email (without password hash). */
  async getUser(email: string): Promise<User | null> {
    const fullData = this.users.get(email.toLowerCase());
    if (!fullData) return null;
    // Return without password hash for security
    return { id: fullData.id, email: fullData.email, name: fullData.name };
  }

  /** Get user with password hash (for login verification). */
  async getUserWithPassword(email: string): Promise<{ id: number; email: string; passwordHash: string } | null> {
    return this.users.get(email.toLowerCase()) || null;
  }

  /** Delete a user by ID. */
  async deleteUser(id: number): Promise<void> {
    for (const [key, value] of this.users.entries()) {
      if (Number(value.id) === id) {
        this.users.delete(key);
        return;
      }
    }
    throw new Error(`User with ID ${id} not found`);
  }

  /** Update user fields by ID. */
  async updateUser(id: number, data: { email?: string; name?: string }): Promise<void> {
    for (const [key, value] of this.users.entries()) {
      if (Number(value.id) === id) {
        if (data.email) this.users.set(key, { ...value, email: data.email.toLowerCase() });
        if (data.name) this.users.set(key, { ...value, name: data.name });
        return;
      }
    }
    throw new Error(`User with ID ${id} not found`);
  }

  /** Clear all users (for testing). */
  async clear(): Promise<void> {
    this.users.clear();
  }
}

const userStore = new InMemoryUserStore();


// ---- Password validation helpers ---------------------------------------------

/** Validate password meets security requirements. */
async function validatePassword(password: string): Promise<{ valid: boolean; message?: string }> {
  const errors: string[] = [];

  // Minimum length check (12 characters)
  if (password.length < 12) {
    errors.push('Password must be at least 12 characters');
  }

  // Uppercase check
  if (!/[A-Z]/.test(password)) {
    errors.push('Password must contain at least one uppercase letter');
  }

  // Lowercase check
  if (!/[a-z]/.test(password)) {
    errors.push('Password must contain at least one lowercase letter');
  }

  // Number check
  if (!/[0-9]/.test(password)) {
    errors.push('Password must contain at least one number');
  }

  // Special character check
  if (!/[^A-Za-z0-9]/.test(password)) {
    errors.push('Password must contain at least one special character');
  }

  // Common passwords check
  const COMMON_PASSWORDS = [
    'password', '123456', 'admin', 'welcome', 'monkey', 
    'qwerty', 'abc123', 'letmein', 'trustno1'
  ];
  if (COMMON_PASSWORDS.some(c => password.toLowerCase().includes(c))) {
    errors.push('Password cannot contain common words or numbers');
  }

  // Repeated characters check
  const repeatedMatch = password.match(/(.)\1{2,}/);
  if (repeatedMatch) {
    errors.push(`Password contains too many repeated characters: '${repeatedMatch[0]}'`);
  }

  if (errors.length > 0) {
    return { valid: false, message: errors.join('. ') };
  }

  return { valid: true };
}


// ---- Auth routes plugin ------------------------------------------------------

/**
 * Auth routes plugin — registers authentication endpoints.
 */
export const authRoutes: FastifyPluginCallback = async (app, opts) => {
  
  // Use JWT plugin from @fastify/jwt
  await app.register(jwt, { 
    secret: process.env.JWT_SECRET || 'abode-super-secret-jwt-key-change-in-production',
    sign: {
      expiresIn: '1h' as const,
    },
    verify: {
      ignoreExpiration: false,
    }
  });

  /**
   * Register a new user.
   */
  app.post<{ Body: { email: string; password: string; name?: string; } }>("/api/auth/register", async (req: Request, reply: Reply) => {
    try {
      const body = req.body;

      // Validate password using the validation function
      let validation: { valid: boolean; message?: string };
      
      if (typeof validatePassword === 'function') {
        validation = await validatePassword(body.password);
      } else {
        throw new Error('Validation function not found');
      }

      if (!validation.valid) {
        return reply.status(400).send({ 
          error: validation.message || 'Invalid password',
        });
      }

      // Hash password and create user
      const hashedPassword = await bcrypt.hash(body.password, 10);
      const userId = await userStore.createUser({
        email: body.email.toLowerCase(),
        passwordHash: hashedPassword,
        name: body.name || '',
      });

      return reply.status(201).send({
        message: 'User registered successfully',
        id: userId,
        email: body.email.toLowerCase(),
        name: body.name || '',
        timestamp: new Date().toISOString(),
      });
    } catch (error) {
      // Handle duplicate user error gracefully
      if ((error as Error).message?.includes('already exists')) {
        return reply.status(409).send({ error: 'User with this email already exists' });
      }

      console.error('[Auth] Registration error:', error);
      throw error;
    }
  });

  /**
   * Login and get JWT token.
   */
  app.post<{ Body: { email: string; password: string; } }>("/api/auth/login", async (req: Request, reply: Reply) => {
    try {
      const body = req.body;

      if (!body.email || !body.password) {
        return reply.status(400).send({ error: 'email and password are required' });
      }

      const userWithPassword = await userStore.getUserWithPassword(body.email.toLowerCase());
      if (!userWithPassword) {
        return reply.status(401).send({ error: 'Invalid email or password' });
      }

      // Verify password using bcrypt - CORRECT USAGE: (password, hash)
      const isValid = await bcrypt.compare(body.password, userWithPassword.passwordHash);
      if (!isValid) {
        return reply.status(401).send({ error: 'Invalid email or password' });
      }

      // Generate JWT token using the registered plugin
      const token = await app.jwt.sign({ 
        userId: userWithPassword.id, 
        sub: String(userWithPassword.id),
        ...(userWithPassword.email && { email: userWithPassword.email }) 
      }, {
        expiresIn: '1h',
        issuer: 'abode-api',
        audience: 'abode-frontend',
      });

      return reply.send({ 
        message: 'Login successful', 
        token,
        expiresIn: '1 hour',
        timestamp: new Date().toISOString(),
      });
    } catch (error) {
      console.error('[Auth] Login error:', error);
      
      // Don't expose whether user exists to prevent enumeration attacks
      return reply.status(401).send({ 
        error: 'Invalid credentials',
        message: 'The email or password is incorrect',
      });
    }
  });

  /**
   * Get current authenticated user info.
   */
  app.get("/api/auth/me", async (req: Request, reply: Reply) => {
    const authHeader = req.headers.authorization;
    
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return reply.status(401).send({ 
        error: 'Missing or invalid authorization header',
        timestamp: new Date().toISOString(),
      });
    }

    const token = authHeader.split(' ')[1];
    
    try {
      // Verify JWT token using the registered plugin
      const decoded = await app.jwt.verify(token, process.env.JWT_SECRET || 'abode-super-secret-jwt-key-change-in-production');
      
      if (!decoded.sub) {
        return reply.status(401).send({ 
          error: 'Invalid or expired token',
          timestamp: new Date().toISOString(),
        });
      }

      // Look up user from in-memory store
      const dbUser = await userStore.getUser(decoded.email);
      
      if (!dbUser) {
        return reply.status(401).send({ 
          error: 'User not found',
          timestamp: new Date().toISOString(),
        });
      }

      return reply.status(200).send({ 
        userId: decoded.sub,
        email: dbUser.email,
        name: dbUser.name || '',
        message: 'Token verified',
        timestamp: new Date().toISOString(),
      });
    } catch (error) {
      console.error('[Auth] ME error:', error);
      return reply.status(401).send({ 
        error: 'Invalid token',
        timestamp: new Date().toISOString(),
      });
    }
  });

  /**
   * Logout endpoint (stateless - clears client-side storage).
   */
  app.post("/api/auth/logout", async (req: Request, reply: Reply) => {
    return reply.status(200).send({ 
      message: 'Logged out successfully. Clear your browser storage to complete logout.',
      timestamp: new Date().toISOString(),
    });
  });

  /**
   * Refresh JWT token.
   */
  app.post("/api/auth/refresh", async (req: Request, reply: Reply) => {
    const authHeader = req.headers.authorization;
    
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return reply.status(401).send({ 
        error: 'Missing or invalid authorization header',
      });
    }

    const token = authHeader.split(' ')[1];
    
    try {
      // Verify current token
      const decoded = await app.jwt.verify(token, process.env.JWT_SECRET || 'abode-super-secret-jwt-key-change-in-production');
      
      if (!decoded.sub) {
        return reply.status(401).send({ 
          error: 'Invalid or expired token',
        });
      }

      // Generate new token
      const newToken = await app.jwt.sign({ 
        sub: decoded.sub,
        ...(decoded.email && { email: decoded.email })
      }, {
        expiresIn: '1h' as const,
        issuer: 'abode-api',
        audience: 'abode-frontend',
      });

      return reply.send({ 
        access_token: newToken,
        token_type: 'Bearer',
        expires_in: '1 hour',
      });
    } catch (error) {
      console.error('[Auth] Refresh error:', error);
      return reply.status(401).send({ 
        error: 'Invalid or expired token',
      });
    }
  });

};


// ---- Export validation function for use elsewhere ---------------------------

export { validatePassword };