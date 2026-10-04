# ldraw-nova-docker

> [!IMPORTANT]
> **Want to try the ldraw-nova web app? Start at the [ldraw-nova repo](https://github.com/anteloc/ldraw-nova#installation).**
>
> This repo is the Docker packaging of [ldraw-nova](https://github.com/anteloc/ldraw-nova). It turns that toolset into a web app you can run. It isn't meant to be used on its own: the Docker image is built from both repos, cloned side by side at the same tag.
>
> The project's landing page, demo video and installation steps are all in **ldraw-nova**. This README will only cover the technical side of the Docker image, and it's being rewritten.
>
> 👉 **[Go to ldraw-nova and install the web app](https://github.com/anteloc/ldraw-nova#installation)**

## Overview

COMING SOON

## Build

COMING SOON

## Configuration

COMING SOON

### Owned parts

Open **My parts** to import sets or review a CSV collection. Set search and
Rebrickable CSV imports require `REBRICKABLE_API_KEY`, configured through the
existing **Settings → Environment** editor. LEGO, BrickLink and Rebrickable set
URLs are accepted as set-number inputs; Rebrickable supplies their inventories.
Search is on demand, without a full catalog mirror.

Offline CSV uses `part,colour,quantity` with LDraw IDs (optional `.dat` suffix)
and explicit LDraw color codes. Rebrickable CSV uses `part_num,color_id,quantity`;
its part and color IDs are mapped through the API. Review unmapped rows, per-copy
quantities, copies and availability before saving. Sources persist in
`data/collection.json`; overlapping imports contribute additional stock.

Generated model cards show owned/missing counts. **Use only my parts** appears
in the composer and on models generated without that option. It passes a frozen
collection snapshot to the existing agent, and publication requires both normal
validation and an exact part/color/quantity match. The original model stays
available. This requires the matching toolkit branch containing
`bom --inventory` and `LDRAW_NOVA_CACHE_DIR` support. There is no purchase flow.

## Development

COMING SOON

## Acknowledgements

COMING SOON
