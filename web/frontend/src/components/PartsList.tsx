import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, type InventoryReport, type ModelFile } from "../api";
import { useApp } from "../context";

export default function PartsList({ model, onUseParts, running }: { model: ModelFile; onUseParts?: (prefer: boolean) => Promise<void>; running?: boolean }) {
  const [report, setReport] = useState<InventoryReport | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [prefer, setPrefer] = useState(false);
  const [version, setVersion] = useState(0);
  const navigate = useNavigate();
  const location = useLocation();
  const { refreshChats } = useApp();
  useEffect(() => {
    let alive = true;
    setReport(null); setError("");
    if (model.model_url) api.compareParts(model.model_url).then(r => { if (alive) setReport(r); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [model.model_url, model.mtime, version]);
  async function revise() {
    if (report && !report.has_available_parts) {
      navigate(`/parts?return=${encodeURIComponent(location.pathname + location.hash)}`);
      return;
    }
    setBusy(true); setError("");
    try {
      if (onUseParts) await onUseParts(prefer);
      else { const result = await api.useParts(model.model_url!, prefer); refreshChats(); navigate(`/chat/${result.chat_id}`); }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="model-parts">
    {report ? <>
      {report.has_collection ? <p><strong>You own {report.owned.toLocaleString()} of {report.required.toLocaleString()} pieces</strong> · {report.missing.toLocaleString()} missing
        {!!report.unresolved && <span className="warn-text"> · {report.unresolved} unresolved</span>}</p>
        : <p>Add your parts to see what you already have.</p>}
      {report.matches && <p className="muted small">Every required part and color fits your available quantities.</p>}
      {!!report.unmapped_inventory && <p className="warn-text small">{report.unmapped_inventory} pieces in your collection have no exact LDraw mapping and cannot count as matches.</p>}
      <details><summary>Owned and missing parts</summary><div className="parts-table"><table><thead><tr><th>Part</th><th>Color</th><th>Need</th><th>Owned</th><th>Missing</th></tr></thead><tbody>
        {report.rows.map((r, i) => <tr key={i}><td title={r.description}>{r.part}</td><td>{r.colour_name ?? r.colour}</td><td>{r.required}</td><td>{r.owned}</td><td>{r.unresolved ? "Unresolved" : r.missing}</td></tr>)}
      </tbody></table></div></details>
    </> : !error && <p className="muted small">Checking your owned parts…</p>}
    {error && <p className="warn-text small" role="alert">{error}</p>}
    <div className="head-actions"><Link to="/parts">My parts</Link><button disabled={busy} onClick={() => setVersion(v => v + 1)}>Refresh counts</button>
      <select aria-label="Rebuild parts usage" value={prefer ? "prefer" : "only"} disabled={busy || running}
        onChange={e => setPrefer(e.target.value === "prefer")}><option value="only">Use only my parts</option><option value="prefer">Use as many of my parts as possible</option></select>
      <button disabled={busy || running || !report} onClick={() => void revise()}>{busy ? "Starting…" : "Rebuild with my parts"}</button></div>
  </div>;
}
