// The agent (agent/server.py). Only route handlers talk to it; the user id
// always comes from the session cookie.
import { cookies } from "next/headers";

export const AGENT_URL = process.env.AGENT_URL ?? "http://127.0.0.1:8000";
export const SESSION_COOKIE = "demo_user";

export async function signedInUser(): Promise<string | null> {
  const store = await cookies();
  const id = store.get(SESSION_COOKIE)?.value?.trim().toLowerCase();
  return id && /^[a-z0-9_-]{1,32}$/.test(id) ? id : null;
}

export async function agent(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${AGENT_URL}${path}`, { ...init, cache: "no-store" });
  const body = await res.text();
  return new Response(body, { status: res.status, headers: { "Content-Type": "application/json" } });
}
