"""Recover missing empty Git skeleton dirs without rewriting checkpoints."""
import subprocess

from tools import checkpoint_manager as cp


def test_existing_store_missing_refs_is_repaired_before_git_operation(tmp_path):
    store = tmp_path / 'store'
    subprocess.run(['git', 'init', '--bare', str(store)], check=True, capture_output=True)
    (store / 'refs' / 'heads').rmdir()
    (store / 'refs' / 'tags').rmdir()
    (store / 'refs').rmdir()
    # Model the post-gc layout, including packed refs. Never reinitialize it.
    (store / 'packed-refs').write_text('# pack-refs with: peeled fully-peeled sorted\n')
    before = {p.relative_to(store): p.read_bytes() for p in store.rglob('*') if p.is_file()}
    ok, output, error = cp._run_git(['rev-parse', '--git-dir'], store, str(tmp_path))
    assert ok, error
    assert output == str(store)
    assert (store / 'refs' / 'heads').is_dir()
    assert all((store / name).read_bytes() == contents for name, contents in before.items())


def test_missing_store_is_not_created_by_read_only_git_probe(tmp_path):
    store = tmp_path / 'absent'
    ok, _, _ = cp._run_git(['rev-parse', '--is-bare-repository'], store, str(tmp_path))
    assert not ok
    assert not store.exists()
