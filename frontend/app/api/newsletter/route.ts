import { NextResponse } from "next/server";
import { z } from "zod";
import { addNewsletterContact, deliverEmail } from "@/lib/email-delivery";

/**
 * POST /api/newsletter
 *
 * Captures a newsletter sign-up (email only). Two things happen per sign-up:
 *  1. The address is stored as a contact in the Resend Audience (the durable
 *     list; account-level on Resend's current API, needs only RESEND_API_KEY).
 *  2. A notification email goes to amin@qgintelligence.com on EVERY sign-up
 *     (founder ask, 2026-06-05), which also doubles as the fallback so an
 *     address is never silently dropped if the audience write fails.
 *
 * Returns 200 {ok:true} when either path succeeded, 422 on a bad email, 503
 * when both fail — the client surfaces a graceful retry, never a fake success.
 */
const Body = z.object({
  email: z.string().trim().email().max(254),
  // Honeypot — a hidden field real users never see. Bots that fill it are
  // silently accepted below (we return ok without saving), so keep the schema
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
    return NextResponse.json(
      { error: "Please enter a valid email address." },
      { status: 422 }
    );
  }

  // Honeypot tripped: pretend success, save nothing.
  if (parsed.data.company) return NextResponse.json({ ok: true });

  const email = parsed.data.email;

  // Persist the address as a contact in the Resend audience, AND notify the
  // founder inbox on every sign-up (founder ask, 2026-06-05). Either
  // succeeding means the sign-up is not lost.
  const saved = await addNewsletterContact(email);
  const notified = await deliverEmail({
    to: "amin@qgintelligence.com",
    subject: "New QGI newsletter sign-up",
    text: `New newsletter sign-up:\n\n${email}\n\nStored in Resend audience: ${
      saved.ok
        ? "yes"
        : saved.configured
          ? "FAILED (see Resend logs; possible key-permissions issue)"
          : "no (Resend key not configured)"
    }\n`,
  });

  if (saved.ok || notified.ok) return NextResponse.json({ ok: true });

  return NextResponse.json(
    { error: "Could not record your sign-up just now. Please try again shortly." },
    { status: 503 }
  );
}
