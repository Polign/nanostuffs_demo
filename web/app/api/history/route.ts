// What Recall holds about the signed-in person, with what each value
// replaced. DELETE drops the person's memory collection.
import { agent, signedInUser } from "@/lib/agent";

export async function GET() {
  const userId = await signedInUser();
  if (!userId) return Response.json({ error: "not signed in" }, { status: 401 });
  return agent(`/history?userId=${encodeURIComponent(userId)}`);
}

export async function DELETE() {
  const userId = await signedInUser();
  if (!userId) return Response.json({ error: "not signed in" }, { status: 401 });
  return agent("/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId }),
  });
}
