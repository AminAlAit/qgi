import { NextResponse } from "next/server";
import { z } from "zod";
import { deliverEmail } from "@/lib/email-delivery";

/**
 * POST /api/contact
 *
 * Sends a contact-form message to the ops inbox via Resend, with the sender's
 * address as reply-to so a reply lands straight back to them. No database.
 *
 * Returns 200 {ok:true} on delivery, 422 on validation failure, 503 when
 * delivery is not configured or fails.
 */
const Body = z.object({
  name: z.string().trim().min(1, "Please enter your name.").max(120),
  email: z.string().trim().email("Please enter a valid email address.").max(254),
  message: z.string().trim().min(10, "Please add a little more detail.").max(5000),
  // Honeypot — a hidden field real users never see. Bots that fill it are
  // silently accepted below (we return ok without sending), so keep the schema
  // permissive and handle it in code rather than rejecting with a raw zod error.
  company: z.string().optional(),
});

export async function POST(req: Request) {
  let json: unknown;
  try {
    json = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 422 });
  }

  const parsed = Body.safeParse(json);
  if (!parsed.success) {
    const first =
      parsed.error.issues[0]?.message ?? "Please check the form and try again.";
    return NextResponse.json({ error: first }, { status: 422 });
  }

  if (parsed.data.company) return NextResponse.json({ ok: true });

  const { name, email, message } = parsed.data;
  const result = await deliverEmail({
    to: "amin@qgintelligence.com",
    subject: `QGI contact form — ${name}`,
    replyTo: email,
    text: `Name: ${name}\nEmail: ${email}\n\n${message}\n`,
  });

  if (!result.ok) {
    return NextResponse.json(
      { error: "Could not send your message just now. Please try again shortly." },
      { status: 503 }
    );
  }
  return NextResponse.json({ ok: true });
}
