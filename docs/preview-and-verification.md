# Quick previews and Verify Build

Agent prompts now create unchecked previews. The initial request and each edit use
the same short workflow: generate a self-contained model and publish an interactive
3D card. Publication preserves the source bytes without synchronous geometry
validation or rendering. The gallery can generate a thumbnail/BOM in the background;
the 3D viewer is available immediately. Preview turns use a compact prompt and a
24-step safety limit instead of the normal 150-step limit and low reasoning effort
by default where supported. The API agent finishes immediately on successful
publication; Claude is interrupted after publication and subsequent tool execution
in that turn is denied.

Inspect the preview or ask for changes. When satisfied, click **Verify Build** below
the conversation. The button explains that the full review uses more AI credits,
and is disabled until a model exists or while a turn is active. Verification
continues the same conversation and workspace, starts from the latest published
revision, and restores the complete toolkit workflow and normal model effort:
geometry/connections, construction steps, renders and visual review, BOM comparison,
and repairs. Permission settings still apply, cancellation and live progress use
the existing turn controls. Later prompts return to previews, including after a
page reload. Full review remains subject to the existing step limit; failed or
interrupted checks must be continued and never count as physical buildability proof.

Model cards distinguish unchecked previews, passed geometry validation, and failed
validation. Passing publication geometry validation does not prove physical
buildability or that all of the agent's review tasks are complete. Legacy cards
have no new status assigned.

For sessions with a parts palette, previews still select from the protected allowed
part/color list, but defer the complete availability and quantity scan to verification.
Unchecked previews can contain palette mistakes; checked publication continues to
reject unavailable pairs or quantities. The protected inventory is preserved across
both workflows and cannot be changed through an agent-written reference CSV.

API clients can set `options.build_mode` to `preview` (the default) or `verify`.
`POST /api/chats/{id}/verify` with an optional `llm_model_id` starts the full review
of that chat's latest published revision. Consumers can provide `model_id` to
verify a specific saved revision and `permissions` to explicitly select tool
permissions; omitted permissions retain the chat's current setting. It rejects
models outside the selected conversation, chats without a model, deleted
models, and active turns. The endpoint preserves the conversation's permissions;
it does not silently grant full tool access. Direct internal ToolContext callers
retain checked publication by default for compatibility.

Consumers that wrap `publish_model` with their own validation policy (including
BrickBuilder staging) must explicitly integrate preview/export behavior and expose
their own Verify Build control before offering this workflow. This fork PR alone
does not bypass such a consumer's publication gate or redeploy its pinned runtime.

Run backend tests in the prepared Nova image per `web/backend/tests/conftest.py`.
Frontend checks: `cd web/frontend && npm ci && npm test && npm run build`.
