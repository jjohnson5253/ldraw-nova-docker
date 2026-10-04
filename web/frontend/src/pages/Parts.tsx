import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type PartsSource } from "../api";

export default function Parts() {
  const [params] = useSearchParams();
  const returnTo = params.get("return");
  const [sources, setSources] = useState<PartsSource[]>([]);
  const [configured, setConfigured] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Awaited<ReturnType<typeof api.searchSets>> | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);
  const [preview, setPreview] = useState<PartsSource | null>(null);
  const [spares, setSpares] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { api.collection().then(r => { setSources(r.sources); setConfigured(r.catalog_configured); setLoaded(true); }).catch(e => setError(e.message)); }, []);
  async function work(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function search(value: string, next = 1) {
    await work(async () => { const r = await api.searchSets(value, next); setResults(r); setSearchQuery(value); setPage(next); });
  }
  const count = (source: PartsSource) => source.parts.reduce((n, p) => n + p.quantity, 0) * source.copies;
  const available = sources.filter(s => s.available);
  const unmapped = available.reduce((n, s) => n + s.parts.filter(p => !p.part || p.colour == null).reduce((q, p) => q + p.quantity, 0) * s.copies, 0);
  const duplicate = preview && !preview.id && sources.some(s => preview.set_num ? s.set_num === preview.set_num : s.name === preview.name);
  return <div className="page parts-page">
    <header className="page-head"><div><h1>My parts</h1><p className="muted">Add sets you own or upload a parts list. Nova can use this collection when you choose “Use only my parts”.</p>
      {loaded && <p>{available.reduce((n, s) => n + count(s), 0).toLocaleString()} available pieces{unmapped > 0 && <span className="warn-text"> · {unmapped.toLocaleString()} unmapped (excluded from matching)</span>}</p>}
    </div></header>
    {returnTo && /^\/(?:models|chat\/[A-Za-z0-9_-]+)(?:#model-[A-Za-z0-9]+)?$/.test(returnTo) && <p><Link to={returnTo}>Return to your model</Link> after adding parts, then choose “Use only my parts”.</p>}
    {error && <div className="banner error" role="alert">{error}</div>}
    <section className="panel" aria-label="Import parts">
      <h2>Add a set</h2>
      {!configured && <p className="muted">Set search needs a Rebrickable API key. <Link to="/settings?environment=REBRICKABLE_API_KEY#environment-heading">Set up Rebrickable</Link> to enter your key. CSV with LDraw IDs works without a key.</p>}
      <form className="head-actions" onSubmit={e => { e.preventDefault(); void search(query); }}>
        <input aria-label="Set name, number, or URL" placeholder="Set name, number, or LEGO / BrickLink / Rebrickable URL" value={query} onChange={e => setQuery(e.target.value)} />
        <button disabled={busy || !query.trim() || !configured}>Search sets</button>
      </form>
      <label className="parts-option"><input type="checkbox" checked={spares} onChange={e => setSpares(e.target.checked)} disabled={busy} /> Include spare pieces when importing sets</label>
      {results && <div className="parts-search-results">
        {results.sets.length === 0 && <p className="muted">No sets found.</p>}
        {results.sets.map(s => <div className="parts-source-head" key={s.set_num}><span><strong>{s.name}</strong><span className="muted small"> · {s.set_num} · {s.year} · {s.num_parts} pieces</span></span>
          <button disabled={busy} onClick={() => void work(async () => setPreview(await api.previewParts({ set: s.set_num, include_spares: spares })))}>Review parts</button></div>)}
        <div className="head-actions">{page > 1 && <button disabled={busy} onClick={() => void search(searchQuery, page - 1)}>Previous</button>}
          {results.next && <button disabled={busy} onClick={() => void search(searchQuery, page + 1)}>Next</button>}</div>
      </div>}
      <h2>Upload a parts list</h2>
      <p className="muted small">CSV headers: <code>part,colour,quantity</code> using LDraw IDs, or <code>part_num,color_id,quantity</code> from Rebrickable (requires your API key).</p>
      <input type="file" accept=".csv,text/csv" aria-label="Parts CSV" disabled={busy} onChange={e => {
        const file = e.target.files?.[0]; e.target.value = "";
        if (file) void work(async () => { if (file.size > 5 * 1024 * 1024) throw new Error("Choose a CSV smaller than 5 MB"); setPreview(await api.previewParts({ csv: await file.text(), name: file.name, include_spares: spares })); });
      }} />
      {busy && <p role="status"><span className="spinner" aria-hidden /> Loading parts…</p>}
    </section>
    {preview && <section className="panel" aria-label="Review imported parts">
      <h2>{preview.id ? "Edit source" : "Review import"}</h2>
      {duplicate && <p className="warn-text">You already added this source. Adding it again counts its pieces again; you can edit the existing source’s copies instead.</p>}
      <div className="parts-source-head">
        <label>Name <input value={preview.name} onChange={e => setPreview({ ...preview, name: e.target.value })} disabled={busy} /></label>
        <label>Copies <input aria-label="Copies" type="number" min="1" max="1000" value={preview.copies} disabled={busy} onChange={e => setPreview({ ...preview, copies: Number(e.target.value) })} /></label>
        <label className="parts-option"><input type="checkbox" checked={preview.available} disabled={busy} onChange={e => setPreview({ ...preview, available: e.target.checked })} /> Available to build</label>
      </div>
      <p className="muted small">Quantities below are per copy. Correct missing pieces before saving. Unmapped pieces stay in your collection but cannot count as owned matches.</p>
      <div className="parts-table"><table><thead><tr><th>Part</th><th>Color</th><th>Quantity per copy</th></tr></thead><tbody>
        {preview.parts.map((p, i) => <tr key={i}><td>{p.part ?? p.provider_part ?? "Unknown"}{p.description && <span className="muted small"> · {p.description}</span>}{!p.part && <span className="warn-text"> · unmapped</span>}</td>
          <td>{p.colour ?? `Unmapped (${p.provider_color ?? "unknown"})`}</td><td><input aria-label={`Quantity for ${p.part ?? p.provider_part ?? "unmapped part"}, color ${p.colour ?? p.provider_color ?? "unknown"}, row ${i + 1}`} type="number" min="0" max="100000" value={p.quantity} disabled={busy}
            onChange={e => setPreview({ ...preview, parts: preview.parts.map((row, index) => index === i ? { ...row, quantity: Number(e.target.value) } : row) })} /></td></tr>)}
      </tbody></table></div>
      <div className="head-actions"><button className="primary" disabled={busy} onClick={() => void work(async () => { const r = await api.saveParts(preview); setSources(r.sources); setPreview(null); })}>{preview.id ? "Save changes" : "Add these parts"}</button>
        <button disabled={busy} onClick={() => setPreview(null)}>Cancel</button></div>
    </section>}
    <h2>Your sources</h2>
    {loaded && !sources.length && <p className="muted">No parts added yet.</p>}
    {sources.map(s => <section className="panel parts-source-head" key={s.id}>
      <div><strong>{s.name}</strong><p className="muted small">{s.copies} {s.copies === 1 ? "copy" : "copies"} · {count(s).toLocaleString()} pieces · {s.available ? "Available" : "Excluded from builds"}</p></div>
      <div className="head-actions"><button disabled={busy} onClick={() => setPreview(structuredClone(s))}>Edit</button>
        <button disabled={busy} onClick={() => void work(async () => setSources((await api.removeParts(s.id!)).sources))}>Remove</button></div>
    </section>)}
  </div>;
}
