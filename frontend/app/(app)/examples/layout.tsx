import type { Metadata } from "next";

/**
 * /examples/* is a prototype area that contains hardcoded sample data and
 * stale version stamps. Block search-engine indexing so Google doesn't
 * surface V1.8.1-era prototype content when searching for QGI pages.
 *
 * Disposition of each page under this layout (keep / move out of app/ /
 * delete) is tracked on the #425-series QA follow-up tickets.
 */
export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

export default function ExamplesLayout({ children }: { children: React.ReactNode }) {
  return children;
}
