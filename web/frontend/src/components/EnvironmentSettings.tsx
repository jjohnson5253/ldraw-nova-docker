import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type EnvironmentVariable } from "../api";
import { useApp } from "../context";
import SetCatalogStatus from "./SetCatalogStatus";

type Row = { key: string; id?: string; name: string; value: string | null; has_value: boolean; fixed: boolean };
const rebrickableRow = (): Row => ({ key: "rebrickable-setup", name: "REBRICKABLE_API_KEY", value: null, has_value: false, fixed: false });
const toRows = (variables: EnvironmentVariable[]): Row[] => {
  const rows: Row[] = variables.map(v => ({ ...v, key: v.id }));
  return rows.some(row => row.name === "REBRICKABLE_API_KEY") ? rows : [...rows, rebrickableRow()];
};

function ReplacementWarning({ row }: { row: Row }) {
  const [warning, setWarning] = useState("");
  useEffect(() => {
    let active = true;
    setWarning("");
    const timer = setTimeout(() => {
      api.checkEnvironment(row.name.trim(), row.id).then(result => {
        if (active) setWarning(result.preconfigured
          ? "This name is already preconfigured. The value you save here takes precedence and replaces that value for new requests."
          : result.saved ? "This variable already has a saved row. Edit that row instead of adding it again." : "");
      }).catch(() => {});
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [row.name, row.id]);
  return warning ? <span className="environment-warning" tabIndex={0} role="img" aria-label={warning} title={warning}>
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M10 2 19 18H1Z" strokeLinejoin="round" /><path d="M10 7v5m0 2v1" strokeLinecap="round" /></svg>
    <span className="environment-tooltip" aria-hidden="true">{warning}</span>
  </span> : null;
}

export default function EnvironmentSettings() {
  const [params] = useSearchParams();
  const setupRebrickable = params.get("environment") === "REBRICKABLE_API_KEY";
  const { refreshLlms } = useApp();
  const [rows, setRows] = useState<Row[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const nextKey = useRef(0);

  useEffect(() => {
    let active = true;
    api.environment().then(result => {
      if (active) {
        setRows(toRows(result.variables)); setLoaded(true);
      }
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (loaded && setupRebrickable) document.getElementById("environment-heading")?.scrollIntoView({ block: "start" });
  }, [loaded, setupRebrickable]);

  function change(key: string, patch: Partial<Row>) {
    setRows(current => current.map(row => row.key === key ? { ...row, ...patch } : row));
    setDirty(true); setMessage(""); setError("");
  }

  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const result = await api.saveEnvironment(rows.filter(row => row.id || row.name !== "REBRICKABLE_API_KEY" || row.value !== null)
        .map(({ id, name, value }) => ({ id, name: name.trim(), value })));
      setRows(toRows(result.variables)); setDirty(false);
      refreshLlms();
      setMessage("Environment variables saved. New requests use these values.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return <section className="panel environment-settings" aria-labelledby="environment-heading">
    <div className="environment-heading">
      <h2 id="environment-heading">Environment variables</h2>
      <button type="button" disabled={!loaded || busy} onClick={() => {
        const key = `new-${nextKey.current++}`;
        setRows(current => [...current, { key, name: "", value: "", has_value: false, fixed: false }]);
        setDirty(true); setMessage(""); setError("");
      }}>Add</button>
    </div>
    <p className="muted small">Click Add, enter a variable name and value, then Save. If the variable is missing or empty, this supplies its value. If it is already preconfigured, the value saved here takes precedence.</p>
    <p className="muted small">Values are hidden for everyone. Leave a saved value untouched to keep it, or type a new value to replace it. An empty value saved here means “no value”.</p>
    <form onSubmit={save}>
      <div className="environment-rows">
        {rows.map((row, index) => row.fixed || row.name === "REBRICKABLE_API_KEY" ? <div className="required-environment" key={row.key}>
          <label className="required-environment-row"><span>{row.name}:</span>
            <span className="environment-value"><input aria-label={`${row.name} value`} aria-describedby={row.fixed ? "typesafe-hint" : "rebrickable-hint"} type="password" autoComplete="new-password" maxLength={65536} disabled={busy}
              placeholder={row.has_value ? "Value saved · type to replace" : "Enter value"} value={row.value ?? ""}
              onChange={e => change(row.key, { value: e.target.value })} />
              <ReplacementWarning row={row} />
              {!row.fixed && row.id && <button type="button" className="danger-text" disabled={busy} onClick={() => {
                setRows(current => current.map(r => r.key === row.key ? rebrickableRow() : r)); setDirty(true); setMessage(""); setError("");
              }}>Remove</button>}</span>
          </label>
          {row.fixed ? <small id="typesafe-hint" className="muted typesafe-hint"><em>This is required for finding required parts via Jev's semantic search</em></small>
            : <><small id="rebrickable-hint" className="muted typesafe-hint">Save your key to download all LEGO sets for local search. Importing a set’s parts uses the Rebrickable API.</small><SetCatalogStatus /></>}
        </div> : <div className="environment-row" key={row.key}>
          <label>
            <span>Name</span>
            <input aria-label={`Variable name ${index + 1}`} required pattern="[A-Za-z_][A-Za-z0-9_]*" maxLength={255}
              autoComplete="off" spellCheck={false} placeholder="OPENROUTER_API_KEY" disabled={busy}
              value={row.name} onChange={e => change(row.key, { name: e.target.value })} />
          </label>
          <label>
            <span>Value</span>
            <span className="environment-value"><input aria-label={`Variable value ${index + 1}`} type="password" autoComplete="new-password" spellCheck={false} maxLength={65536}
              placeholder={row.has_value ? "Value saved · type to replace" : "Enter value"} disabled={busy}
              value={row.value ?? ""}
              onChange={e => change(row.key, { value: e.target.value })} />
              <ReplacementWarning row={row} /></span>
          </label>
          <button type="button" className="danger-text" aria-label={`Remove variable ${index + 1}`} disabled={busy} onClick={() => {
            setRows(current => current.filter(r => r.key !== row.key)); setDirty(true); setMessage(""); setError("");
          }}>Remove</button>
        </div>)}
      </div>
      {!loaded && !error && <p className="muted small">Loading environment variables…</p>}
      {rows.length > 1 && <p className="muted small">Remove a variable and save to use its preconfigured value again, if there is one.</p>}
      {error && <p className="warn-text" role="alert">{error}</p>}
      {message && <p className="ok-text small" role="status">{message}</p>}
      <div className="form-actions">
        {dirty && <span className="muted small">Unsaved changes</span>}
        <button type="submit" className="primary" disabled={!loaded || !dirty || busy}>{busy ? "Saving…" : "Save environment variables"}</button>
      </div>
    </form>
  </section>;
}
