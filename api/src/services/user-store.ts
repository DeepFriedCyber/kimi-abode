/**
 * User store for managing user authentication and profile data using PostgreSQL.
 */

import { Pool } from 'pg';
import type { Property } from '../db/types';
import { hashPassword, comparePassword } from './passwords';

// Initialize database pool
const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgres://postgres:postgres@localhost:5432/abode',
});

/**
 * Find a user by email.
 */
export async function findUserByEmail(email: string): Promise<any | null> {
  const client = await pool.connect();
  try {
    const result = await client.query(
      'SELECT id, email, name, created_at FROM users WHERE email = $1',
      [email]
    );
    
    if (result.rows.length === 0) {
      return null;
    }
    
    return { ...result.rows[0], password_hash: undefined }; // Exclude password hash
  } finally {
    client.release();
  }
}

/**
 * Create a new user.
 */
export async function createUser(
  email: string,
  name: string,
  password: string
): Promise<{ id: number; email: string }> {
  // Validate and hash password
  const valid = await validatePasswordForCreation(password);
  
  if (!valid.valid) {
    throw new Error(valid.message || 'Invalid password');
  }
  
  const hashedPassword = await hashPassword(password);
  
  const client = await pool.connect();
  try {
    const result = await client.query(
      `INSERT INTO users (email, name, password_hash, created_at) 
       VALUES ($1, $2, $3, NOW()) 
       RETURNING id, email`,
      [email, name, hashedPassword]
    );
    
    return { id: result.rows[0].id, email: result.rows[0].email };
  } finally {
    client.release();
  }
}

/**
 * Validate password during user creation.
 */
async function validatePasswordForCreation(password: string): Promise<{ valid: boolean; message?: string }> {
  if (password.length < 8) {
    return { valid: false, message: 'Password must be at least 8 characters' };
  }
  
  if (!/[A-Z]/.test(password)) {
    return { valid: false, message: 'Password must contain an uppercase letter' };
  }
  
  if (!/[a-z]/.test(password)) {
    return { valid: false, message: 'Password must contain a lowercase letter' };
  }
  
  if (!/[0-9]/.test(password)) {
    return { valid: false, message: 'Password must contain a number' };
  }
  
  if (!/[^A-Za-z0-9]/.test(password)) {
    return { valid: false, message: 'Password must contain a special character' };
  }
  
  return { valid: true };
}

/**
 * Authenticate user and create session token.
 */
export async function authenticateUser(email: string, password: string): Promise<{ 
  user: any; 
  access_token: string; 
}> {
  const user = await findUserByEmail(email);
  
  if (!user) {
    throw new Error('Invalid credentials');
  }
  
  // Verify password
  const isValid = await comparePassword(password, user.password_hash!);
  
  if (!isValid) {
    throw new Error('Invalid credentials');
  }
  
  return {
    user: { id: user.id, email: user.email, name: user.name },
    access_token: `mock-${user.id}-${Date.now()}`, // In production, use JWT or similar
  };
}

/**
 * Update user profile.
 */
export async function updateUserProfile(
  userId: number,
  updates: { name?: string; email?: string }
): Promise<any> {
  const client = await pool.connect();
  try {
    const { name, email } = updates;
    
    if (!name) {
      throw new Error('Name cannot be empty');
    }
    
    // Check if email already exists
    if (email) {
      const existing = await findUserByEmail(email);
      if (existing && existing.id !== userId) {
        throw new Error('Email already in use');
      }
    }
    
    let query = 'UPDATE users SET ';
    const values: any[] = [];
    let paramCount = 0;
    
    if (name) {
      query += `name = $${++paramCount},`;
      values.push(name);
    }
    
    if (email) {
      query += `email = $${++paramCount},`;
      values.push(email);
    }
    
    query = query.slice(0, -1) + ' WHERE id = $' + ++paramCount;
    values.push(userId);
    
    const result = await client.query(query, values);
    return { success: true };
  } finally {
    client.release();
  }
}

/**
 * Delete a user.
 */
export async function deleteUser(userId: number): Promise<void> {
  const client = await pool.connect();
  try {
    await client.query('DELETE FROM users WHERE id = $1', [userId]);
  } finally {
    client.release();
  }
}

/**
 * Get all users (for admin purposes).
 */
export async function getAllUsers(): Promise<any[]> {
  const client = await pool.connect();
  try {
    const result = await client.query(
      'SELECT id, email, name, created_at FROM users'
    );
    return result.rows.map(row => ({ ...row, password_hash: undefined }));
  } finally {
    client.release();
  }
}

// Export types for TypeScript
export interface User {
  id: number;
  email: string;
  name: string;
  created_at?: string;
}

export interface AuthResult {
  user: User;
  access_token: string;
}
