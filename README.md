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

See [Parts palettes](docs/parts-palettes.md) to upload an allowed-parts CSV or
configure a local default palette for the agent.

## Development

COMING SOON

## Acknowledgements

COMING SOON


## Choose an allowed-parts palette

On New chat or in an idle chat, upload a CSV parts palette and select
**Only use this parts palette**. The agent must honor exact LDraw part/color pairs
and any quantity limits; publication rejects models outside the selected palette.
Uncheck the option to use all library parts while retaining the uploaded palette.
See [parts palettes](docs/parts-palettes.md) for the format, API and server defaults,
and [the on/off example](examples/parts-palette/README.md) for the generated palette,
models, inventory audit and screenshots.

Build with the paired `ldraw-nova` **codex/selectable-parts-palette** branch until
both companion PRs are included in a matching release.
