/**
 * Property Repository — Database abstraction for property search and retrieval.
 * Simplified implementation using only InMemoryPropertyStore.
 */

import type { Property, PropertyStore } from "./types";
import { InMemoryPropertyStore } from "./types";

export class PropertyRepository implements PropertyStore {
  private repo: InMemoryPropertyStore;

  constructor() {
    // Always use InMemoryPropertyStore for simplicity and reliability
    console.log("[PropertyRepository] Using in-memory store (simplified implementation)");
    this.repo = new InMemoryPropertyStore();
  }

  async getAll(): Promise<Property[]> {
    return this.repo.getAll();
  }

  async getLimited(limit: number): Promise<Property[]> {
    const all = await this.repo.getAll();
    return all.slice(0, limit);
  }

  async count(): Promise<number> {
    const all = await this.repo.getAll();
    return all.length;
  }

  async find(query: string): Promise<Property[]> {
    const results = await this.repo.find(query);
    return results.slice(0, 50);
  }

  async upsert(property: Partial<Property>): Promise<number> {
    // In-memory store always creates new entries with incremented ID
    return await this.repo.upsert({
      ...property,
      id: Date.now() % 1000000, // Simple ID generation for in-memory
    });
  }

  async clear(): Promise<void> {
    console.log("[PropertyRepository] In-memory fallback - cleared");
    await this.repo.clear();
  }
}