/**
 * Password hashing and verification using bcrypt (server-side).
 */

import bcrypt from 'bcryptjs';

const SALT_ROUNDS = 12; // Higher rounds for production security

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
export async function validatePassword(password: string): Promise<{ valid: boolean; message?: string }> {
  // Length requirement - modern standard is 12+ characters
  if (password.length < 12) {
    return { 
      valid: false, 
      message: `Password must be at least ${12} characters` 
    };
  }
  
  // Check for complexity requirements
  const hasUppercase = /[A-Z]/.test(password);
  const hasLowercase = /[a-z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecialChar = /[^A-Za-z0-9]/.test(password);
  
  if (!hasUppercase) {
    return { valid: false, message: 'Password must contain at least one uppercase letter' };
  }
  
  if (!hasLowercase) {
    return { valid: false, message: 'Password must contain at least one lowercase letter' };
  }
  
  if (!hasNumber) {
    return { valid: false, message: 'Password must contain at least one number' };
  }
  
  if (!hasSpecialChar) {
    return { valid: false, message: 'Password must contain at least one special character' };
  }
  
  // Check for common passwords
  const COMMON_PASSWORDS = ['password', '123456', 'admin', 'welcome', 'monkey'];
  if (COMMON_PASSWORDS.some(c => password.toLowerCase().includes(c))) {
    return { valid: false, message: 'Password cannot contain common words or numbers' };
  }
  
  // Check for adjacent keyboard keys (e.g., "qwerty")
  const ADJACENT_KEYS = [
    ['q', 'w', 'e', 'r', 't', 'y'],
    ['z', 'x', 'c', 'v', 'b', 'n', 'm'],
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']
  ];
  
  const lowercasePassword = password.toLowerCase();
  for (const adjacent of ADJACENT_KEYS) {
    if (adjacent.length >= 3) {
      const pattern = new RegExp('[' + adjacent.join('|') + `]{${adjacent.length - 2},}`, 'i');
      if (pattern.test(lowercasePassword)) {
        return { 
          valid: false, 
          message: 'Password should not contain adjacent keyboard key patterns' 
        };
      }
    }
  }
  
  // Check for repeated characters
  const REPEATED_PATTERN = /(.)\1{2,}/;
  if (REPEATED_PATTERN.test(password)) {
    return { valid: false, message: 'Password cannot contain three or more repeated characters' };
  }
  
  return { valid: true };
}
