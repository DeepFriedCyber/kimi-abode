/**
 * Password hashing and verification using bcryptjs.
 */

import bcrypt from 'bcryptjs';

const SALT_ROUNDS = 10;

/**
 * Hash a password with bcrypt.
 * @param password - The plain text password.
 * @returns The hashed password as a string.
 */
export async function hashPassword(password: string): Promise<string> {
  return await bcrypt.hash(password, SALT_ROUNDS);
}

/**
 * Compare a plain text password with a hashed password.
 * @param password - The plain text password.
 * @param hashedPassword - The pre-hashed password stored in the database.
 * @returns True if the passwords match.
 */
export async function comparePassword(
  password: string,
  hashedPassword: string
): Promise<boolean> {
  return await bcrypt.compare(password, hashedPassword);
}

/**
 * Validate a password meets minimum requirements.
 * @param password - The password to validate.
 * @returns Object with validity status and message.
 */
export function validatePassword(password: string): { valid: boolean; message?: string } {
  if (password.length < 8) {
    return { valid: false, message: 'Password must be at least 8 characters' };
  }
  
  // Check for at least one uppercase letter
  if (!/[A-Z]/.test(password)) {
    return { valid: false, message: 'Password must contain at least one uppercase letter' };
  }
  
  // Check for at least one lowercase letter
  if (!/[a-z]/.test(password)) {
    return { valid: false, message: 'Password must contain at least one lowercase letter' };
  }
  
  // Check for at least one number
  if (!/[0-9]/.test(password)) {
    return { valid: false, message: 'Password must contain at least one number' };
  }
  
  // Check for at least one special character
  if (!/[^A-Za-z0-9]/.test(password)) {
    return { valid: false, message: 'Password must contain at least one special character' };
  }
  
  return { valid: true };
}

/**
 * Generate a random salt (not used with bcrypt.js but available for reference).
 */
export function generateSalt(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()';
  let salt = '';
  for (let i = 0; i < SALT_ROUNDS; i++) {
    const index = Math.floor(Math.random() * chars.length);
    salt += chars[index];
  }
  return salt;
}
