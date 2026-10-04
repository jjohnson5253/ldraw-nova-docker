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
FILES = {
    "themes": THEMES, "sets": SETS,
    "inventories": "id,version,set_num\n1,1,75000-1\n2,2,75000-1\n3,1,fig-001\n4,1,75001-1\n",
    "inventory_parts": "inventory_id,part_num,color_id,quantity,is_spare,img_url\n1,3001,5,99,False,image\n2,3001,5,2,False,image\n2,3001,5,1,True,image\n3,3003,1,1,False,image\n3,3001,5,1,True,image\n4,3003,1,2,False,image\n",
    "inventory_minifigs": "inventory_id,fig_num,quantity\n2,fig-001,2\n",
    "inventory_sets": "inventory_id,set_num,quantity\n2,75001-1,3\n",
    "parts": "part_num,name,part_cat_id,part_material\n3001,Brick 2 x 4,1,Plastic\n3003,Brick 2 x 2,1,Plastic\n",
    "colors": "id,name,rgb,is_trans\n5,Red,FF0000,False\n1,Blue,0000FF,False\n",
    "minifigs": "fig_num,name,num_parts,img_url\nfig-001,Figure,1,image\n",
    "part_relationships": "rel_type,child_part_num,parent_part_num\n",
    "elements": "element_id,part_num,color_id,design_id\n12345,3001,5,3001\n",
    "part_categories": "id,name\n1,Bricks\n",
}


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
            text = FILES[url.rsplit("/", 1)[-1].removesuffix(".csv.gz")]
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
    assert len(index) == 12 and all(url.startswith("https://cdn.rebrickable.com/") for url in index)
    assert set_catalog.status()["inventory_ready"]
    assert set_catalog.status()["total_parts"] == 2
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
    assert collection.search("falcon")["sets"] and len(index) == 12


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
    assert len(list(set_catalog.path().parent.iterdir())) == 2
    monkeypatch.setattr(set_catalog, "_download", download)
    set_catalog.ensure(refresh=True)
    set_catalog._worker.join(5)
    assert set_catalog.status()["state"] == "ready"


def test_background_sync_deduplicates_and_blocks_search_until_finished(index, monkeypatch):
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
    assert set_catalog.status()["state"] == "syncing" and not set_catalog.status()["ready"]
    with pytest.raises(ValueError, match="Wait for indexing to finish"):
        collection.search("falcon")
    client = TestClient(main.app)
    assert client.get("/api/collection/catalog").json()["ready"] is False
    assert client.get("/api/collection/sets", params={"search": "falcon"}).status_code == 400
    release.set()
    worker.join(5)
    assert set_catalog.status()["state"] == "ready"
    assert collection.search("falcon")["sets"]
    assert client.get("/api/collection/sets", params={"search": "falcon"}).status_code == 200


def test_catalog_api_reports_missing_initial_download_and_retries(index):
    client = TestClient(main.app)
    assert client.get("/api/collection/catalog").json()["ready"] is False
    assert client.get("/api/collection/sets", params={"search": "falcon"}).status_code == 400
    assert client.post("/api/collection/catalog").status_code == 200
    set_catalog._worker.join(5)
    assert client.get("/api/collection/catalog").json()["total_sets"] == 26


def test_sets_are_searchable_while_inventory_index_builds_and_upgrade_skips_sets(index, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = set_catalog._download
    def slow(name, folder, fields=None):
        if name == "inventory_parts":
            entered.set()
            release.wait(5)
        yield from original(name, folder, fields)
    monkeypatch.setattr(set_catalog, "_download", slow)
    set_catalog.ensure()
    assert entered.wait(3)
    state = set_catalog.status()
    assert state["ready"] and not state["inventory_ready"] and state["state"] == "inventory_syncing"
    assert collection.search("falcon")["sets"]
    assert set_catalog.inventory("75000-1") is None  # API fallback until every table is ready.
    release.set()
    set_catalog._worker.join(5)
    assert set_catalog.status()["inventory_ready"]
    # Existing installations download the additional files without rebuilding sets.
    set_catalog.inventory_path().unlink()
    index.clear()
    set_catalog.ensure()
    set_catalog._worker.join(5)
    assert len(index) == 10 and all("/sets.csv.gz" not in url and "/themes.csv.gz" not in url for url in index)


def test_local_inventory_versions_minifigs_contained_sets_spares_and_api_mapping(index, monkeypatch):
    set_catalog.ensure()
    set_catalog._worker.join(5)
    source = set_catalog.inventory("75000-1")
    assert {(r["part_num"], r["color_id"]): r["quantity"] for r in source["parts"]} == {("3001", 5): 2, ("3003", 1): 8}
    source = set_catalog.inventory("75000-1", True)
    assert {(r["part_num"], r["color_id"]): r["quantity"] for r in source["parts"]} == {("3001", 5): 5, ("3003", 1): 8}
    assert set_catalog.inventory("12345-1") is None
    def api(path, **params):
        if path == "colors/":
            return {"results": [{"id": 5, "external_ids": {"LDraw": {"ext_ids": [4]}}}, {"id": 1, "external_ids": {"LDraw": {"ext_ids": [1]}}}]}
        assert path == "parts/" and params["part_nums"] == "3001,3003"  # No set/inventory API calls.
        return {"results": [{"part_num": part, "external_ids": {"LDraw": [part]}} for part in ("3001", "3003")]}
    monkeypatch.setattr(collection, "catalog", api)
    mapped = collection.preview({"set": "75000", "include_spares": False})
    assert {(r["part"], r["colour"]): r["quantity"] for r in mapped["parts"]} == {("3001", 4): 2, ("3003", 1): 8}


def test_failed_inventory_refresh_preserves_previous_complete_data_and_search(index, monkeypatch):
    set_catalog.ensure()
    set_catalog._worker.join(5)
    previous = set_catalog.inventory_path().read_bytes()
    original = set_catalog._download
    def broken(name, folder, fields=None):
        if name == "inventory_parts":
            raise URLError("private-key must never leak")
        yield from original(name, folder, fields)
    monkeypatch.setattr(set_catalog, "_download", broken)
    set_catalog.ensure(refresh=True)
    set_catalog._worker.join(5)
    state = set_catalog.status()
    assert state["ready"] and state["inventory_ready"] and state["state"] == "error"
    assert "private-key" not in str(state)
    assert set_catalog.inventory_path().read_bytes() == previous
    assert collection.search("falcon")["sets"] and set_catalog.inventory("75000-1")
    assert len(list(set_catalog.path().parent.iterdir())) == 2
