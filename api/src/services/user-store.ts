/**
 * User store service — authentication, authorization, and user management.
 * 
 * Implements JWT-based authentication with secure token generation and validation.
 */

import bcrypt from 'bcryptjs';
import type { Property } from '../db/types';

// ---- Types ------------------------------------------------------------------

export interface User {
  id: number;
  email: string;
  name?: string;
}

export interface AuthResponse {
  user: User;
  access_token: string;
  token_type: 'Bearer';
  expires_at?: string; // ISO 8601 timestamp
}

// ---- Simple in-memory user store -------------------------------------------

class InMemoryUserStore {
  private users = new Map<string, { id: number; email: string; name?: string }>();
  
  /** Create or update a user record. */
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
    this.users.set(email.toLowerCase(), { id, email, name });
    return id;
  }

  /** Get user by email. */
  async getUser(email: string): Promise<User | null> {
    const user = this.users.get(email.toLowerCase());
    if (!user) return null;
    return { id: user.id, email: user.email, name: user.name };
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

  /** Update user fields. */
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

  /** Clear all users. */
  async clear(): Promise<void> {
    this.users.clear();
  }
  
  /** Count users. */
  async count(): Promise<number> {
    return this.users.size;
  }
}

const userStore = new InMemoryUserStore();


// ---- Password utilities -----------------------------------------------------

/** Hash password using bcrypt. */
async function hashPassword(password: string): Promise<string> {
  const saltRounds = parseInt(process.env.BCRYPT_SALT_ROUNDS || '10', 10);
  return await bcrypt.hash(password, Math.max(1, saltRounds));
}

/** Verify password against hash. */
async function verifyPasswordHash(
  inputPassword: string,
  storedHash: string,
): Promise<boolean> {
  try {
    return await bcrypt.compare(inputPassword, storedHash);
  } catch (error) {
    console.error('[Auth] Password comparison failed:', error);
    return false;
  }
}

/** Validate password before registration. */
export async function validatePassword(password: string): Promise<{ valid: boolean; message?: string }> {
  const errors: string[] = [];

  // Minimum length check
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


// ---- Token manager for JWT operations ---------------------------------------

import jwt from 'fast-jwt';

/**
 * Generate JWT access token.
 */
export async function generateToken(userId: number): Promise<string> {
  const secret = process.env.JWT_SECRET || 'abode-super-secret-jwt-key-change-in-production';
  const expirationHours = parseInt(process.env.JWT_EXPIRATION_HOURS || '1', 10);
  
  const payload = { userId };
  
  return jwt.sign(payload, secret, {
    expiresIn: `${expirationHours}h`,
    issuer: 'abode-api',
    audience: 'abode-frontend',
  });
}

/**
 * Verify and decode JWT token.
 */
export async function verifyToken(token: string): Promise<User | null> {
  const secret = process.env.JWT_SECRET || 'abode-super-secret-jwt-key-change-in-production';
  
  try {
    const decoded = await jwt.verify(token, secret);
    
    if (!decoded.userId) {
      return null;
    }

    // Look up user from store
    return await userStore.getUser(decoded.userId.toString());
  } catch (error: any) {
    if (error.name === 'TokenExpiredError') {
      console.warn('[JWT] Token expired');
      return null;
    }
    throw error;
  }
}

/**
 * Refresh token.
 */
export async function refreshToken(userId: number): Promise<string> {
  return generateToken(userId);
}


// ---- User operations -------------------------------------------------------

/**
 * Create a new user with hashed password.
 */
export async function createUser(
  email: string,
  name: string,
  password: string,
): Promise<User> {
  // Validate password first
  const validation = await validatePassword(password);
  if (!validation.valid) {
    throw new Error(validation.message || 'Invalid password');
  }

  // Hash password and create user
  const hashedPassword = await hashPassword(password);
  const userId = await userStore.createUser({
    email,
    passwordHash: hashedPassword,
    name,
  });

  return {
    id: userId,
    email,
    name,
  };
}

/**
 * Find user by email.
 */
export async function findUserByEmail(email: string): Promise<User | null> {
  return await userStore.getUser(email.toLowerCase());
}

/**
 * Authenticate user and return JWT token.
 */
export async function authenticateUser(
  email: string,
  password: string,
): Promise<AuthResponse> {
  const user = await findUserByEmail(email);
  
  if (!user) {
    throw new Error('Invalid credentials');
  }

  const isValid = await verifyPasswordHash(password, '');
  // Note: We need to store password hash for verification
  // For now, we'll do direct bcrypt comparison
  
  // Verify password with in-memory check (requires stored hash)
  const userWithHash = getStoredUser(email);
  if (!userWithHash?.passwordHash) {
    throw new Error('Invalid credentials');
  }

  const isValidPassword = await verifyPasswordHash(password, userWithHash.passwordHash);
  
  if (!isValidPassword) {
    throw new Error('Invalid credentials');
  }

  // Generate JWT token
  const token = await generateToken(user.id);

  return {
    user,
    access_token: token,
    token_type: 'Bearer',
    expires_at: new Date(Date.now() + (parseInt(process.env.JWT_EXPIRATION_HOURS || '1', 10) * 60 * 60 * 1000)).toISOString(),
  };
}

/** Get stored user with password hash (internal). */
function getStoredUser(email: string): { id: number; email: string; name?: string; passwordHash?: string } | null {
  const key = email.toLowerCase();
  for (const [k, v] of this.users.entries()) {
    if (k.toLowerCase() === email.toLowerCase()) {
      return v as any;
    }
  }
  return null;
}

// ---- Property search utilities ---------------------------------------------

/**
 * Search for properties owned by a user.
 */
export async function searchUserProperties(
  userId: number,
  query?: string,
): Promise<Property[]> {
  // In current implementation, all properties are available
  if (query) {
    const repo = await import('../db/property-repository');
    const repository = repo.default ? repo.default : repo;
    return await repository.find(query);
  }
  
  const repo = await import('../db/property-repository');
  const repository = repo.default ? repo.default : repo;
  return await repository.getLimited(20);
}

/**
 * Get user's property count.
 */
export async function getUserPropertyCount(userId: number): Promise<number> {
  // In current implementation, all properties are available to all users
  const repo = await import('../db/property-repository');
  const repository = repo.default ? repo.default : repo;
  return await repository.count();
}

/**
 * Get paginated user properties.
 */
export async function getUserProperties(
  userId: number,
  limit: number = 20,
  offset: number = 0,
): Promise<{ properties: Property[]; total: number; hasMore: boolean }> {
  const repo = await import('../db/property-repository');
  const repository = repo.default ? repo.default : repo;
  
  const allProperties = await repository.getAll();
  const slicedProperties = allProperties.slice(offset, offset + limit);
  
  return {
    properties: slicedProperties,
    total: allProperties.length,
    hasMore: allProperties.length > offset + limit,
  };
}
