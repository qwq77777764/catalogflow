# Windows desktop application

## Open CatalogFlow

Extract the release ZIP and double-click **CatalogFlow.exe**. The launcher opens the local
workbench in your default browser. Python, Git, and a terminal are not required on the computer
running the executable. Keep the launcher open while using the workbench; use **Open interface**
to reopen it and **Exit** to stop the local service. Closing only the browser page does not stop
the application.

CatalogFlow keeps its existing preview-first behavior. Starting the application does not contact
your suppliers or write products to a store. Creating a store draft remains an explicit operation;
permitted product writes use `draft` and `catalog_visibility=hidden`.

The desktop release includes the pricing workbench, CN / English (US) interface, editable freight
currency conversion, connection profiles, and saved work reports. Automatic reference exchange
rates require a network connection. Formula calculation and manually entered exchange rates can
be used offline. The existing command-line import interface is also available through executable
arguments; the desktop workbench does not yet replace every import command with a visual form.

## Your configuration and AI tools

Configuration and reports remain under `%APPDATA%\CatalogFlow`, independently of the EXE's
location. Existing `CATALOGFLOW_CONFIG_DIR` overrides remain supported. Moving or replacing the
EXE does not migrate or erase those files. Secrets stay in Windows Credential Manager for the
current Windows account; they are not included in the executable, ZIP, or work reports.

Codex CLI and Claude Code remain optional, separately installed tools. To use AI generation,
install and sign in to your chosen CLI on the same Windows account. The launcher does not bundle
their executables, copy login state from another computer, or include an AI subscription. An
installed CLI may send the authorized product facts and images to its provider.

If the desktop app cannot find an installed CLI, set its executable path in the AI connection
profile. An Explorer-launched application can have a different PATH from an already-open terminal.
A successful `--version` check confirms discovery, not that provider authentication or generation
has succeeded. Supplier and store integrations also need your own configured credentials.

## Build from public sources

Build on **Windows x64 with CPython 3.11 x64**, including Tcl/Tk. From the repository root:

```powershell
python packaging/build_windows.py
```

The script creates an isolated virtual environment under `build/windows/venv`, installs the pinned
PyInstaller, hooks, runtime keyring backend, and build tooling, then runs a frozen application
self-test. It does not use an existing global Python package collection as the bundle input.
Dependencies and temporary files stay under `build/windows`. No administrator privileges are
required. Run `--prepare-only` to install the build tools before the desktop source is ready;
`--skip-install` reuses those tools while still reinstalling the current CatalogFlow source.

Successful output is placed in `dist/windows`:

- `CatalogFlow.exe`
- `CatalogFlow-<version>-windows-x64.zip`, containing the EXE, licenses, and this guide
- `THIRD_PARTY_LICENSES.txt`, including CPython, OpenSSL's Apache license, Tcl/Tk and backend licenses
- SHA256 checksum files and `build-manifest.json`

Only explicitly listed dashboard JavaScript/HTML, the listing schema, the browser collector asset,
package metadata, and required dependency resources are bundled. The build sanitizes PATH and
rejects binary dependencies outside the isolated environment, CPython, and Windows directories.
Metadata collection excludes
pip's `direct_url.json`, which can contain a local build path. Configuration, work reports, supplier
responses, and login files are never release inputs. CPython and dependency licenses accompany
their bundled resources.

The executable uses PyInstaller's windowed single-file mode. It extracts its runtime to a temporary
directory on launch, so startup can take longer than running the Python source. Distribution and
testing do not require installing Python on the target computer. Build output is unsigned unless
the release publisher separately signs it; a published SHA256 checksum identifies the exact file
tested, but it is not a Windows code-signing certificate.

## Release acceptance

The build runs `CatalogFlow.exe --self-test <report.json>` with synthetic temporary configuration.
Do not publish an artifact whose self-test failed or whose source changed during the build. The
self-test complements manual checks on a second Windows computer:

1. Open the EXE from a path containing spaces and Chinese characters, without Python on PATH.
2. Check the browser opens, CN/EN switching, pricing formulas, manual currency conversion, and reports.
3. Close and reopen the page, start the EXE a second time, then exit and confirm the local service stops.
4. Use a dedicated synthetic Credential Manager item to verify save, restart, read, and cleanup.
5. Verify optional CLI discovery separately from an explicitly authorized real AI generation.

SSH checks can validate the executable and local HTTP service, but do not prove that the launcher
or browser appeared in the user's interactive Windows desktop session.
Windows Credential Manager can also reject SSH logon sessions with Windows error 1312.
Run the optional credential write/read/delete test from the signed-in interactive desktop;
a successful backend import in SSH does not establish that its vault is accessible.

Build implementation references:
[PyInstaller runtime paths](https://pyinstaller.org/en/stable/runtime-information.html),
[Windows no-console and external-program considerations](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html),
[PyInstaller installation and hook version pairing](https://pyinstaller.org/en/stable/installation.html).

## 中文使用说明

解压后双击 **CatalogFlow.exe**，程序会打开本机可视化界面；目标电脑不需要安装 Python。
启动器的“打开界面”用于重新打开网页，“退出”用于停止服务。只关闭网页不会退出程序。

配置和工作报告继续保存在 `%APPDATA%\CatalogFlow`，密钥保存在当前 Windows 用户的凭据管理器。
替换 EXE 不会清空这些数据，安装包也不包含他人的配置、报告或登录信息。

本地定价公式和手动汇率可以离线使用；拉取参考汇率需要联网。AI 生成功能仍需在当前电脑自行
安装并登录 Codex CLI 或 Claude Code，CJ 和店铺连接也需要自己的授权。打开程序本身不会执行刊登。
目前部分导入操作仍使用命令行参数，不能把这一版描述为已经完成全部商品导入的可视化操作。

开发者在带 Tcl/Tk 的 Windows x64 / Python 3.11 x64 环境执行
`python packaging/build_windows.py` 即可构建。请先通过自动自检和另一台电脑上的人工验收，
再发布 `dist/windows` 中的 EXE、ZIP 和 SHA256 文件。
