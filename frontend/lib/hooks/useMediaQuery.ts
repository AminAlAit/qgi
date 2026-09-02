import { useEffect, useState } from "react";

/**
 * Shared SSR-safe media-query hook. Defaults to `false` on the server and on
 * the first client paint (so SSR always renders the desktop branch and there
 * is no hydration mismatch), then syncs to the real viewport after mount.
 *
 * The initial read is deferred via requestAnimationFrame so we never call
 * setState synchronously inside the effect body (react-hooks/set-state-in-effect
 * — the same rAF-deferral pattern the Sidebar uses). Subsequent updates come
 * from the matchMedia "change" listener.
 *
 * Replaces the matchMedia useState/useEffect block that was previously copied
 * into every responsive component. One call site each:
 *   const isMobile = useMediaQuery("(max-width: 1023px)");
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    const raf = requestAnimationFrame(() => setMatches(mq.matches));
    mq.addEventListener("change", onChange);
    return () => {
      cancelAnimationFrame(raf);
      mq.removeEventListener("change", onChange);
    };
  }, [query]);
  return matches;
}

/**
 * True only after the component has mounted on the client. Use to gate a
 * client-only layout behind a neutral skeleton so the server never emits a
 * layout that would visibly reflow on first paint (e.g. the full-screen pro
 * terminal, whose desktop grid would clip to a blank on a phone before the
 * media-query branch resolves). rAF-deferred to avoid set-state-in-effect.
 */
export function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(raf);
  }, []);
  return mounted;
}

/**
 * Combined mount + media-query in a SINGLE state, so `mounted` and `isMobile`
 * flip together in one commit. Use this (instead of separate useMounted() +
 * useMediaQuery() calls) for skeleton-gated responsive layouts: with two
 * independent effects there is a one-frame window where mounted=true but
 * isMobile=false, which would briefly render the desktop branch on a phone.
 *
 * Initial read is rAF-deferred (set-state-in-effect compliance); the skeleton
 * (mounted=false) shows until the deferred read, then the correct branch.
 */
export function useResponsiveLayout(query: string): {
  mounted: boolean;
  isMobile: boolean;
} {
  const [state, setState] = useState({ mounted: false, isMobile: false });
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setState({ mounted: true, isMobile: mq.matches });
    const raf = requestAnimationFrame(() =>
      setState({ mounted: true, isMobile: mq.matches })
    );
    mq.addEventListener("change", onChange);
    return () => {
      cancelAnimationFrame(raf);
      mq.removeEventListener("change", onChange);
    };
  }, [query]);
  return state;
}
