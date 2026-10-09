# BrickBuilder Nova deployment

Railway's production Nova service deploys this repository's `main-BrickBuilderAI`
branch with `RAILWAY_DOCKERFILE_PATH=Railway.Dockerfile`. The existing `Dockerfile`
and Docker Compose setup continue to serve standalone Nova.

The Railway recipe builds this branch's web app and imports the toolkit from the
matching `ldraw-nova:main-BrickBuilderAI` release, using an immutable commit pin.
It also imports BrickBuilder's private gateway from a pinned BrickBuilder commit.
The gateway keeps the service compatible with the app's existing authenticated
API, tenant isolation, shared caches, and persistent storage.

Keep the existing Railway variables and `/data` volume. The service uses port 8000
and `NOVA_BIND_HOST=::` for private networking. No public domain is required.

Railway supplies `RAILWAY_GIT_COMMIT_SHA` so the runtime reports the deployed web
revision. For a local build, provide `--build-arg NOVA_WEB_REVISION=$(git rev-parse HEAD)`.

To release new toolkit or gateway code, update the commit pins in
`scripts/prepare_railway.py`, run `python3 scripts/prepare_railway.py`, validate the
image, and merge a reviewed PR into `main-BrickBuilderAI`. A toolkit-only push does
not automatically deploy this separate repository; update its pin here to deploy.

Validate the generator with `python3 -m unittest discover -s tests`.

Railway build arguments: https://docs.railway.com/builds/dockerfiles
Railway commit metadata: https://docs.railway.com/variables/reference
