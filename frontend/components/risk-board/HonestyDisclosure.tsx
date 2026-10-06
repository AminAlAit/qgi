/**
 * Disclosure panel. Surfaces the discrimination-vs-probability contract
 * directly on the page. Calm slate-blue tone per V4.1 bar.
 */
export function HonestyDisclosure() {
  return (
    <div
      data-tour="risk-board-honesty"
      style={{
        padding: "14px 16px",
        border: "1px solid #3A5A70",
        background: "rgba(91,126,153,0.08)",
        borderRadius: "6px",
        borderLeft: "3px solid #5B7E99",
        marginBottom: "24px",
      }}
    >
      <div
        style={{
          fontSize: "10px",
          letterSpacing: "1.2px",
          color: "#5B7E99",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "8px",
          textTransform: "uppercase",
        }}
      >
        How to read this board
      </div>
      <ol
        style={{
          fontSize: "13px",
          color: "var(--qgi-text)",
          lineHeight: 1.65,
          margin: 0,
          paddingLeft: "18px",
        }}
      >
        <li>
          Scores are <strong>discrimination ranks, not probabilities</strong>. A country
          at 80 is not &ldquo;80% likely&rdquo; to experience the event; it sits high in
          the distribution of countries whose recent movement shape resembles this trend.
        </li>
        <li>
          Movements over time describe <strong>rank shifts</strong>, not changes in
          forward odds.
        </li>
        <li>No row on this board makes a forward-dated claim.</li>
        {/* V4.1 §4: "Not yet tested" → "Coming soon" (audience-facing). */}
        <li>
          Trends marked &ldquo;Coming soon&rdquo; show placeholder rows; scores appear
          once their evidence base is sufficient.
        </li>
      </ol>
    </div>
  );
}
