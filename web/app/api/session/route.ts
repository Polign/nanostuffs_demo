// Sign in for the demo: a name in a cookie stands in for the real session.
// In the Nanostuffs app the user id comes from their existing auth; the
// point is only that the route handlers read it server-side.
import { cookies } from "next/headers";
import { SESSION_COOKIE, signedInUser } from "@/lib/agent";

export async function GET() {
  return Response.json({ userId: await signedInUser() });
}

export async function POST(request: Request) {
  const { userId } = (await request.json().catch(() => ({}))) as { userId?: string };
  const id = (userId ?? "").trim().toLowerCase();
  if (!/^[a-z0-9_-]{1,32}$/.test(id)) {
    return Response.json({ error: "userId must be 1 to 32 letters, digits, - or _" }, { status: 400 });
  }
  const store = await cookies();
  store.set(SESSION_COOKIE, id, { httpOnly: true, sameSite: "lax", path: "/" });
  return Response.json({ userId: id });
}

export async function DELETE() {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
  return Response.json({ userId: null });
}
