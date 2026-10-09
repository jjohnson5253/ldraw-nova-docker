// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import BuildVerification from "../src/components/BuildVerification";
import { captureVerifyBuild } from "../src/analytics";
import { api, type ChatModel } from "../src/api";
import { previewEffort } from "../src/modelChoices";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const model = { model_url: "/files/generated/car.mpd", validation_status: "preview" } as ChatModel;

test("verification needs a preview and explains additional credit use", () => {
  render(<BuildVerification disabled={false} onVerify={vi.fn()} />);
  expect((screen.getByRole("button", { name: "Verify Build" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText(/more AI credits/)).toBeTruthy();
});

test("ready previews can be verified once; running builds disable the control", () => {
  const verify = vi.fn();
  const { rerender } = render(<BuildVerification model={model} disabled={false} onVerify={verify} />);
  fireEvent.click(screen.getByRole("button", { name: "Verify Build" }));
  expect(verify).toHaveBeenCalledTimes(1);
  rerender(<BuildVerification model={model} disabled onVerify={verify} />);
  fireEvent.click(screen.getByRole("button", { name: "Verify Build" }));
  expect(verify).toHaveBeenCalledTimes(1);
});

test("geometry evidence is labelled without claiming full physical validity", () => {
  render(<BuildVerification model={{ ...model, validation_status: "passed" }} disabled={false} onVerify={vi.fn()} />);
  expect(screen.getByText(/Geometry checks passed/)).toBeTruthy();
});

test("verification calls its explicit endpoint with selected model", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ started: true }), {
    headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetch);
  await api.verifyBuild("chat-id", "selected-model");
  expect(fetch.mock.calls[0][0]).toBe("/api/chats/chat-id/verify");
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ llm_model_id: "selected-model" });
});

test("verification analytics sends no prompt and cannot interrupt the build", () => {
  const capture = vi.fn();
  vi.stubGlobal("window", { posthog: { capture } });
  captureVerifyBuild(true);
  expect(capture).toHaveBeenCalledWith("nova_verify_build_clicked", { has_preview: true });
  capture.mockImplementation(() => { throw new Error("analytics unavailable"); });
  expect(() => captureVerifyBuild(true)).not.toThrow();
});

test("preview effort prefers low reasoning while supporting models without effort settings", () => {
  expect(previewEffort({ efforts: ["low", "medium", "high"], default_effort: "high" })).toBe("low");
  expect(previewEffort({ efforts: [], default_effort: null })).toBe(null);
});
