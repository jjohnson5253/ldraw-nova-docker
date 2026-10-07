# Restricting Nova with an external local palette

Nova contains a generic palette reader and validation tools. It ships no
supplier catalog or prices, and makes no supplier network requests. The calling
application owns supplier catalogs and cost estimates. Without a configured
palette, Nova retains its normal unrestricted behavior.

To restrict new chats to a local CSV, mount a file outside the agent's writable
workspace and set:

```sh
NOVA_PARTS_PALETTE=/config/palettes/allowed-parts.csv
```

`NOVA_PARTS_PALETTE=none` explicitly disables the default palette for new chats.
The older `NOVA_PARTS_CATALOG` variable remains an alias for absolute CSV paths;
there are no built-in supplier presets. Changes do not disable palettes already
configured on existing chats. Those chats retain their protected snapshots.

The schema requires LDraw `part_id,color_id` columns. Optional fields are
`name,sku,max_quantity`; a shared inventory group in `sku` aggregates quantities
across aliases. Additional fields are ignored and stripped before storing the
palette. Pricing and weights are not used or exposed by Nova.

A trusted caller can supply a palette for an individual chat before a turn:

```http
PUT /api/chats/<chat-id>/parts-catalog
Content-Type: application/json

{"csv":"part_id,color_id,max_quantity\n3001,4,100\n"}
```

The normal same-origin API protections apply. Missing chats return 404, running
chats return 409, and malformed palettes return 400. Restrictions apply to
subsequent turns and edits. A chat's default palette is frozen on its first turn.
Refreshing the external local file does not change existing chat snapshots.

`ChatPartsPolicy` keeps an authoritative palette in protected
`/config/parts-catalogs` with 0700 directory/0600 file permissions. The agent's
`output/allowed-parts.csv` is a reference; modifying it cannot change authority.

Both agent adapters use shared system guidance, `list_allowed_parts` and
`check_model_parts`. Publication validates the captured source bytes before
geometry checks, rendering or storing a model. The toolkit resolves physical
parts in an unprivileged process with isolated files and a timeout. Unavailable
colors, exceeded quantities, unknown dependencies and custom geometry block
publication. Geometry and visual review remain necessary.

## BrickBuilder and staging deployment

BrickBuilder stores supplier data and prices in its own backend. Before a Nova
generation/edit it sends only an availability palette, without prices, weights
or supplier metadata, through its private integration. BrickBuilder computes
costs independently and validates the final import against its own catalog.

Railway's existing BrickBuilder staging Nova service builds from BrickBuilder's
staging branch using immutable commits of both Nova forks. Merging fork changes
alone does not update those pins; merge the updated BrickBuilder consumer PR to
rebuild the staging runtime/API. No additional Railway environment is required.
