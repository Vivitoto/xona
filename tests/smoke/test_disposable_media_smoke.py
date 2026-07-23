from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import disposable_smoke


def test_canonicalizes_paths_and_rejects_symlinks_missing_and_ambiguous_paths() -> None:
    root = disposable_smoke.create_disposable_root()
    try:
        sandbox = disposable_smoke.DisposableSmokeSandbox(root)
        sandbox.mkdir("incoming")
        media = sandbox.write_bytes("incoming/movie.mp4", b"movie")

        resolved = disposable_smoke.canonicalize_path(
            root / "incoming" / ".." / "incoming" / "movie.mp4",
            root=root,
            require_exists=True,
        )
        assert resolved == media

        symlink = root / "incoming-link"
        symlink.symlink_to(root / "incoming", target_is_directory=True)
        with pytest.raises(disposable_smoke.SmokeSafetyError, match="symlink"):
            disposable_smoke.canonicalize_path(
                symlink / "movie.mp4",
                root=root,
                require_exists=True,
            )

        with pytest.raises(disposable_smoke.SmokeSafetyError, match="does not exist"):
            disposable_smoke.canonicalize_path(
                root / "incoming" / "missing.mp4",
                root=root,
                require_exists=True,
            )

        with pytest.raises(disposable_smoke.SmokeSafetyError, match="Ambiguous"):
            disposable_smoke.canonicalize_unique_paths(
                [media, root / "incoming" / "." / "movie.mp4"],
                root=root,
                require_exists=True,
            )
    finally:
        disposable_smoke.cleanup_disposable_root(root)


def test_disposable_root_must_be_generated_under_tmp_xona_smoke(tmp_path: Path) -> None:
    root = disposable_smoke.create_disposable_root()
    try:
        assert root.parent == Path("/tmp").resolve(strict=True)
        assert root.name.startswith("xona-smoke-")
        assert disposable_smoke.validate_disposable_root(root) == root
    finally:
        disposable_smoke.cleanup_disposable_root(root)

    outside_tmp = tmp_path / "xona-smoke-outside"
    outside_tmp.mkdir()
    with pytest.raises(disposable_smoke.SmokeSafetyError, match="/tmp/xona-smoke"):
        disposable_smoke.validate_disposable_root(outside_tmp, require_marker=False)

    manual_root = Path("/tmp") / f"xona-smoke-manual-{os.getpid()}"
    manual_root.mkdir()
    try:
        with pytest.raises(disposable_smoke.SmokeSafetyError, match="not generated"):
            disposable_smoke.validate_disposable_root(manual_root)
    finally:
        manual_root.rmdir()


def test_sandbox_refuses_reads_writes_outside_root_and_user_media(tmp_path: Path) -> None:
    root = disposable_smoke.create_disposable_root()
    user_media = tmp_path / "user-media"
    user_media.mkdir()
    (user_media / "private.mp4").write_bytes(b"private")
    try:
        sandbox = disposable_smoke.DisposableSmokeSandbox(root)
        sandbox.mkdir("incoming")

        with pytest.raises(disposable_smoke.SmokeSafetyError, match="outside"):
            sandbox.read_bytes(user_media / "private.mp4")
        with pytest.raises(disposable_smoke.SmokeSafetyError, match="outside"):
            sandbox.write_bytes(tmp_path / "outside.mp4", b"outside")
        assert not (tmp_path / "outside.mp4").exists()

        guarded = disposable_smoke.DisposableSmokeSandbox(
            root,
            user_media_roots=(user_media,),
        )
        with pytest.raises(disposable_smoke.SmokeSafetyError, match="user media root"):
            disposable_smoke.canonicalize_path(
                user_media / "private.mp4",
                require_exists=True,
                user_media_roots=(user_media,),
            )
        assert guarded.path("incoming", require_exists=True) == root / "incoming"
    finally:
        disposable_smoke.cleanup_disposable_root(root)


def test_disposable_smoke_uses_only_synthetic_temp_media(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    user_media = tmp_path / "real-media"
    user_media.mkdir()
    sentinel = user_media / "sentinel.mp4"
    sentinel.write_bytes(b"do-not-touch")
    monkeypatch.setenv("STORAGE_ROOTS", str(user_media))

    result = disposable_smoke.run_disposable_smoke()

    assert result.status == "passed"
    assert result.cleaned_up is True
    assert not result.root.exists()
    assert sentinel.read_bytes() == b"do-not-touch"
