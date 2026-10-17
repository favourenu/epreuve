from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import serve_frontend


def make_client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app shell</html>")
    (tmp_path / "assets" / "app-1234.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("do not serve")
    app = FastAPI()
    serve_frontend(app, tmp_path)
    return TestClient(app)


def test_client_routes_get_the_app_shell(tmp_path):
    c = make_client(tmp_path)
    for path in ("/", "/dashboard", "/reset-password", "/attempts/abc/results"):
        r = c.get(path)
        assert r.status_code == 200 and "app shell" in r.text, path
        assert r.headers["cache-control"] == "no-cache"


def test_static_files_are_served(tmp_path):
    c = make_client(tmp_path)
    assert c.get("/assets/app-1234.js").text == "console.log(1)"
    assert c.get("/favicon.svg").text == "<svg/>"


def test_unknown_api_paths_are_404_not_the_app(tmp_path):
    c = make_client(tmp_path)
    assert c.get("/api/nope").status_code == 404


def test_files_outside_the_build_folder_are_never_served(tmp_path):
    c = make_client(tmp_path)
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        assert "do not serve" not in c.get(path).text, path
