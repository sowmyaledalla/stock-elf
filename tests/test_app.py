"""Smoke tests: pages that need no network render, and removed pages stay removed."""
import pytest
from app import app


@pytest.fixture()
def client():
    return app.test_client()


@pytest.mark.parametrize("path", ["/", "/how-to-use", "/methodology", "/methodology/dcf", "/methodology/technicals",
                                  "/technicals", "/dcf", "/dcf2", "/skills/catalog"])
def test_pages_load(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/rule1", "/robinhood/auth", "/options", "/_savelog"])
def test_removed_pages_are_gone(client, path):
    assert client.get(path).status_code == 404


def test_brand_bar_on_every_page(client):
    for path in ["/", "/how-to-use", "/methodology/dcf", "/technicals", "/dcf2"]:
        assert b"Stock Elf" in client.get(path).data


def test_narrative_prompt_fills_ticker(client):
    r = client.get("/skills/prompt?skill=company-narrative&ticker=msft")
    assert r.status_code == 200 and b"MSFT" in r.data
    assert client.get("/skills/prompt?skill=nope&ticker=MSFT").status_code == 400


def test_dcf_calc_requires_ticker(client):
    assert client.post("/dcf/calc", json={}).status_code == 400


@pytest.mark.parametrize("path", ["/how-to-use", "/methodology", "/methodology/dcf", "/methodology/technicals"])
def test_doc_anchors_resolve(client, path):
    """Every '#section' link in a rendered doc points at a real heading id (the same links work on GitHub)."""
    import re
    html = client.get(path).get_data(as_text=True)
    ids = set(re.findall(r'id="([^"]+)"', html))
    missing = [h for h in re.findall(r'href="#([^"]+)"', html) if h not in ids]
    assert not missing


def test_doc_cross_links_use_app_routes(client):
    html = client.get("/methodology").get_data(as_text=True)
    assert 'href="/methodology/dcf"' in html and ".md" not in html
