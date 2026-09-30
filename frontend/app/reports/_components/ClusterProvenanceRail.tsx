type ClusterProvenanceRailProps = {
  clusters: string[];
};

export function ClusterProvenanceRail({ clusters }: ClusterProvenanceRailProps) {
  if (clusters.length === 0) return null;

  return (
    <section
      aria-labelledby="cluster-rail-label"
      className="mb-10 pb-10"
      style={{ borderBottom: "1px solid var(--qgi-border)" }}
    >
      <div className="flex items-center gap-3 mb-5">
        <h2
          id="cluster-rail-label"
          className="text-[11px] tracking-[0.25em] uppercase font-data font-semibold"
          style={{ color: "var(--qgi-accent)" }}
        >
          By Cluster
        </h2>
        <span
          className="h-px flex-1"
          style={{ backgroundColor: "var(--qgi-border)" }}
          aria-hidden="true"
        />
      </div>
      <div className="flex flex-wrap gap-2">
        {clusters.map((cluster) => (
          <span
            key={cluster}
            className="text-[11px] tracking-wider uppercase font-data px-3 py-1.5 rounded"
            style={{
              backgroundColor: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            {cluster}
          </span>
        ))}
      </div>
    </section>
  );
}
