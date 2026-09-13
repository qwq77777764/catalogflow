# Windows desktop application

## Open CatalogFlow

Extract the release ZIP and double-click **CatalogFlow.exe**. The launcher opens the local
workbench in your default browser. Python, Git, and a terminal are not required on the computer
running the executable. Keep the launcher open while using the workbench; use **Open interface**
to reopen it and **Exit** to stop the local service. Closing only the browser page does not stop
the application. Exit refuses to stop an active AI check, test, preview or draft write; wait for the task to finish.

CatalogFlow keeps its existing preview-first behavior. Starting the application does not contact
your suppliers or write products to a store. Creating a store draft remains an explicit operation;
permitted product writes use `draft` and `catalog_visibility=hidden`.

The desktop release includes the single-product import wizard, pricing workbench, CN / English (US)
interface, editable freight currency conversion, connection profiles, and saved work reports. Automatic reference exchange
rates require a network connection. Formula calculation and manually entered exchange rates can
be used offline. The existing command-line import interface is also available through executable
arguments.

## Import and review one product

In v0.10, start with **Get started** to check the chosen CLI and its sign-in status, follow official
installation/sign-in guidance, or explicitly test a small synthetic AI request (which can consume
usage). Browser-selected CJ and Alibaba links enter **Collected products**; confirm collection
before choosing one. Alibaba selections use a manual facts/variants/cost/freight form, without
requiring JSON authoring. No store is required to try the software. See the
[first-run walkthrough](https://github.com/qwq77777764/catalogflow/blob/main/docs/first-run.md).

Save your connection profiles and pricing settings in the workbench, then use its import wizard:

1. Select one CJ URL/PID and a saved CJ API profile, or fill in the manual product form with
   authorized facts, variants, costs, freight and images. The advanced JSON upload remains available
   (`alibaba-manual`, UTF-8 with optional BOM, maximum 48 KiB). Choose Codex, Claude, or template
   generation. Select a saved WooCommerce profile now if you want to create a draft after review;
   a store is not required for a preview.
2. Generate and review the product. The panel shows each variant's cost, freight, and USD selling
   price, plus source/image links and image counts. You can edit the title, description HTML as
   text, category, and tags. Prices use the saved settings captured for this preview.
3. Check the review acknowledgment and click the hidden-draft action. Confirmation reuses the
   reviewed snapshot without rerunning CJ, AI, or pricing. Store writes stay `draft + hidden` and
   use the existing report archive and duplicate guards. Image uploads additionally need the
   WordPress application-password fields in the selected WooCommerce profile.

One import task runs at a time. **Open interface** can recover the current task while the same
application is running. The token is removed from the page address after loading, so ordinary F5
on that address is not a reliable recovery method. Restarting the application loses unconfirmed
previews held in memory, while written reports remain. Review recovered content again; unsaved
browser edits are not a persistent record.

This wizard handles one CJ API product or one manual product from its form/advanced JSON. It does not automatically normalize
an Alibaba/1688 web URL, process a batch, write through SSH, or migrate old private reports. See the
[visual import guide](https://github.com/qwq77777764/catalogflow/blob/main/docs/visual-import.md)
for input and review details.

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
   Generate an authorized synthetic JSON preview with the template generator, inspect its variants,
   and verify that a preview without a store cannot create a draft.
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
AI 检查、小型测试、预览或草稿写入执行中，退出操作会要求先等待任务完成。

配置和工作报告继续保存在 `%APPDATA%\CatalogFlow`，密钥保存在当前 Windows 用户的凭据管理器。
替换 EXE 不会清空这些数据，安装包也不包含他人的配置、报告或登录信息。

本地定价公式和手动汇率可以离线使用；拉取参考汇率需要联网。AI 生成功能仍需在当前电脑自行
安装并登录 Codex CLI 或 Claude Code，CJ 和店铺连接也需要自己的授权。打开程序本身不会执行刊登。

单商品导入现在可直接在界面中完成：

1. 先保存所需连接和定价，再选择 CJ 链接/PID 与 CJ 档案，或直接填写已获授权的商品资料表单。
   高级入口仍可上传规范化 JSON（`alibaba-manual`，UTF-8，可带 BOM，最多 48 KiB）。
   选择 Codex、Claude 或模板生成。
   只做预览可不选店铺；如需随后创建草稿，应在生成预览前选定 WooCommerce 档案。
2. 核对每个变体的成本、运费、USD 售价、原链接、图片数量及链接，并编辑标题、HTML 描述文本、
   分类和标签。售价来自开始预览时已保存的定价设置。
3. 勾选已完成审核，再点击创建隐藏草稿。确认沿用已审核快照，不重复调用 CJ、AI 或重新定价；
   结果仍写入工作报告并受原有防重复机制保护。需要上传图片时，WooCommerce 档案还须填写
   WordPress 用户名及应用程序密码。

同一会话一次处理一个导入任务。程序仍运行时，通过启动器“打开界面”可恢复当前任务；普通 F5
刷新后的地址可能已无认证信息。重启程序会丢失未确认的内存预览，但已写入报告仍保留；网页内
未提交的修改也不是持久化记录，重新打开后须再次检查。Alibaba/1688 网页链接自动归一化、批量
导入、SSH 写店铺与旧私人报告迁移仍未实现，命令行接口继续保留。

开发者在带 Tcl/Tk 的 Windows x64 / Python 3.11 x64 环境执行
`python packaging/build_windows.py` 即可构建。请先通过自动自检和另一台电脑上的人工验收，
再发布 `dist/windows` 中的 EXE、ZIP 和 SHA256 文件。
