from app.modules.registry import list_modules


def test_native_modules_include_v22_scanners():
    ids = [module["id"] for module in list_modules()]
    assert "credential_leaks" in ids
    assert "ahmia_search" in ids
    assert "breach_scan" in ids
