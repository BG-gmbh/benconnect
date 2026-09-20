from pathlib import Path


def test_setup_page_uses_shared_form_handler_for_setup_requests():
    repo_root = Path(__file__).resolve().parents[1]
    html_path = repo_root / "flutter_app" / "docs" / "setup.html"
    config_path = repo_root / "flutter_app" / "docs" / "js" / "config.js"
    form_handler_path = repo_root / "flutter_app" / "docs" / "js" / "form-handler.js"

    html = html_path.read_text(encoding="utf-8")
    config_js = config_path.read_text(encoding="utf-8")
    form_handler_js = form_handler_path.read_text(encoding="utf-8")

    assert '<script src="/js/config.js"></script>' in html
    assert '<script src="/js/form-handler.js"></script>' in html
    assert 'action="/setup"' in html
    # config.js loest API-Aufrufe lokal same-origin auf (relative URLs) und
    # bleibt in Produktion same-origin, damit /setup unter benconnect.de an
    # denselben Render-Service geht.
    assert 'resolveApiUrl' in config_js
    assert 'function detectApiBase' in config_js
    assert 'return "";' in config_js
    assert 'group-ly.tech' not in config_js
    assert 'function normalizeAction' in form_handler_js
