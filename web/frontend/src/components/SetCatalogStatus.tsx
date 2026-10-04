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
    if (!status) return;
    const pending: Status = { ...status, ready: false, state: "syncing", stage: "Starting catalog download", indexed: 0, error: undefined };
    setStatus(pending); onChange?.(pending);
    try { const s = await api.setCatalog(true); setStatus(s); onChange?.(s); setError(""); }
    catch (e) { setStatus(status); onChange?.(status); setError((e as Error).message); }
  }
  if (!status) return error ? <p className="warn-text" role="alert">{error}</p> : null;
  return <div className="small">
    <p className="muted" role="status">{status.state === "syncing" ? <><span className="spinner" aria-hidden /> {status.stage}…{status.indexed ? ` ${status.indexed.toLocaleString()} sets indexed.` : ""} Search is available when indexing finishes.</>
      : status.ready ? `${status.total_sets?.toLocaleString()} sets indexed locally · Updated ${new Date(status.updated_at!).toLocaleDateString()}. Search uses this downloaded catalog.`
      : "Saving your Rebrickable key downloads the complete set catalog for local search."}</p>
    {status.state === "inventory_syncing" ? <p className="muted" role="status"><span className="spinner" aria-hidden /> {status.stage}…{status.indexed ? ` ${status.indexed.toLocaleString()} rows indexed.` : ""} Set search is available while parts index in the background.</p>
      : status.inventory_ready && <p className="muted">{status.total_parts?.toLocaleString()} part types · {status.total_inventory_rows?.toLocaleString()} inventory entries indexed locally.</p>}
    {(error || status.error) && <p className="warn-text" role="alert">{error || status.error}</p>}
    {status.configured && <button type="button" disabled={status.state === "syncing" || status.state === "inventory_syncing"} onClick={() => void refresh()}>{status.state === "error" ? "Retry catalog download" : "Refresh catalog"}</button>}
  </div>;
}
