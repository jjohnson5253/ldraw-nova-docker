// Honor an existing PostHog installation without introducing a new tracking
// destination or sending conversation contents to analytics.
export function captureVerifyBuild(hasPreview: boolean) {
  const host = window as Window & { posthog?: { capture: (event: string, properties: Record<string, unknown>) => void } };
  try { host.posthog?.capture("nova_verify_build_clicked", { has_preview: hasPreview }); }
  catch { /* Analytics must not block a build. */ }
}
