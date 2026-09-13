"""Build a Windows desktop executable from public sources in an isolated environment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tomllib
import venv
import zipfile
from pathlib import Path

PUBLIC_ASSETS = (
    "dashboard.html",
    "dashboard-i18n.js",
    "dashboard-fx.js",
    "dashboard-history.js",
    "dashboard-import.js",
    "dashboard-setup.js",
    "schemas/listing.schema.json",
    "browser/catalogflow-collector.user.js",
)
_METADATA_NAMES = {"METADATA", "WHEEL", "entry_points.txt", "top_level.txt"}


def project_version(root: Path) -> str:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Windows releases require a numeric major.minor.patch version")
    return version


def public_assets(root: Path) -> list[tuple[str, str]]:
    package = root / "src" / "catalogflow"
    assets = []
    for relative in PUBLIC_ASSETS:
        path = package / relative
        if not path.is_file() or not path.resolve().is_relative_to(package.resolve()):
            raise ValueError(f"Missing or external release asset: {relative}")
        assets.append((str(path), (Path("catalogflow") / relative).parent.as_posix()))
    return assets


def metadata_files(distribution_name: str) -> list[tuple[str, str]]:
    """Keep entry points and licenses, excluding pip's local direct_url.json and RECORD."""
    distribution = importlib.metadata.distribution(distribution_name)
    result = []
    for file in distribution.files or ():
        parts = file.parts
        if not parts or not parts[0].endswith(".dist-info"):
            continue
        if file.name not in _METADATA_NAMES and not any(
            part.lower().startswith(("license", "copying")) for part in parts[1:]
        ):
            continue
        result.append((str(distribution.locate_file(file)), file.parent.as_posix()))
    if not any(Path(source).name == "METADATA" for source, _ in result):
        raise ValueError(f"Missing release metadata: {distribution_name}")
    return result


def version_resource(version: str) -> str:
    number = (*map(int, version.split(".")), 0)
    return f"""VSVersionInfo(
    ffi=FixedFileInfo(filevers={number!r}, prodvers={number!r}, mask=0x3f,
        flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('CompanyName', 'CatalogFlow contributors'),
        StringStruct('FileDescription', 'CatalogFlow local desktop workbench'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'CatalogFlow'),
        StringStruct('LegalCopyright', 'CatalogFlow contributors - MIT License'),
        StringStruct('OriginalFilename', 'CatalogFlow.exe'),
        StringStruct('ProductName', 'CatalogFlow'),
        StringStruct('ProductVersion', '{version}')])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"""


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_fingerprint(root: Path) -> str:
    """Detect concurrent source edits so the release cannot mix different working states."""
    sources = list((root / "src" / "catalogflow").rglob("*.py"))
    sources.extend(Path(source) for source, _ in public_assets(root))
    sources.extend(
        root / path
        for path in (
            "pyproject.toml",
            "LICENSE",
            "docs/windows.md",
            "packaging/desktop_entry.py",
            "packaging/catalogflow.spec",
            "packaging/build_windows.py",
            "packaging/requirements-windows.txt",
            "packaging/THIRD-PARTY-NOTICES.txt",
        )
    )
    digest = hashlib.sha256()
    for path in sorted(sources):
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Release sources must remain inside the checkout")
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def release_zip(root: Path, executable: Path, version: str, output: Path) -> Path:
    """Explicit file allowlist: never archive a working tree or a user's configuration."""
    archive_path = output / f"CatalogFlow-{version}-windows-x64.zip"
    entries = (
        (executable, "CatalogFlow.exe"),
        (root / "LICENSE", "LICENSE.txt"),
        (root / "docs" / "windows.md", "WINDOWS.md"),
        (output / "THIRD_PARTY_LICENSES.txt", "THIRD_PARTY_LICENSES.txt"),
    )
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, name in entries:
            archive.write(source, f"CatalogFlow-{version}/{name}")
    return archive_path


def run_build_command(arguments: list[str], root: Path, environment: dict[str, str]) -> None:
    subprocess.run(  # noqa: S603 - fixed build commands passed as an argument list, never a shell
        arguments, cwd=root, env=environment, check=True
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare-only", action="store_true", help="Install isolated build dependencies"
    )
    parser.add_argument(
        "--skip-install", action="store_true", help="Reuse the prepared build environment"
    )
    args = parser.parse_args(argv)
    if (
        sys.platform != "win32"
        or platform.machine().lower() not in {"amd64", "x86_64"}
        or struct.calcsize("P") != 8
        or sys.version_info[:2] != (3, 11)
    ):
        parser.error("Build this Windows x64 release using Windows x64 and CPython 3.11 x64")
    root = Path(__file__).resolve().parents[1]
    version = project_version(root)
    public_assets(root)
    work = root / "build" / "windows"
    output = root / "dist" / "windows"
    for directory in (work, output):
        if not directory.resolve().is_relative_to(root):
            raise ValueError("Build output must remain inside this checkout")
        directory.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYINSTALLER_CONFIG_DIR"] = str(work / "cache")
    environment["CATALOGFLOW_BUILD_ROOT"] = str(root)
    environment["CATALOGFLOW_VERSION_RESOURCE"] = str(work / "version.txt")
    environment["CATALOGFLOW_LICENSE_BUNDLE"] = str(work / "THIRD_PARTY_LICENSES.txt")
    environment["PIP_CACHE_DIR"] = str(work / "pip-cache")
    environment["TEMP"] = str(work / "temp")
    environment["TMP"] = environment["TEMP"]
    Path(environment["TEMP"]).mkdir(exist_ok=True)
    build_environment = work / "venv"
    build_python = build_environment / "Scripts" / "python.exe"
    # Do not let another application's DLL directory leak into dependency discovery.
    windows = Path(os.environ["SystemRoot"])
    environment["PATH"] = os.pathsep.join(
        map(
            str,
            (
                build_environment / "Scripts",
                Path(sys.base_prefix),
                Path(sys.base_prefix) / "DLLs",
                windows / "System32",
                windows,
            ),
        )
    )
    if not build_python.exists():
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(build_environment)
    if not args.skip_install:
        run_build_command(
            [
                str(build_python),
                "-m",
                "pip",
                "--isolated",
                "--disable-pip-version-check",
                "install",
                "--cache-dir",
                str(work / "pip-cache"),
                "-r",
                str(root / "packaging" / "requirements-windows.txt"),
            ],
            root,
            environment,
        )
    if args.prepare_only:
        return 0
    if not (root / "src" / "catalogflow" / "desktop.py").is_file():
        raise ValueError("The desktop entry point must exist before building")
    source_hash = source_fingerprint(root)
    run_build_command(
        [
            str(build_python),
            "-m",
            "pip",
            "--isolated",
            "--disable-pip-version-check",
            "install",
            "--no-deps",
            "--no-build-isolation",
            "--force-reinstall",
            str(root),
        ],
        root,
        environment,
    )
    (work / "version.txt").write_text(version_resource(version), encoding="utf-8")
    run_build_command(
        [
            str(build_python),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(output),
            "--workpath",
            str(work / "pyinstaller"),
            str(root / "packaging" / "catalogflow.spec"),
        ],
        root,
        environment,
    )
    executable = output / "CatalogFlow.exe"
    smoke_report = work / "smoke-report.json"
    # Use a unique report path so an old successful smoke test cannot mask a failing build.
    smoke_report = smoke_report.with_stem("smoke-" + sha256_file(executable)[:16])
    if smoke_report.exists():
        smoke_report.unlink()
    result = subprocess.run(  # noqa: S603 - newly built local executable, bounded self-test only
        [str(executable), "--self-test", str(smoke_report)],
        cwd=work,
        env=environment,
        timeout=60,
        check=False,
    )
    smoke = json.loads(smoke_report.read_text(encoding="utf-8"))
    if result.returncode != 0 or smoke.get("ok") is not True:
        raise RuntimeError(
            "The frozen application self-test failed; no release archive was created"
        )
    if project_version(root) != version or source_fingerprint(root) != source_hash:
        raise RuntimeError("The project source changed during the build; rebuild before release")
    shutil.copyfile(work / "THIRD_PARTY_LICENSES.txt", output / "THIRD_PARTY_LICENSES.txt")
    archive = release_zip(root, executable, version, output)
    for artifact in (executable, archive):
        artifact.with_suffix(artifact.suffix + ".sha256").write_text(
            f"{sha256_file(artifact)}  {artifact.name}\n", encoding="ascii"
        )
    manifest = {
        "version": version,
        "platform": "windows-x64",
        "python": platform.python_version(),
        "artifacts": {path.name: sha256_file(path) for path in (executable, archive)},
        "frozen_self_test": True,
        "source_sha256": source_hash,
    }
    (output / "build-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
