from pathlib import Path

from clone_manager import paths


def _make_data_dir(root: Path) -> Path:
    (root / "config").mkdir(parents=True)
    (root / "assets").mkdir()
    (root / "config" / "command_responses.json").write_text("{}", encoding="utf-8")
    (root / "assets" / "branding.jpg").write_bytes(b"test-image")
    return root


def test_explicit_data_dir_is_used(monkeypatch, tmp_path):
    data_dir = _make_data_dir(tmp_path / "runtime-data")
    monkeypatch.setenv("CLONE_MANAGER_DATA_DIR", str(data_dir))
    monkeypatch.chdir(tmp_path)

    assert paths.resolve_app_data_dir() == data_dir.resolve()


def test_working_directory_wins_over_installed_package_path(monkeypatch, tmp_path):
    runtime_dir = _make_data_dir(tmp_path / "app")
    fake_package_file = (
        tmp_path
        / "venv"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "clone_manager"
        / "paths.py"
    )
    fake_package_file.parent.mkdir(parents=True)
    fake_package_file.write_text("# simulated installed package", encoding="utf-8")

    monkeypatch.delenv("CLONE_MANAGER_DATA_DIR", raising=False)
    monkeypatch.chdir(runtime_dir)
    monkeypatch.setattr(paths, "__file__", str(fake_package_file))

    assert paths.resolve_app_data_dir() == runtime_dir.resolve()
