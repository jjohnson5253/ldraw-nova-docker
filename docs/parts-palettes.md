# Parts palettes

A parts palette restricts the agent to exact LDraw part/color combinations, with
optional quantity limits. Upload your own collection or any externally prepared
parts list; no supplier catalog or prices are bundled with Nova.

## Upload a palette

On **New chat**, choose **Upload palette** before sending the first message.
Existing chats also offer **Upload palette** or **Replace palette** above the
message composer. Changes are allowed only while the chat is idle. An invalid
replacement leaves the previous palette active.

Choose **Use all parts** to remove a chat restriction. If the server has a default
palette, the button is **Use default parts** and restores that default instead.
Palette changes apply to future turns and publications, including edits to older
models. They do not rewrite models already published.

The upload control includes a downloadable example. CSV files must be UTF-8
(a UTF-8 BOM is accepted), at most 16 MB, and have these columns:

| Column | Required | Meaning |
| --- | --- | --- |
| `part_id` | Yes | LDraw part ID, such as `3001` or `3001.dat`. |
| `color_id` | Yes | Exact LDraw color ID, such as `4` for red. Use LDraw IDs rather than another catalog's color numbering. |
| `max_quantity` | No | Nonnegative integer limit for the entire candidate model. Blank means unlimited; `0` disallows use. |
| `name` | No | Searchable description. |
| `sku` | No | Optional inventory group. Rows sharing a group share one quantity limit and must specify the same limit. Defaults to a unique group for each part/color pair. |

```csv
part_id,color_id,name,max_quantity
3001,4,Brick 2 x 4,20
3002,0,Brick 2 x 3,10
```

IDs are normalized to lowercase and an optional `.dat` suffix is removed.
Inherited colors `16` and `24` cannot appear in the palette: the model's inherited
colors are resolved to concrete colors before checking. Conflicting duplicate
rows are rejected. Unknown columns are ignored and removed from saved snapshots.
The upload checks CSV structure; the model check resolves actual library parts.

## Local server default

Mount a CSV into the container and set an absolute path:

```yaml
environment:
  NOVA_PARTS_PALETTE: /config/my-parts.csv
```

Keep that file outside the agent's writable workspace. Unset the variable, or use
`none`, for unrestricted parts unless a chat has an uploaded palette. A malformed
or missing configured default fails rather than silently disabling restrictions.
The default is frozen into a chat snapshot before its first restricted turn;
later changes to the default do not change that chat's snapshot.

## How the restriction works

`parts_catalog.py` parses and searches generic palettes and validates quantities.
`parts_inventory.py` uses the existing toolkit to expand MPD submodels into
physical occurrences, resolving inherited colors and repeated instances.
`parts_policy.py` manages per-chat snapshots and model validation. The parent
toolkit needs no modifications.

The shared agent prompt requires palette use. `list_allowed_parts` offers
paginated search, and `check_model_parts` lets the agent check a candidate before
publication. A convenient `output/allowed-parts.csv` is restored before each turn;
the authoritative CSV is stored separately under `/config/parts-catalogs` with
owner-only permissions. Editing the workspace copy cannot alter the policy.
This protection relies on Nova's existing unprivileged agent sandbox; deployments
that run agent code as the server's own user cannot provide that isolation.

`publish_model` checks the captured model bytes before running the existing
validation/rendering and before storing a published model. Unavailable pairs,
excess quantities, unresolved dependencies, custom colors, inline geometry,
scaled/sheared/mirrored placements and
embedded DAT overrides block publication. Expansion runs with the toolkit's
interpreter as the unprivileged agent account, with a timeout and model/part limits.
Palette validation does not prove a model is physically buildable; the existing
geometry, visual review and BOM checks still apply.

API clients can pass `parts_palette_csv` when creating a chat, validate CSV with
`POST /api/parts-palette/validate`, and read, replace or remove a chat palette with
`GET`, `PUT` (`{"csv": "..."}`), or `DELETE`
`/api/chats/{chat_id}/parts-palette`. Palette mutation retains the app's existing
same-origin protection and rejects changes during a running turn with HTTP 409.
