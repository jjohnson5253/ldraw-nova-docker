// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import PartsPalette from '../src/components/PartsPalette';
import { api } from '../src/api';
import { MemoryRouter } from 'react-router-dom';
import Home from '../src/pages/Home';
import { AppContext, type AppState } from '../src/context';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const palette = { allowed_combinations: 3, enabled: true, default_available: false };

test('upload enables a validated palette and the switch retains it while disabled', async () => {
  vi.spyOn(api, 'partsPalette').mockResolvedValue({ ...palette, allowed_combinations: null, enabled: false });
  vi.spyOn(api, 'validatePalette').mockResolvedValue(palette);
  const change = vi.fn(), selection = vi.fn();
  render(<PartsPalette onChange={change} onSelection={selection} onBusy={vi.fn()} />);
  await screen.findByText('All library parts available');
  const file = { name: 'my-palette.csv', size: 50, text: async () => 'part_id,color_id\n3001,4\n' };
  fireEvent.change(screen.getByLabelText('Upload parts palette CSV'), { target: { files: [file] } });
  const checkbox = await screen.findByRole('checkbox', { name: 'Only use this parts palette' });
  expect((checkbox as HTMLInputElement).checked).toBe(true);
  expect(change).toHaveBeenLastCalledWith('part_id,color_id\n3001,4\n');
  fireEvent.click(checkbox);
  await screen.findByText(/Restriction off: generation can use all library parts/);
  expect(selection).toHaveBeenLastCalledWith(false);
  expect(change).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/my-palette.csv/)).toBeTruthy();
});

test('existing chat selection persists through the API and is locked during generation', async () => {
  vi.spyOn(api, 'partsPalette').mockResolvedValue(palette);
  const select = vi.spyOn(api, 'selectPalette').mockResolvedValue({ ...palette, enabled: false });
  const busy = vi.fn();
  const view = render(<PartsPalette chatId="chat" onBusy={busy} />);
  const checkbox = await screen.findByRole('checkbox');
  fireEvent.click(checkbox);
  await waitFor(() => expect(select).toHaveBeenCalledWith('chat', false));
  await screen.findByText(/Restriction off/);
  view.rerender(<PartsPalette chatId="chat" onBusy={busy} running />);
  expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: 'Replace palette' }) as HTMLButtonElement).disabled).toBe(true);
});

test('a failed toggle preserves the enforced selection', async () => {
  vi.spyOn(api, 'partsPalette').mockResolvedValue(palette);
  vi.spyOn(api, 'selectPalette').mockRejectedValue(new Error('Wait for generation to finish'));
  render(<PartsPalette chatId="chat" onBusy={vi.fn()} />);
  fireEvent.click(await screen.findByRole('checkbox'));
  await screen.findByRole('alert');
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
});

test('an invalid replacement preserves the saved palette and selection', async () => {
  vi.spyOn(api, 'partsPalette').mockResolvedValue(palette);
  vi.spyOn(api, 'savePalette').mockRejectedValue(new Error('Parts catalog is missing required columns'));
  render(<PartsPalette chatId="chat" onBusy={vi.fn()} />);
  await screen.findByRole('checkbox');
  fireEvent.change(screen.getByLabelText('Upload parts palette CSV'), {
    target: { files: [{ name: 'invalid.csv', size: 10, text: async () => 'wrong\n' }] },
  });
  await screen.findByRole('alert');
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
  expect(screen.getByText('Restricted to 3 part/color pairs')).toBeTruthy();
});


test.each([true, false])('new-chat generation sends the palette selection %s', async enabled => {
  vi.spyOn(api, 'partsPalette').mockResolvedValue({ ...palette, allowed_combinations: null, enabled: false });
  vi.spyOn(api, 'validatePalette').mockResolvedValue(palette);
  const create = vi.spyOn(api, 'createChat').mockResolvedValue({ id: 'chat' } as never);
  const send = vi.spyOn(api, 'send').mockResolvedValue({} as never);
  const app = { chats: [], llms: [{ id: 'model', model_name: 'Test', litellm_params: { model: 'openai/gpt-6-sol' } }],
    defaultLlmId: 'model', refreshChats: vi.fn() } as unknown as AppState;
  render(<MemoryRouter><AppContext.Provider value={app}><Home /></AppContext.Provider></MemoryRouter>);
  await screen.findByText('All library parts available');
  const csv = 'part_id,color_id\n3001,4\n';
  fireEvent.change(screen.getByLabelText('Upload parts palette CSV'), {
    target: { files: [{ name: 'palette.csv', size: 30, text: async () => csv }] },
  });
  const checkbox = await screen.findByRole('checkbox');
  if (!enabled) fireEvent.click(checkbox);
  await waitFor(() => expect((checkbox as HTMLInputElement).disabled).toBe(false));
  fireEvent.change(screen.getByRole('textbox', { name: 'Message' }), { target: { value: 'Build a tower' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  expect(create).toHaveBeenCalledWith('model', csv, enabled);
  expect(send.mock.calls[0][1]).toBe('Build a tower');
});
