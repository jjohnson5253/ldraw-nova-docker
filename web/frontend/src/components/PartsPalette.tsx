import { useEffect, useRef, useState } from 'react';
import { api, type PartsPaletteInfo } from '../api';

export default function PartsPalette({ chatId, running = false, onChange, onBusy }: {
  chatId?: string; running?: boolean;
  onChange?: (csv: string | null) => void;
  onBusy: (busy: boolean) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [info, setInfo] = useState<PartsPaletteInfo | null>(null);
  const [filename, setFilename] = useState('');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    onBusy(true);
    api.partsPalette(chatId).then(value => { if (active) setInfo(value); })
      .catch(e => { if (active) setError((e as Error).message); })
      .finally(() => { if (active) { setBusy(false); onBusy(false); } });
    return () => { active = false; };
  }, [chatId, onBusy]);

  async function upload(file: File) {
    setError('');
    if (!file.name.toLowerCase().endsWith('.csv') || file.size > 16 * 1024 * 1024) {
      setError('Choose a CSV parts palette no larger than 16 MB.'); return;
    }
    setBusy(true); onBusy(true);
    try {
      const csv = await file.text();
      const updated = chatId ? await api.savePalette(chatId, csv) : await api.validatePalette(csv);
      setInfo(updated); setFilename(file.name); onChange?.(csv);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); onBusy(false); }
  }
  async function clear() {
    setError(''); setBusy(true); onBusy(true);
    try {
      setInfo(chatId ? await api.clearPalette(chatId) : await api.partsPalette());
      setFilename(''); onChange?.(null);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); onBusy(false); }
  }
  const restricted = info?.allowed_combinations != null;
  return <section className="parts-palette" aria-label="Parts palette">
    <div className="palette-row">
      <div className="palette-status" role="status" aria-live="polite">
        <strong>Parts palette</strong>
        <span className="muted">{busy ? 'Checking palette…' : restricted
          ? `${info.allowed_combinations!.toLocaleString()} allowed part/color pairs${filename ? ` · ${filename}` : ''}`
          : info ? 'All library parts available' : 'Unable to load palette settings'}</span>
      </div>
      <div className="palette-actions">
        <input ref={input} type="file" accept=".csv,text/csv" hidden disabled={busy || running}
          aria-label="Upload parts palette CSV" onChange={e => {
            const file = e.target.files?.[0]; e.target.value = ''; if (file) void upload(file);
          }} />
        <button type="button" disabled={busy || running} onClick={() => input.current?.click()}>
          {restricted ? 'Replace palette' : 'Upload palette'}</button>
        {restricted && <button type="button" disabled={busy || running} onClick={() => void clear()}>
          {info.default_available ? 'Use default parts' : 'Use all parts'}</button>}
      </div>
    </div>
    <small className="muted">Upload a CSV with LDraw part IDs and color IDs, plus optional quantity limits.{' '}
      <a href="/api/parts-palette/example" download>Download an example</a>.</small>
    {error && <div className="banner error" role="alert">{error}</div>}
  </section>;
}
