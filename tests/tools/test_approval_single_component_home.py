"""Absolute single-directory homes remain sensitive, unlike filesystem roots."""
import pytest
from tools.approval_detection import detect_dangerous_command, _home_prefix_fold_regex

@pytest.mark.parametrize("home", ["/root", "/srv", "/home/alice"])
def test_absolute_home_ssh_write_requires_approval(monkeypatch, home):
    monkeypatch.setenv("HOME", home)
    dangerous, key, _ = detect_dangerous_command(f"printf test >> {home}/.ssh/authorized_keys")
    assert dangerous and key
    assert not detect_dangerous_command(f"cat {home}/.ssh/authorized_keys")[0]
    assert not detect_dangerous_command(f"printf test > {home}/notes.txt")[0]

@pytest.mark.parametrize("home", ["", "/", "C:\\", "C:", "root", ".", ".."])
def test_degenerate_home_does_not_fold_other_paths(home):
    assert _home_prefix_fold_regex(home) is None
