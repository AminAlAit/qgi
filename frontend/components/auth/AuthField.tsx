"use client";

/** Shared labelled input for the auth forms (login / signup / forgot). */
export function AuthField({
  label,
  type,
  value,
  onChange,
  autoComplete,
  placeholder,
  inputMode,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  placeholder?: string;
  inputMode?: "text" | "email" | "numeric";
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
      <span style={{ fontSize: "12px", color: "var(--qgi-text-muted)" }}>{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        placeholder={placeholder}
        inputMode={inputMode}
        required
        // Keyboard focus ring matches the sidebar's convention (Sidebar.tsx):
        // never remove the outline outright — swap it for a visible ring.
        className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--qgi-surface)]"
        style={{
          padding: "10px 12px",
          fontSize: "14px",
          minHeight: "44px", // WCAG 2.5.5 target size (matches PublicNav CTA)
          color: "var(--qgi-text)",
          background: "var(--qgi-bg)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "8px",
        }}
      />
    </label>
  );
}

/** Shared primary submit button for the auth forms. */
export function AuthSubmit({
  loading,
  children,
}: {
  loading: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--qgi-surface)]"
      style={{
        padding: "11px 14px",
        minHeight: "44px", // WCAG 2.5.5 target size
        fontSize: "14px",
        fontWeight: 600,
        color: "var(--qgi-bg)",
        background: "var(--qgi-accent)",
        border: "none",
        borderRadius: "8px",
        cursor: loading ? "default" : "pointer",
        opacity: loading ? 0.6 : 1,
      }}
    >
      {children}
    </button>
  );
}

/** Shared inline error line. role="alert" so screen readers announce it. */
export function AuthError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" style={{ color: "var(--qgi-danger)", fontSize: "13px", margin: 0 }}>
      {message}
    </p>
  );
}
