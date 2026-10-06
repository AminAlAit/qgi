import { SECTION_LABEL } from "../_data/reports-manifest";

type PublicationMastheadProps = {
  reportCount: number;
  countryCount: number;
};

export function PublicationMasthead({
  reportCount,
  countryCount,
}: PublicationMastheadProps) {
  return (
    <div className="mb-12">
      <div
        className="text-[10px] tracking-widest uppercase mb-3 font-data"
        style={{ color: "var(--qgi-accent)" }}
      >
        {SECTION_LABEL}
      </div>
      <h1 className="text-3xl lg:text-4xl font-semibold mb-4 leading-tight">
        {SECTION_LABEL}
      </h1>
      <p
        className="text-base lg:text-lg leading-relaxed max-w-3xl mb-8"
        style={{ color: "var(--qgi-text-muted)" }}
      >
        Every report anchors on a structural finding only QGI&apos;s pattern engine can
        produce; scoring date and method on every piece.
      </p>
      <div className="flex flex-wrap gap-6">
        <div className="flex flex-col">
          <span
            className="font-data font-bold text-2xl leading-none"
            style={{ color: "var(--qgi-accent)" }}
          >
            {reportCount}
          </span>
          <span
            className="text-[10px] tracking-widest uppercase font-data mt-1"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Reports
          </span>
        </div>
        <div
          className="self-stretch w-px"
          style={{ backgroundColor: "var(--qgi-border)" }}
          aria-hidden="true"
        />
        <div className="flex flex-col">
          <span
            className="font-data font-bold text-2xl leading-none"
            style={{ color: "var(--qgi-accent)" }}
          >
            {countryCount}
          </span>
          <span
            className="text-[10px] tracking-widest uppercase font-data mt-1"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Countries
          </span>
        </div>
      </div>
    </div>
  );
}
