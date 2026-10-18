from tests.test_certification_admin import admin  # noqa: F401  (fixture)


def test_public_docs_are_read_only_and_leave_out_admin(anon):
    page = anon.get("/api/docs")
    assert page.status_code == 200 and '"supportedSubmitMethods": []' in page.text

    spec = anon.get("/api/openapi.json").json()
    paths = spec["paths"]
    assert "/api/auth/login" in paths and "/api/public/certificates/{code}" in paths
    assert not any(p.startswith(("/api/admin", "/api/internal")) for p in paths)
    assert "/api/payments/paystack/webhook" not in paths
    assert "admin" not in {t["name"] for t in spec["tags"]}


def test_default_docs_are_switched_off(anon):
    for path in ("/docs", "/redoc", "/openapi.json"):
        r = anon.get(path)
        assert r.status_code == 404 or "swagger" not in r.text.lower()


def test_internal_docs_are_for_admins_only(anon, client, admin):  # noqa: F811
    for c in (anon, client):
        assert c.get("/api/internal/docs").status_code in (401, 403)
        assert c.get("/api/internal/openapi.json").status_code in (401, 403)

    page = admin.get("/api/internal/docs")
    assert page.status_code == 200 and "supportedSubmitMethods" not in page.text
    paths = admin.get("/api/internal/openapi.json").json()["paths"]
    assert "/api/admin/users" in paths and "/api/auth/login" in paths
