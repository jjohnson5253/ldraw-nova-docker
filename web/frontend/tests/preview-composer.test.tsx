// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Composer from "../src/components/Composer";
import { AppContext, type AppState } from "../src/context";

afterEach(cleanup);
const app = {
  chats: [],
  llms: [{ id: "model", model_name: "Test model", litellm_params: { model: "openai/gpt-6-luna" },
    profile: { efforts: ["low", "medium", "high"], default_effort: "high", context_window: 1000, context_budgets: [1000] } }],
} as AppState;

test.each(["verify", undefined] as const)("an edit after reloading %s sends an unchecked preview with normal default effort", async build_mode => {
  const send = vi.fn();
  render(<MemoryRouter><AppContext.Provider value={app}><Composer llmId="model" onLlmChange={vi.fn()}
    running={false} onSend={send} initialText="Make it red"
    initialOptions={{ mode: "agent", permissions: "full", build_mode, effort: "high" }} />
  </AppContext.Provider></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  expect(send.mock.calls[0][0]).toBe("Make it red");
  expect(send.mock.calls[0][1]).toMatchObject({ build_mode: "preview", effort: "high", permissions: "full" });
});
