"""One origin: the API serves its own pages, and a page can tell what answered it.

This pins the failure that made the app look broken in a browser during the last
run-through: the pages defaulted to port 8000, a different project's server was
sitting on it and answered with HTML, and every panel said only "could not reach
the server" with no way to see who was really there.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.main import app


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


@pytest.fixture
def client():
    return TestClient(app)


def test_the_api_root_serves_the_dashboard(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "<h1>Checkiz</h1>" in res.text


@pytest.mark.parametrize("page", ["index.html", "qr.html", "overlay.html"])
def test_every_page_loads_and_shares_one_api_rule(client, page):
    """Each page used to guess its own port, which is how a foreign server on 8000
    made the whole app look broken. All three must carry the shared helper."""
    res = client.get("/" + page)
    assert res.status_code == 200, res.text
    assert "<title>" in res.text
    assert '<script src="api.js">' in res.text


@pytest.mark.parametrize("helper", ["api.js", "camera.js"])
def test_the_shared_scripts_are_served(client, helper):
    res = client.get("/" + helper)
    assert res.status_code == 200
    assert res.text.strip()


def test_an_api_route_wins_over_the_page_folder(client):
    """The mount is last, so /health and /history stay JSON even though "/" is
    now a catch-all. If it were mounted first the dashboard would be the only
    thing that worked and every fetch would get HTML back."""
    res = client.get("/history")
    assert res.status_code == 200
    assert res.json() == []


def test_health_names_the_server_so_a_page_can_tell_it_apart(client):
    body = client.get("/health").json()
    assert body["name"] == "checkiz"
    assert body["ui"] is True


def test_frontend_dir_takes_the_environment_override(tmp_path, monkeypatch):
    pages = tmp_path / "web"
    pages.mkdir()
    monkeypatch.setenv("CHECKIZ_FRONTEND", str(pages))
    assert main.frontend_dir() == str(pages)


def test_frontend_dir_finds_the_pages_next_to_the_package(tmp_path, monkeypatch):
    """No override: the folder beside this file's own backend/ is the answer, which
    is the same rule that puts /app/frontend next to /app/backend in the image."""
    monkeypatch.delenv("CHECKIZ_FRONTEND", raising=False)
    fake = tmp_path / "checkiz"
    (fake / "backend" / "app").mkdir(parents=True)
    (fake / "frontend").mkdir()
    monkeypatch.setattr(main, "__file__", str(fake / "backend" / "app" / "main.py"))
    assert main.frontend_dir() == str(fake / "frontend")


def test_frontend_dir_says_none_instead_of_mounting_nothing(tmp_path, monkeypatch):
    """A container with only the backend in it must still serve the API; the pages
    are an addition, not a dependency."""
    monkeypatch.delenv("CHECKIZ_FRONTEND", raising=False)
    monkeypatch.setattr(main, "__file__", str(tmp_path / "nope" / "app" / "main.py"))
    assert main.frontend_dir() is None


def test_the_pages_folder_found_for_this_checkout_has_the_dashboard():
    pages = Path(main.FRONTEND)
    assert (pages / "index.html").is_file()
    assert (pages / "api.js").is_file()


def test_the_api_key_box_is_wired_to_remember_and_reload():
    """A server with CHECKIZ_API_KEY kept saying "Invalid or missing API key" until the
    seller retyped the secret on every page and after every refresh, because the box
    was the only place it lived. The behaviour is executed against a stubbed DOM (see
    docs/STATUS.md, "The key box that remembered nothing"); this pins the wiring, so a
    page cannot quietly stop using the helper and pass the behavioural tests."""
    pages = Path(main.FRONTEND)
    api = (pages / "api.js").read_text()
    assert "function checkizKey(" in api
    assert "sessionStorage.setItem" in api and "sessionStorage.getItem" in api
    assert "localStorage.setItem" not in api and "localStorage.getItem" not in api, \
        "a key kept past the tab outlives a shared till"

    idx = (pages / "index.html").read_text()
    first_request = idx.index("\nloadLedger(); loadHistory(); loadOrders(); loadReview();")
    assert idx.index("checkizKey(") < first_request, "the box must be filled before the first request"
    assert "checkizKey(() => { loadLedger(); loadHistory(); loadOrders(); loadReview(); });" in idx

    qr = (pages / "qr.html").read_text()
    assert "checkizKey(() => loadSeller());\nloadSeller();" in qr, \
        "the call that fails at open is the one entering the key has to retry"
    assert "checkizKey" not in (pages / "overlay.html").read_text(), \
        "the overlay has no box to fill - it takes ?key= in the OBS URL"


# ---- the database file location --------------------------------------------

def test_the_database_path_can_be_pointed_at_another_file(tmp_path, monkeypatch):
    """Two instances on one machine - a demo over the seller's data, a device test -
    must not be able to write into the same SQLite file."""
    monkeypatch.setenv("CHECKIZ_DB_PATH", str(tmp_path / "demo.db"))
    assert db._db_path() == tmp_path / "demo.db"


def test_a_relative_or_home_tilde_path_becomes_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CHECKIZ_DB_PATH", "side.db")
    assert db._db_path() == tmp_path / "side.db"
    monkeypatch.setenv("CHECKIZ_DB_PATH", "~/side.db")
    assert db._db_path().is_absolute() and "~" not in str(db._db_path())


def test_the_default_stays_beside_the_package(tmp_path, monkeypatch):
    monkeypatch.delenv("CHECKIZ_DB_PATH", raising=False)
    monkeypatch.setattr(db, "__file__", str(tmp_path / "backend" / "app" / "db.py"))
    assert db._db_path() == tmp_path / "backend" / "checkiz.db"


def test_a_pointed_at_database_is_the_one_that_gets_created(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKIZ_DB_PATH", str(tmp_path / "elsewhere.db"))
    monkeypatch.setattr(db, "DB_PATH", db._db_path())
    db.init_db()
    assert (tmp_path / "elsewhere.db").is_file()
