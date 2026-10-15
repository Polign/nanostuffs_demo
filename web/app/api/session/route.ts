// Sign-in: the user id is kept in an httpOnly cookie and read server-side
// by the other route handlers.
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
