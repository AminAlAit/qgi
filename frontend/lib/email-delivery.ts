/**
 * email-delivery — thin wrapper over the Resend REST API used by the public
 * /api/newsletter and /api/contact route handlers.
 *
 * No SDK dependency: we POST to https://api.resend.com/emails with `fetch`,
 * so the bundle stays lean and there is nothing to keep in lockstep with a
 * package version.
 *
 * Configuration (all via env — set in Vercel project settings):
 *   RESEND_API_KEY   required to actually deliver. Absent ⇒ deliver() returns
 *                    { ok:false, configured:false } and the caller surfaces a
 *                    graceful failure (we never fake a success).
 *   EMAIL_FROM       sender, must be a Resend-verified domain address.
 *                    Default "QG Intelligence <noreply@send.qgintelligence.com>".
 *   EMAIL_TO         destination inbox. Default the ops inbox
 *                    "qgintelligence@gmail.com".
 */

const RESEND_ENDPOINT = "https://api.resend.com/emails";

export interface DeliverInput {
  subject: string;
  text: string;
  /** Optional reply-to (e.g. the sender's address on a contact form). */
  replyTo?: string;
  /** Optional explicit recipient; overrides EMAIL_TO and the default inbox. */
  to?: string;
}

export interface DeliverResult {
  ok: boolean;
  /** false when RESEND_API_KEY is not set — lets the caller return a clear 503. */
  configured: boolean;
}

/**
 * Persist a newsletter sign-up as a contact in the Resend Audience. This is
 * the real "save the email" path: contacts live in the account-level audience,
 * exportable and mailable later. Requires only RESEND_API_KEY — Resend's
 * current API (POST /contacts) is single-audience, so there is no audience id
 * to configure (the old audiences/{id}/contacts endpoint does not exist on
 * new accounts; verified against the dashboard + docs 2026-06-05). Returns
 * { ok:false, configured:false } when the key is absent, so the caller can
 * fall back to a notification email rather than silently dropping the address.
 */
export async function addNewsletterContact(email: string): Promise<DeliverResult> {
  const key = process.env.RESEND_API_KEY;
  if (!key) return { ok: false, configured: false };

  try {
    const res = await fetch("https://api.resend.com/contacts", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, unsubscribed: false }),
    });
    // 200/201 = created; 409 = already a contact, which we treat as success.
    if (res.ok || res.status === 409) return { ok: true, configured: true };
    const body = await res.text().catch(() => "");
    console.error(
      "[email-delivery] Resend audience add failed",
      res.status,
      body.slice(0, 300)
    );
    return { ok: false, configured: true };
  } catch (err) {
    console.error("[email-delivery] audience request failed:", err);
    return { ok: false, configured: true };
  }
}

export async function deliverEmail({
  subject,
  text,
  replyTo,
  to,
}: DeliverInput): Promise<DeliverResult> {
  const key = process.env.RESEND_API_KEY;
  if (!key) return { ok: false, configured: false };

  // Must be on the Resend-verified sending domain (send.qgintelligence.com).
  const from =
    process.env.EMAIL_FROM || "QG Intelligence <noreply@send.qgintelligence.com>";
  const recipient = to || process.env.EMAIL_TO || "qgintelligence@gmail.com";

  try {
    const res = await fetch(RESEND_ENDPOINT, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from,
        to: [recipient],
        subject,
        text,
        ...(replyTo ? { reply_to: replyTo } : {}),
      }),
    });
    if (!res.ok) {
      // Don't surface the provider body to the client; log server-side only.
      const body = await res.text().catch(() => "");
      console.error("[email-delivery] Resend responded", res.status, body.slice(0, 300));
      return { ok: false, configured: true };
    }
    return { ok: true, configured: true };
  } catch (err) {
    console.error("[email-delivery] request failed:", err);
    return { ok: false, configured: true };
  }
}
