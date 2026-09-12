import importlib.util
import zipfile
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "catalogflow_windows_build", ROOT / "packaging" / "build_windows.py"
)
assert SPEC is not None and SPEC.loader is not None
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def test_release_assets_exist_and_only_include_expected_public_resources():
    assets = build.public_assets(ROOT)
    assert len(assets) == 7
    assert any(Path(source).name == "dashboard-history.js" for source, _ in assets)
    assert any(Path(source).name == "dashboard-import.js" for source, _ in assets)
    assert any(destination == "catalogflow/schemas" for _, destination in assets)
    assert all(Path(source).is_relative_to(ROOT / "src" / "catalogflow") for source, _ in assets)
    assert all(Path(source).suffix in {".html", ".js", ".json"} for source, _ in assets)


def test_missing_asset_fails_instead_of_shipping_broken_dashboard(tmp_path):
    with pytest.raises(ValueError, match="Missing or external release asset"):
        build.public_assets(tmp_path)


def test_metadata_excludes_local_install_urls_and_package_record(monkeypatch, tmp_path):
    selected = []

    class Distribution:
        files = [
            PurePosixPath(name)
            for name in (
                "catalogflow/__init__.py",
                "catalogflow-0.8.0.dist-info/METADATA",
                "catalogflow-0.8.0.dist-info/entry_points.txt",
                "catalogflow-0.8.0.dist-info/direct_url.json",
                "catalogflow-0.8.0.dist-info/RECORD",
                "catalogflow-0.8.0.dist-info/licenses/LICENSE",
            )
        ]

        def locate_file(self, file):
            selected.append(file.name)
            return tmp_path / str(file)

    monkeypatch.setattr(build.importlib.metadata, "distribution", lambda name: Distribution())
    files = build.metadata_files("catalogflow")
    assert selected == ["METADATA", "entry_points.txt", "LICENSE"]
    assert len(files) == 3


def test_archive_allowlist_never_collects_configs_reports_or_output_directory(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "LICENSE").write_text("public license")
    (tmp_path / "docs" / "windows.md").write_text("public guide")
    output = tmp_path / "dist"
    output.mkdir()
    executable = output / "CatalogFlow.exe"
    executable.write_bytes(b"synthetic executable")
    (output / "THIRD_PARTY_LICENSES.txt").write_text("public dependency licenses")
    (output / "profile.json").write_text("private test marker")
    (tmp_path / "report.txt").write_text("private test marker")
    archive = build.release_zip(tmp_path, executable, "0.8.0", output)
    with zipfile.ZipFile(archive) as packaged:
        assert packaged.namelist() == [
            "CatalogFlow-0.8.0/CatalogFlow.exe",
            "CatalogFlow-0.8.0/LICENSE.txt",
            "CatalogFlow-0.8.0/WINDOWS.md",
            "CatalogFlow-0.8.0/THIRD_PARTY_LICENSES.txt",
        ]
        assert all(
            b"private test marker" not in packaged.read(name) for name in packaged.namelist()
        )


@pytest.mark.parametrize("version", ["0.8.0rc1", "0.8", "invalid"])
def test_invalid_windows_version_does_not_generate_executable_metadata(tmp_path, version):
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')
    with pytest.raises(ValueError, match="numeric"):
        build.project_version(tmp_path)


def test_numeric_version_has_consistent_windows_file_and_product_metadata():
    resource = build.version_resource("0.8.0")
    assert "filevers=(0, 8, 0, 0)" in resource
    assert "prodvers=(0, 8, 0, 0)" in resource
    assert "StringStruct('FileVersion', '0.8.0')" in resource
    assert "StringStruct('ProductVersion', '0.8.0')" in resource
