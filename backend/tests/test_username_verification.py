"""Username verification-state classification (no live HTTP)."""

from app.models.evidence import VerificationState
from app.modules.username.scanner import UsernameScanModule


def test_http_200_alone_is_possible_not_verified():
    mod = UsernameScanModule()
    site = {"name": "Example", "e_code": 200}
    assess = mod._assess_response(200, "<html>welcome</html>", site)
    assert assess.verification == VerificationState.POSSIBLE


def test_positive_marker_with_exists_code_is_verified():
    mod = UsernameScanModule()
    site = {"name": "Example", "e_code": 200, "e_string": "@janedoe"}
    assess = mod._assess_response(200, "Profile page for @janedoe", site)
    assert assess.verification == VerificationState.VERIFIED
    assert "@janedoe" in assess.positive_markers


def test_missing_marker_is_not_found():
    mod = UsernameScanModule()
    site = {"name": "Example", "m_string": "user not found", "m_code": 200}
    assess = mod._assess_response(200, "Sorry, user not found", site)
    assert assess.verification == VerificationState.NOT_FOUND


def test_captcha_wall_is_blocked():
    mod = UsernameScanModule()
    site = {"name": "Example", "e_code": 200, "e_string": "profile"}
    assess = mod._assess_response(200, "Checking your browser before redirect", site)
    assert assess.verification == VerificationState.BLOCKED
