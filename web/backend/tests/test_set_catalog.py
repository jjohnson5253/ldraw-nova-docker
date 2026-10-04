import gzip
import io
import threading
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

import collection
import environment_config
import main
import set_catalog
import settings

THEMES = "id,name,parent_id\n1,Star Wars,\n2,Ultimate Collector Series,1\n"
SETS = "set_num,name,year,theme_id,num_parts,img_url\n" + "\n".join(
    f"{75000+i}-1,Millennium Falcon {i},2020,2,100,image" for i in range(25)
) + "\n99999-1,Star Wars Bag,2025,1,0,image\n"


@pytest.fixture
def index(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(set_catalog, "_worker", None)
    monkeypatch.setattr(set_catalog, "_progress", {})
    monkeypatch.setattr(set_catalog, "_stop", threading.Event())
    monkeypatch.setattr(environment_config, "snapshot", lambda: {"REBRICKABLE_API_KEY": "private-test-key"})
    requests = []
    class Opener:
        def open(self, url, **kwargs):
            requests.append(url)
            text = THEMES if url.endswith("themes.csv.gz") else SETS
            return io.BytesIO(gzip.compress(text.encode()))
    monkeypatch.setattr(set_catalog, "build_opener", lambda *args: Opener())
    # Exercise the real downloader, overriding the suite's offline safeguard.
    monkeypatch.setattr(set_catalog, "_download", REAL_DOWNLOAD)
    yield requests
    set_catalog.shutdown()


REAL_DOWNLOAD = set_catalog._download


def test_entire_catalog_is_persistent_and_search_never_uses_api(index, monkeypatch):
    set_catalog.ensure()
    set_catalog._worker.join(5)
    assert set_catalog.status()["total_sets"] == 26
    assert set_catalog.status()["state"] == "ready"
    assert len(index) == 2 and all(url.startswith("https://cdn.rebrickable.com/") for url in index)
    assert all("private-test-key" not in url for url in index)
    monkeypatch.setattr(collection, "catalog", lambda *a, **kw: pytest.fail("Search must be local"))
    result = collection.search("star wars")  # Parent theme matches names that omit Star Wars.
    assert len(result["sets"]) == 20 and result["next"]
    assert all(row["num_parts"] > 0 for row in result["sets"])
    second = collection.search("star wars", 2)
    assert len(second["sets"]) == 6 and not second["next"]
    assert second["sets"][-1]["num_parts"] == 0  # Catalog retains merchandise too.
    assert collection.search("https://rebrickable.com/sets/75000-1/")["sets"][0]["set_num"] == "75000-1"
    assert collection.search("' OR 1=1 --")["sets"] == []
    assert collection.search("%")["sets"] == []
    # A restart and a removed key keep the catalog searchable without redownloading.
    set_catalog._progress.clear()
    monkeypatch.setattr(environment_config, "snapshot", lambda: {})
    set_catalog.ensure()
    assert collection.search("falcon")["sets"] and len(index) == 2


def test_failed_refresh_keeps_complete_previous_catalog_and_can_retry(index, monkeypatch):
    set_catalog.ensure()
    set_catalog._worker.join(5)
    original = set_catalog.path().read_bytes()
    download = set_catalog._download
    def broken(name, folder):
        if name == "sets":
            yield {"set_num": "12345-1", "name": "Partial", "year": "2026", "theme_id": "1", "num_parts": "3"}
            raise URLError("private-test-key must never leak")
        else:
            yield from download(name, folder)
    monkeypatch.setattr(set_catalog, "_download", broken)
    set_catalog.ensure(refresh=True)
    set_catalog._worker.join(5)
    state = set_catalog.status()
    assert state["ready"] and state["state"] == "error"
    assert "private-test-key" not in str(state)
    assert set_catalog.path().read_bytes() == original
    assert len(list(set_catalog.path().parent.iterdir())) == 1
    monkeypatch.setattr(set_catalog, "_download", download)
    set_catalog.ensure(refresh=True)
    set_catalog._worker.join(5)
    assert set_catalog.status()["state"] == "ready"


def test_background_sync_deduplicates_and_old_search_remains_usable(index, monkeypatch):
    set_catalog.ensure()
    set_catalog._worker.join(5)
    entered, release = threading.Event(), threading.Event()
    original = set_catalog._download
    def slow(*args):
        entered.set()
        release.wait(3)
        yield from original(*args)
    monkeypatch.setattr(set_catalog, "_download", slow)
    set_catalog.ensure(refresh=True)
    assert entered.wait(2)
    worker = set_catalog._worker
    set_catalog.ensure(refresh=True)
    assert worker is set_catalog._worker
    assert set_catalog.status()["state"] == "syncing" and collection.search("falcon")["sets"]
    release.set()
    worker.join(5)
    assert set_catalog.status()["state"] == "ready"


def test_catalog_api_reports_missing_initial_download_and_retries(index):
    client = TestClient(main.app)
    assert client.get("/api/collection/catalog").json()["ready"] is False
    assert client.get("/api/collection/sets", params={"search": "falcon"}).status_code == 400
    assert client.post("/api/collection/catalog").status_code == 200
    set_catalog._worker.join(5)
    assert client.get("/api/collection/catalog").json()["total_sets"] == 26
