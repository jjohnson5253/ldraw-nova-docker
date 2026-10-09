"""Run inside the built image; check gateway startup and its authorization contract."""

import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


def get_runtime(headers):
    request = urllib.request.Request("http://127.0.0.1:8000/integration/runtime", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def main():
    process = subprocess.Popen([
        "uvicorn", "brickbuilder_integration.gateway:app", "--app-dir", "/app/web/backend",
        "--host", "127.0.0.1", "--port", "8000",
    ])
    try:
        deadline = time.monotonic() + 60
        while True:
            if process.poll() is not None:
                raise RuntimeError("Gateway exited before becoming ready")
            try:
                status, _ = get_runtime({})
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Gateway did not become ready")
                time.sleep(0.5)
        assert status == 401, "Gateway must reject missing credentials"
        authorization = {"Authorization": "Bearer " + os.environ["NOVA_SERVICE_TOKEN"]}
        assert get_runtime(authorization)[0] == 400, "Gateway must require a valid tenant"
        authorization["X-Nova-Tenant"] = "0" * 64
        status, versions = get_runtime(authorization)
        assert status == 200, "Authenticated runtime discovery must work"
        assert versions["web"] == os.environ["EXPECTED_WEB_REVISION"]
        expected = json.loads(Path("/app/web/backend/brickbuilder_integration/versions.json").read_text())
        assert versions["toolkit"] == expected["toolkit"]
        assert versions["parts_catalog_version"] == 1
        assert versions["generation_usage_version"] == 1
        assert Path("/opt/ldraw-nova/ldraw_tools/parts_policy.py").is_file()
        print("Runtime startup, metadata, parts support, and gateway authorization passed.")
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
