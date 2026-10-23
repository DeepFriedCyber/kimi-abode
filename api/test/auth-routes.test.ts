/**
 * Auth route integration tests using Fastify's inject().
 */

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { buildApp } from "../src/app";

const PASSWORD = "a long passphrase for testing";

describe("auth routes", () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    app = await buildApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  it("registers a user", async () => {
    const response = await app.inject({
      method: "POST",
      url: "/api/auth/register",
      payload: { email: "register@example.com", password: PASSWORD, name: "Test" },
    });

    expect(response.statusCode).toBe(201);
    const body = response.json();
    expect(body.user.email).toBe("register@example.com");
    expect(body.user.passwordHash).toBeUndefined();
  });

  it("rejects weak passwords", async () => {
    const response = await app.inject({
      method: "POST",
      url: "/api/auth/register",
      payload: { email: "weak@example.com", password: "short" },
    });

    expect(response.statusCode).toBe(400);
  });

  it("rejects malformed emails", async () => {
    const response = await app.inject({
      method: "POST",
      url: "/api/auth/register",
      payload: { email: "not-an-email", password: PASSWORD },
    });

    expect(response.statusCode).toBe(400);
    expect(response.json().error).toBe("Invalid request");
  });

  it("does not confirm whether an email is registered", async () => {
    await app.inject({
      method: "POST",
      url: "/api/auth/register",
      payload: { email: "dupe@example.com", password: PASSWORD },
    });

    const response = await app.inject({
      method: "POST",
      url: "/api/auth/register",
      payload: { email: "dupe@example.com", password: PASSWORD },
    });

    expect(response.statusCode).toBe(409);
    expect(response.json().error).not.toMatch(/already exists/i);
  });

  it("logs in and returns a usable token", async () => {
    await app.inject({
      method: "POST",
      url: "/api/auth/register",
      payload: { email: "login@example.com", password: PASSWORD, name: "Login" },
    });

    const login = await app.inject({
      method: "POST",
      url: "/api/auth/login",
      payload: { email: "login@example.com", password: PASSWORD },
    });

    expect(login.statusCode).toBe(200);
    const { access_token, user } = login.json();
    expect(typeof access_token).toBe("string");
    expect(user.email).toBe("login@example.com");

    const me = await app.inject({
      method: "GET",
      url: "/api/auth/me",
      headers: { authorization: `Bearer ${access_token}` },
    });

    expect(me.statusCode).toBe(200);
    expect(me.json().user.email).toBe("login@example.com");
  });

  it("rejects a wrong password with the same response as an unknown user", async () => {
    await app.inject({
      method: "POST",
      url: "/api/auth/register",
      payload: { email: "wrongpass@example.com", password: PASSWORD },
    });

    const wrongPassword = await app.inject({
      method: "POST",
      url: "/api/auth/login",
      payload: { email: "wrongpass@example.com", password: `${PASSWORD}x` },
    });

    const unknownUser = await app.inject({
      method: "POST",
      url: "/api/auth/login",
      payload: { email: "nobody@example.com", password: PASSWORD },
    });

    expect(wrongPassword.statusCode).toBe(401);
    expect(unknownUser.statusCode).toBe(401);
    expect(wrongPassword.json()).toEqual(unknownUser.json());
  });

  it("rejects requests without a bearer token", async () => {
    const response = await app.inject({ method: "GET", url: "/api/auth/me" });
    expect(response.statusCode).toBe(401);
  });
});
