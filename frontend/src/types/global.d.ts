export {};

declare global {
  /** App version, injected at build time from package.json via Vite `define`. */
  const __APP_VERSION__: string;

  interface Window {
    VANTA?: {
      FOG?: (options: Record<string, unknown>) => { destroy: () => void };
    };
    THREE?: unknown;
  }
}
