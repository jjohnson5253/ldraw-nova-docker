import { useEffect, useState } from "react";
import { api, type SetCatalogStatus as Status } from "../api";

export default function SetCatalogStatus({ onChange }: { onChange?: (status: Status) => void }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const load = () => api.setCatalog().then(s => {
      if (active) { setStatus(s); onChange?.(s); setError(""); }
    }).catch(e => { if (active) setError(e.message); });
    void load();
    const timer = setInterval(load, 2000);
    return () => { active = false; clearInterval(timer); };
  }, [onChange]);
  async function refresh() {
    try { const s = await api.setCatalog(true); setStatus(s); onChange?.(s); setError(""); }
    catch (e) { setError((e as Error).message); }
  }
  if (!status) return error ? <p className="warn-text" role="alert">{error}</p> : null;
  return <div className="small">
    <p className="muted" role="status">{status.state === "syncing" ? <><span className="spinner" aria-hidden /> {status.stage}…{status.indexed ? ` ${status.indexed.toLocaleString()} sets indexed.` : ""}</>
      : status.ready ? `${status.total_sets?.toLocaleString()} sets indexed locally · Updated ${new Date(status.updated_at!).toLocaleDateString()}. Search uses this downloaded catalog.`
      : "Saving your Rebrickable key downloads the complete set catalog for local search."}</p>
    {(error || status.error) && <p className="warn-text" role="alert">{error || status.error}</p>}
    {status.configured && <button type="button" disabled={status.state === "syncing"} onClick={() => void refresh()}>{status.state === "error" ? "Retry catalog download" : "Refresh catalog"}</button>}
  </div>;
}
