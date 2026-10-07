# Restricting Nova to a supplier or personal inventory

Nova defaults to the Brickwith catalog shipped by its companion toolkit.
`NOVA_PARTS_CATALOG=brickwith` selects that snapshot (the default).
`NOVA_PARTS_CATALOG=/absolute/path/inventory.csv` selects any compatible CSV.
`NOVA_PARTS_CATALOG=none` explicitly leaves new chats unrestricted.

The schema requires LDraw `part_id,color_id` columns; optional fields are
`name,sku,unit_price,weight_kg,max_quantity`. See the toolkit's
`docs/agent/parts-catalog.md` for pricing, refresh and validation details.
Rebuild with the matching toolkit staging revision: older toolkit revisions do
not provide `parts_catalog.py`, `catalog_inventory.py` or the supplier snapshot.

A trusted caller can replace an individual chat's catalog before a turn:

```http
PUT /api/chats/<chat-id>/parts-catalog
Content-Type: application/json

{"csv":"part_id,color_id,max_quantity\n3001,4,100\n"}
```

The normal same-origin API protections apply. Missing chats return 404, running
chats return 409, and malformed catalogs return 400. Changes apply to subsequent
turns and edits. A chat's default is frozen on its first turn, so refreshing the
server catalog never silently changes an active chat's inventory.

`ChatPartsPolicy` keeps the authoritative CSV in protected `/config/parts-catalogs`
with 0700 directory/0600 file permissions. The agent's `output/allowed-parts.csv`
is a convenient reference; editing it never changes authorization.

Both LLM adapters use the shared system prompt and tool schemas. The agent can
search `list_allowed_parts` and inspect candidates with `check_model_parts`.
`publish_model` validates the captured source bytes before geometry checks,
rendering or storing a model. The toolkit resolves real physical parts in a
separate unprivileged process with isolated temporary files and a timeout.
Unavailable colors, exceeded quantities, unknown dependencies and custom
geometry block publication. Geometry/buildability review remains necessary.
Priced catalogs also provide a Decimal USD parts subtotal and actual weight.
Pure allowlists provide validation with a null price; prices are never guessed.

## Railway and BrickBuilder

A Git branch named staging does not create a Railway environment. Connect the
service in an existing staging environment to its source branch, or deploy a
consumer image that pins these source commits. Private networking is isolated
per project/environment; BrickBuilder's staging API and Nova must share that
boundary and their existing integration token.

BrickBuilder's Nova integration imports this service's policy instance rather
than installing its own enforcement hooks. Its Docker build fetches immutable
revisions of both Nova forks. Merge updated consumer pins into BrickBuilder's
staging branch to deploy these revisions through its existing Railway service.
Nova fork merges alone do not change those consumer pins.
