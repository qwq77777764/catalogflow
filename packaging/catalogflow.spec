# PyInstaller spec: execute only in the isolated Windows build environment.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

sys.path.insert(0, str(Path(SPECPATH)))
from build_windows import metadata_files, public_assets

root = Path(os.environ["CATALOGFLOW_BUILD_ROOT"])
datas = public_assets(root)
for package in (
    "catalogflow", "keyring", "jaraco.classes", "jaraco.context", "jaraco.functools",
    "more-itertools", "pywin32-ctypes", "backports.tarfile", "importlib_metadata", "zipp",
):
    datas.extend(metadata_files(package))
datas.extend(
    (source, destination) for source, destination in metadata_files("pyinstaller")
    if Path(source).name == "COPYING.txt"
)
# CPython's redistribution license accompanies its interpreter inside the executable.
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if not python_license.is_file():
    raise RuntimeError("The CPython redistribution license was not found")
datas.append((str(python_license), "third_party_licenses/python"))
hiddenimports = [
    "tkinter", "tkinter.ttk", "tkinter.messagebox",
    "keyring.backends.Windows", "keyring.backends.chainer", "keyring.backends.fail",
    "keyring.backends.null", "win32ctypes.pywin32", "win32ctypes.pywin32.win32cred",
    "win32ctypes.pywin32.pywintypes",
]
hiddenimports += collect_submodules("win32ctypes.core.ctypes")
a = Analysis(
    [str(root / "packaging" / "desktop_entry.py")],
    pathex=[str(root / "src")],
    binaries=[], datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["pytest", "ruff", "keyrings.alt"],
    noarchive=False,
)
allowed_binary_roots = (
    Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(),
    Path(os.environ["SystemRoot"]).resolve(),
)
for name, source, _kind in a.binaries:
    if not any(Path(source).resolve().is_relative_to(parent) for parent in allowed_binary_roots):
        raise RuntimeError(f"Unapproved binary source for {name}")
license_parts = [(root / "packaging" / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")]
for name, source, _kind in sorted(a.datas):
    if Path(name).name.lower().startswith(("license", "copying")):
        if not any(Path(source).resolve().is_relative_to(parent) for parent in allowed_binary_roots):
            raise RuntimeError(f"Unapproved license source for {name}")
        license_parts.append(f"\n\n{'=' * 72}\n{name}\n{'=' * 72}\n")
        license_parts.append(Path(source).read_text(encoding="utf-8", errors="replace"))
license_output = Path(os.environ["CATALOGFLOW_LICENSE_BUNDLE"])
if not license_output.resolve().is_relative_to((root / "build").resolve()):
    raise RuntimeError("The license bundle must remain inside the build directory")
license_output.write_text("\n".join(license_parts), encoding="utf-8")
a.datas.append(("THIRD_PARTY_LICENSES.txt", str(license_output), "DATA"))
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="CatalogFlow", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=True,
    version=os.environ["CATALOGFLOW_VERSION_RESOURCE"],
    uac_admin=False,
)
