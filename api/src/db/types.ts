/**
 * Database repository interfaces shared across storage backends.
 */

export interface Property {
  id: number;
  address_line1?: string;
  address_line2?: string | null;
  town?: string | null;
  postcode?: string | null;
  outcode?: string | null;
  property_type?: string;
  num_beds?: number;
  price_paid?: number;
  date_sold?: string | Date;
  latitude?: number | null;
  longitude?: number | null;
  source?: string;
}

export interface PropertyStore {
  getAll(): Promise<Property[]>;
  getLimited(limit: number): Promise<Property[]>;
  count(): Promise<number>;
  find(query: string): Promise<Property[]>;
  upsert(property: Partial<Property>): Promise<number>;
  clear?: () => Promise<void>;
}

// ---- In-memory property store (default implementation) ----------------------
export class InMemoryPropertyStore implements PropertyStore {
  private properties: Map<number, Property> = new Map();
  private counter = 1;

  async getAll(): Promise<Property[]> {
    return Array.from(this.properties.values());
  }

  async getLimited(limit: number): Promise<Property[]> {
    const all = await this.getAll();
    return all.slice(0, limit);
  }

  async count(): Promise<number> {
    return this.properties.size;
  }

  async find(query: string): Promise<Property[]> {
    const q = query.toLowerCase();
    const matches: Property[] = [];
    for (const prop of this.properties.values()) {
      const text = JSON.stringify(prop).toLowerCase();
      if (text.includes(q)) {
        matches.push(prop);
      }
    }

    return matches.slice(0, 50);
  }

  async upsert(property: Partial<Property>): Promise<number> {
    const id = this.counter++;
    const prop: Property = {
      id,
      address_line1: property.address_line1 ?? "",
      address_line2: property.address_line2 ?? null,
      town: property.town ?? null,
      postcode: property.postcode ?? null,
      outcode: property.outcode ?? null,
      property_type: property.property_type ?? "detached",
      num_beds: property.num_beds ?? 2,
      price_paid: property.price_paid ?? 300000,
      date_sold: property.date_sold ? new Date(property.date_sold) : new Date(),
      latitude: property.latitude ?? null,
      longitude: property.longitude ?? null,
      source: property.source ?? "land-registry",
    };

    this.properties.set(id, prop);
    return id;
  }

  async clear(): Promise<void> {
    this.properties.clear();
  }
}

