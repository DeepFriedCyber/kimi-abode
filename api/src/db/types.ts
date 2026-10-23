/**
 * Property domain types and the in-memory store implementation.
 *
 * This is the single in-memory implementation used by every layer (the API
 * gateway and tests). Storage backends implement the same `PropertyStore`
 * contract.
 */

export interface Property {
  id: number;
  address_line1: string;
  address_line2?: string | null;
  town?: string | null;
  postcode?: string | null;
  outcode?: string | null;
  property_type?: string | null;
  num_beds?: number | null;
  price_paid?: number | null;
  date_sold?: string | Date | null;
  latitude?: number | null;
  longitude?: number | null;
  source?: string | null;
}

export interface PropertyStore {
  readonly driver: string;
  getAll(): Promise<Property[]>;
  getLimited(limit: number): Promise<Property[]>;
  count(): Promise<number>;
  find(query: string): Promise<Property[]>;
  upsert(property: Partial<Property>): Promise<number>;
  clear(): Promise<void>;
}

/** Stable identity for deduplication: address + postcode, case-insensitive. */
export function propertyKey(property: Partial<Property>): string {
  const address = (property.address_line1 ?? "").trim().toLowerCase();
  const postcode = (property.postcode ?? "").trim().toLowerCase();
  return `${address}|${postcode}`;
}

function searchBlob(property: Property): string {
  return [
    property.address_line1,
    property.address_line2,
    property.town,
    property.postcode,
    property.outcode,
    property.property_type,
    property.source,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export class InMemoryPropertyStore implements PropertyStore {
  readonly driver = "memory";

  private readonly properties = new Map<number, Property>();
  private readonly idsByKey = new Map<string, number>();
  private readonly blobs = new Map<number, string>();
  private nextId = 1;

  async getAll(): Promise<Property[]> {
    return [...this.properties.values()];
  }

  async getLimited(limit: number): Promise<Property[]> {
    const safeLimit = Math.max(0, Math.floor(limit));
    return [...this.properties.values()].slice(0, safeLimit);
  }

  async count(): Promise<number> {
    return this.properties.size;
  }

  async find(query: string): Promise<Property[]> {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];

    const matches: Property[] = [];
    for (const [id, property] of this.properties) {
      if (this.blobs.get(id)?.includes(needle)) {
        matches.push(property);
        if (matches.length >= 50) break;
      }
    }
    return matches;
  }

  async upsert(input: Partial<Property>): Promise<number> {
    const key = propertyKey(input);
    const existingId = this.idsByKey.get(key);

    const id = existingId ?? input.id ?? this.nextId++;
    if (id >= this.nextId) this.nextId = id + 1;

    const existing = existingId !== undefined ? this.properties.get(existingId) : undefined;
    const merged: Property = {
      ...existing,
      ...stripUndefined(input),
      id,
      address_line1: input.address_line1 ?? existing?.address_line1 ?? "",
      property_type: input.property_type ?? existing?.property_type ?? "unknown",
      source: input.source ?? existing?.source ?? "land-registry",
    };

    this.properties.set(id, merged);
    this.idsByKey.set(key, id);
    this.blobs.set(id, searchBlob(merged));
    return id;
  }

  async clear(): Promise<void> {
    this.properties.clear();
    this.idsByKey.clear();
    this.blobs.clear();
    this.nextId = 1;
  }
}

function stripUndefined<T extends object>(value: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(value).filter(([, v]) => v !== undefined),
  ) as Partial<T>;
}
