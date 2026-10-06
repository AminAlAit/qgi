import "@testing-library/jest-dom";

// jsdom does not implement window.matchMedia, but components with responsive
// effects call it on mount (e.g. Sidebar's <=900px auto-collapse, Sidebar.tsx).
// Polyfill a non-matching stub so those components render in tests.
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}
