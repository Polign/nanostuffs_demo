// Forwards the message to the agent with the signed-in user's id.
import { agent, signedInUser } from "@/lib/agent";

export async function POST(request: Request) {
  const userId = await signedInUser();
  if (!userId) return Response.json({ error: "not signed in" }, { status: 401 });
  const { message, memory = true } = (await request.json().catch(() => ({}))) as { message?: string; memory?: boolean };
  if (!message?.trim()) return Response.json({ error: "message is required" }, { status: 400 });
  return agent("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, message: message.trim(), memory }),
  });
}
