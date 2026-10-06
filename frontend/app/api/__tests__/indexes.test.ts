import { describe, it, expect } from "vitest";
import { GET } from "@/app/api/indexes/route";

describe("GET /api/indexes", () => {
  it("returns 200 with Content-Type application/json", async () => {
    const res = GET();
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("application/json");
  });

  it("returns an array of indexes", async () => {
    const res = GET();
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
    expect(body.length).toBeGreaterThan(0);
  });

  it("every entry has required fields", async () => {
    const res = GET();
    const body = await res.json();
    const required = ["id", "name", "sector", "org", "source", "description", "citation"];
    for (const entry of body) {
      for (const field of required) {
        expect(entry, `Missing field '${field}' in entry ${entry.id}`).toHaveProperty(
          field
        );
      }
    }
  });

  it("has entries across multiple sectors", async () => {
    const res = GET();
    const body = await res.json();
    const sectors = new Set(body.map((e: { sector: string }) => e.sector));
    expect(sectors.size).toBeGreaterThanOrEqual(5);
  });
});
