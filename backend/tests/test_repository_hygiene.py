"""Local mirror of repository-hygiene machine-path regressions."""

import re


def _contains_machine_path(line: str) -> bool:
    machine_path_patterns = [
        re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\"),
        re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:/(?:Users|home)/[^/\s]+/"),
        re.compile(r"(?<![A-Za-z0-9:/])/(?:Users|home)/[^/\s]+/"),
    ]
    web_url_pattern = re.compile(r"https?://[^\s<>()\[\]{}\"']+")
    without_web_urls = web_url_pattern.sub("", line)
    return any(pattern.search(without_web_urls) for pattern in machine_path_patterns)


def test_hygiene_detects_windows_backslash_and_forward_slash_paths():
    windows_path = "C:" + chr(92) + "Users" + chr(92) + "alice" + chr(92) + "file.txt"
    windows_forward = "C:" + "/" + "Users/alice/file.txt"
    posix_home = "/" + "home/alice/file.txt"
    macos_users = "/" + "Users/alice/file.txt"
    assert _contains_machine_path(windows_path)
    assert _contains_machine_path(windows_forward)
    assert _contains_machine_path("path=" + windows_forward)
    assert _contains_machine_path(posix_home)
    assert _contains_machine_path(macos_users)


def test_hygiene_ignores_path_like_segments_inside_urls():
    windows_forward = "C:" + "/" + "Users/alice/file.txt"
    assert not _contains_machine_path("https://example.com/home/alice/profile")
    assert not _contains_machine_path("See https://example.com/Users/alice/profile")
    assert not _contains_machine_path("https://cdn.example.com/" + windows_forward)
