"""Durable local run reports and fail-closed hidden-draft reservations.

Every run and item file is created once. Interrupted work can be reconstructed
from those records; SQLite reservations are never automatically retried.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .configuration import default_config_directory

_RUN_ID = re.compile(r"\d{8}T\d{12}Z-[a-f0-9]{32}")
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_ITEMS = 1000
_ERROR_LABELS = {
    "configuration_failed": "连接或配置初始化失败 / Connection or settings setup failed",
    "saved_pricing_invalid": "保存的定价设置无效 / Saved pricing settings are invalid",
    "review_required": "需核对已有草稿后处理 / Reconcile the previous attempt before retrying",
    "woocommerce_invalid_response": "店铺响应无效 / Invalid store response",
    "woocommerce_request_failed": "店铺请求失败 / Store request failed",
    "woocommerce_existing_product": (
        "店铺已有对应商品，需核对 / Existing store product needs review"
    ),
    "woocommerce_ambiguous_term": "店铺分类或标签存在歧义 / Ambiguous category or tag",
    "woocommerce_term_search_limit": "分类标签查询超限 / Category or tag search limit reached",
    "woocommerce_draft_state_unconfirmed": "无法确认隐藏草稿状态 / Hidden draft state unconfirmed",
    "woocommerce_image_limit": "图片数量超限 / Image count limit reached",
    "wordpress_media_credentials_required": (
        "需要配置图片上传凭据 / Media upload credentials required"
    ),
    "woocommerce_image_download_failed": "授权图片读取失败 / Authorized image download failed",
    "woocommerce_draft_failed": "创建草稿失败 / Draft creation failed",
    "woocommerce_variant_limit": "变体数量超限 / Variant count limit reached",
    "woocommerce_invalid_variants": "商品变体无效 / Invalid product variants",
    "woocommerce_invalid_prices": "商品价格无效 / Invalid product prices",
    "woocommerce_invalid_terms": "分类或标签无效 / Invalid category or tags",
}
_STATUS_LABELS = {
    "running": "未完成 / Unfinished", "completed": "运行结束 / Run completed",
    "interrupted": "尚未完成，结果待确认 / Unfinished; result unconfirmed",
    "previewed": "本地预览成功 / Local preview created",
    "drafted": "隐藏草稿成功 / Hidden draft created",
    "skipped_duplicate": "已存在，跳过 / Existing draft skipped",
    "blocked_incomplete": "上次结果未确认，已阻止重试 / Previous attempt needs reconciliation",
    "failed": "失败 / Failed", "rejected": "校验未通过 / Validation rejected",
}


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def validate_run_id(value: str) -> str:
    if not isinstance(value, str) or not _RUN_ID.fullmatch(value):
        raise ValueError("Invalid report identifier")
    return value


def clean_text(value: object, limit: int = 300) -> str:
    """Keep bounded single-line text; never interpret it as HTML."""
    return " ".join(str(value or "").split())[:limit]


def canonical_url(value: object, *, store: bool = False) -> str:
    """Strip session parameters and reject non-public URL forms without fetching."""
    if not isinstance(value, str) or len(value) > 4096:
        return ""
    try:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
        if parts.scheme not in {"http", "https"} or not host:
            return ""
        if parts.username is not None or parts.password is not None:
            return ""
        if any(ord(character) < 33 for character in value):
            return ""
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if (
                "." not in host or host.endswith((".localhost", ".local", ".internal"))
                or not re.fullmatch(r"[a-z0-9.-]+", host)
                or not re.fullmatch(r"[a-z]{2,63}", host.rsplit(".", 1)[-1])
            ):
                return ""
        else:
            if not address.is_global:
                return ""
        netloc = f"[{host}]" if ":" in host else host
        if port is not None and port != (443 if parts.scheme == "https" else 80):
            netloc += f":{port}"
        query = ""
        if host == "cjdropshipping.com" or host.endswith(".cjdropshipping.com"):
            values = parse_qs(parts.query, max_num_fields=50)
            for name in ("pid", "productId", "product_id"):
                candidate = values.get(name, [""])[0]
                if re.fullmatch(
                    r"(?:\d{10,30}|[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})",
                    candidate,
                ):
                    query = f"{name}={candidate}"
                    break
        if store and parts.path.endswith("/wp-admin/post.php"):
            values = parse_qs(parts.query)
            post = values.get("post", [""])[0]
            if re.fullmatch(r"[0-9]{1,20}", post):
                query = f"post={post}&action=edit"
        return urlunsplit((parts.scheme, netloc, parts.path or "/", query, ""))
    except ValueError:
        return ""


def safe_error(exc: BaseException) -> str:
    """Exception messages may contain credentials, responses or local paths."""
    names = {
        "ValueError", "TypeError", "KeyError", "OSError", "PermissionError",
        "FileNotFoundError", "TimeoutError", "ConnectionError", "RuntimeError",
        "CjApiError", "WooCommerceDraftError", "CostFormulaError",
        "JSONDecodeError", "UnicodeDecodeError",
    }
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code in _ERROR_LABELS:
        return code
    name = type(exc).__name__
    return name if name in names else "operation_failed"


def _write_once(path: Path, value: dict[str, Any] | str) -> None:
    data = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    encoded = data.encode("utf-8")
    if len(encoded) > _MAX_FILE_BYTES:
        raise ValueError("Report file exceeds the size limit")
    temporary = path.with_name(f".{path.name}-{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic and exclusive on NTFS/POSIX: a crash cannot expose half a JSON record.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path, *, directory: Path) -> dict[str, Any]:
    if path.resolve().parent != directory.resolve():
        raise RuntimeError("Report file is outside its run directory")
    with path.open("rb") as stream:
        data = stream.read(_MAX_FILE_BYTES + 1)
    if len(data) > _MAX_FILE_BYTES:
        raise RuntimeError("Report file exceeds the size limit")
    try:
        document = json.loads(data)
    except (ValueError, UnicodeError):
        raise RuntimeError("Report file is invalid") from None
    if not isinstance(document, dict):
        raise RuntimeError("Report file is invalid")
    return document


def _check_item(item: dict[str, Any], index: int) -> None:
    text_fields = ("started_at", "finished_at", "source", "source_id", "source_url",
                   "title", "status", "store_url", "artifact_path")
    if item.get("index") != index or any(
        not isinstance(item.get(key), str) or len(item[key]) > 4096 for key in text_fields
    ):
        raise RuntimeError("Report item is invalid")
    if item["status"] not in {
        "started", "previewed", "drafted", "skipped_duplicate", "blocked_incomplete",
        "failed", "rejected", "interrupted",
    }:
        raise RuntimeError("Report item status is invalid")
    errors = item.get("errors")
    if not isinstance(errors, list) or len(errors) > 30 or any(
        not isinstance(value, str) or len(value) > 500 for value in errors
    ):
        raise RuntimeError("Report item errors are invalid")
    if item.get("store_id") is not None and not isinstance(item["store_id"], str):
        raise RuntimeError("Report store identifier is invalid")


@dataclass(frozen=True)
class Reservation:
    status: str
    store_id: str | None = None
    store_url: str = ""


class HistoryRepository:
    """directory is the config root, with lazy reports/ and SQLite creation."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self.config_directory = Path(directory) if directory else default_config_directory()
        self.directory = self.config_directory / "reports"
        self.registry_path = self.config_directory / "import-history.sqlite3"

    def _run_directory(self, run_id: str) -> Path:
        path = self.directory / validate_run_id(run_id)
        if path.resolve().parent != self.directory.resolve():
            raise ValueError("Invalid report directory")
        return path

    def create_run(self, mode: str) -> RunRecord:
        if mode not in {"dry-run", "draft"}:
            raise ValueError("Invalid import mode")
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ-") + uuid.uuid4().hex
        directory = self._run_directory(run_id)
        directory.mkdir(parents=True, exist_ok=False)
        _write_once(directory / "start.json", {
            "version": 1, "run_id": run_id, "mode": mode, "started_at": timestamp(),
        })
        return RunRecord(self, run_id)

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Report limit must be between 1 and 100")
        if not self.directory.exists():
            return []
        identifiers = sorted(
            (p.name for p in self.directory.iterdir() if _RUN_ID.fullmatch(p.name)),
            reverse=True,
        )
        result = []
        for identifier in identifiers:
            try:
                document = self.read(identifier)
            except (FileNotFoundError, ValueError, RuntimeError):
                continue
            summary = {key: value for key, value in document.items() if key != "items"}
            summary["item_count"] = len(document["items"])
            result.append(summary)
            if len(result) == limit:
                break
        return result

    def read(self, run_id: str) -> dict[str, Any]:
        directory = self._run_directory(run_id)
        start = _read_json(directory / "start.json", directory=directory)
        if (
            start.get("version") != 1 or start.get("run_id") != run_id
            or start.get("mode") not in {"dry-run", "draft"}
            or not isinstance(start.get("started_at"), str)
        ):
            raise RuntimeError("Report header is invalid")
        items = []
        item_paths = sorted(directory.glob("item-*.start.json"))
        if len(item_paths) > _MAX_ITEMS:
            raise RuntimeError("Report item limit exceeded")
        for item_path in item_paths:
            if not re.fullmatch(r"item-\d{6}\.start\.json", item_path.name):
                raise RuntimeError("Report item filename is invalid")
            index = int(item_path.name[5:11])
            item = _read_json(item_path, directory=directory)
            provenance = item_path.with_name(item_path.name.replace(".start", ".product"))
            if provenance.exists():
                item = _read_json(provenance, directory=directory)
            final_path = item_path.with_name(item_path.name.replace(".start.json", ".json"))
            if final_path.exists():
                item = _read_json(final_path, directory=directory)
            else:
                item.update(status="interrupted", finished_at="", errors=["review_required"])
                artifact = directory / f"item-{index:06d}-preview.json"
                if artifact.exists() and artifact.resolve().parent == directory.resolve():
                    item["artifact_path"] = str(artifact)
            _check_item(item, index)
            items.append(item)
        finish_path = directory / "finish.json"
        finish = _read_json(finish_path, directory=directory) if finish_path.exists() else {}
        if finish and (finish.get("status") not in {"completed", "interrupted"}
                       or not isinstance(finish.get("finished_at"), str)):
            raise RuntimeError("Report completion is invalid")
        result = {
            **start, "status": finish.get("status", "running"),
            "finished_at": finish.get("finished_at", ""), "items": items,
            "counts": dict(Counter(item["status"] for item in items)),
            "report_path": str(directory / "report.txt"),
        }
        if len(json.dumps(result, ensure_ascii=False).encode()) > _MAX_FILE_BYTES:
            raise RuntimeError("Report exceeds the size limit")
        return result

    def report_text(self, run_id: str) -> str:
        # Render structured durable records, never serve arbitrary filesystem content.
        return render_report(self.read(run_id))

    def _connection(self) -> sqlite3.Connection:
        self.config_directory.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.registry_path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS drafts ("
            "identity TEXT NOT NULL, source TEXT NOT NULL, source_id TEXT NOT NULL, "
            "state TEXT NOT NULL, run_id TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "store_id TEXT, store_url TEXT NOT NULL DEFAULT '', "
            "PRIMARY KEY(identity, source, source_id))"
        )
        return connection

    @staticmethod
    def _key(store_identity: str, source: str, source_id: str) -> tuple[str, str, str]:
        if not all(isinstance(value, str) and value.strip()
                   for value in (store_identity, source, source_id)):
            raise ValueError("Draft history requires store and source identities")
        return hashlib.sha256(store_identity.encode()).hexdigest(), source, source_id

    def reserve(self, store_identity: str, source: str, source_id: str,
                run_id: str) -> Reservation:
        key = self._key(store_identity, source, source_id)
        validate_run_id(run_id)
        connection = None
        try:
            connection = self._connection()
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT state, store_id, store_url FROM drafts "
                "WHERE identity=? AND source=? AND source_id=?", key,
            ).fetchone()
            if existing:
                connection.commit()
                return Reservation(
                    "duplicate" if existing[0] == "completed" else "blocked",
                    existing[1], existing[2],
                )
            connection.execute(
                "INSERT INTO drafts(identity,source,source_id,state,run_id,updated_at) "
                "VALUES(?,?,?,'reserved',?,?)", (*key, run_id, timestamp()),
            )
            connection.commit()
            return Reservation("reserved")
        except sqlite3.Error:
            raise RuntimeError("Draft history is unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    def lookup(self, store_identity: str, source: str, source_id: str) -> Reservation | None:
        """Check known work before spending AI usage; reserve still arbitrates later races."""
        key = self._key(store_identity, source, source_id)
        if not self.registry_path.exists():
            return None
        connection = None
        try:
            connection = sqlite3.connect(
                self.registry_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10,
            )
            existing = connection.execute(
                "SELECT state,store_id,store_url FROM drafts "
                "WHERE identity=? AND source=? AND source_id=?", key,
            ).fetchone()
            if existing:
                return Reservation(
                    "duplicate" if existing[0] == "completed" else "blocked",
                    existing[1], existing[2],
                )
            return None
        except sqlite3.Error:
            raise RuntimeError("Draft history is unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    def record_draft(self, store_identity: str, source: str, source_id: str,
                     run_id: str, *, completed: bool, store_id: str | None = None,
                     store_url: str = "") -> None:
        key = self._key(store_identity, source, source_id)
        connection = None
        try:
            connection = self._connection()
            cursor = connection.execute(
                "UPDATE drafts SET state=?, updated_at=?, store_id=?, store_url=? "
                "WHERE identity=? AND source=? AND source_id=? AND run_id=? AND state='reserved'",
                ("completed" if completed else "uncertain", timestamp(),
                 clean_text(store_id, 100) or None, canonical_url(store_url, store=True),
                 *key, validate_run_id(run_id)),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Draft reservation is no longer owned by this run")
        except sqlite3.Error:
            raise RuntimeError("Draft history is unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    def release_unwritten(self, store_identity: str, source: str, source_id: str,
                          run_id: str) -> None:
        """Only call when the known exporter explicitly guarantees no write started."""
        connection = None
        try:
            connection = self._connection()
            connection.execute(
                "DELETE FROM drafts WHERE identity=? AND source=? AND source_id=? "
                "AND run_id=? AND state='reserved' AND store_id IS NULL",
                (*self._key(store_identity, source, source_id), validate_run_id(run_id)),
            )
        except sqlite3.Error:
            raise RuntimeError("Draft history is unavailable") from None
        finally:
            if connection is not None:
                connection.close()


class RunRecord:
    def __init__(self, repository: HistoryRepository, run_id: str) -> None:
        self.repository = repository
        self.run_id = run_id
        self.directory = repository._run_directory(run_id)
        self._next_index = 1

    def start_item(self, *, source: str, source_url: str = "") -> dict[str, Any]:
        if self._next_index > _MAX_ITEMS:
            raise ValueError("A run supports at most 1000 items")
        item = {
            "index": self._next_index, "started_at": timestamp(), "finished_at": "",
            "source": clean_text(source, 50), "source_id": "",
            "source_url": canonical_url(source_url), "title": "", "status": "started",
            "errors": [], "store_id": None, "store_url": "", "artifact_path": "",
        }
        _write_once(self.directory / f"item-{self._next_index:06d}.start.json", item)
        self._next_index += 1
        return item

    def record_product(self, item: dict[str, Any]) -> None:
        _check_item(item, item["index"])
        _write_once(self.directory / f"item-{item['index']:06d}.product.json", item)

    def write_artifact(self, index: int, payload: dict[str, Any]) -> str:
        path = self.directory / f"item-{index:06d}-preview.json"
        _write_once(path, payload)
        return str(path)

    def finish_item(self, item: dict[str, Any]) -> None:
        item = {**item, "finished_at": timestamp()}
        _check_item(item, item["index"])
        _write_once(self.directory / f"item-{int(item['index']):06d}.json", item)

    def finish(self, *, interrupted: bool = False) -> None:
        _write_once(self.directory / "finish.json", {
            "finished_at": timestamp(), "status": "interrupted" if interrupted else "completed",
        })
        report = self.repository.read(self.run_id)
        _write_once(self.directory / "report.json", report)
        _write_once(self.directory / "report.txt", render_report(report))


def render_report(report: dict[str, Any]) -> str:
    counts = report["counts"]
    mode_label = ("本地预览（没有店铺写入） / Local preview (no store write)"
                  if report["mode"] == "dry-run" else "隐藏草稿 / Hidden drafts")
    status_label = _STATUS_LABELS.get(report["status"], report["status"])
    lines = [
        "CatalogFlow 工作记录 / Run report", f"运行编号 / Run: {report['run_id']}",
        f"模式 / Mode: {mode_label}", f"开始 / Started: {report['started_at']}",
        f"结束 / Finished: {report['finished_at'] or '-'}",
        f"状态 / Status: {status_label}",
        f"总数 / Total: {len(report['items'])}; "
        f"预览 / Preview: {counts.get('previewed', 0)}; "
        f"草稿 / Drafted: {counts.get('drafted', 0)}; "
        f"失败 / Failed: {counts.get('failed', 0) + counts.get('rejected', 0)}; "
        f"跳过 / Skipped: {counts.get('skipped_duplicate', 0)}; "
        f"待核对 / Review: {counts.get('blocked_incomplete', 0) + counts.get('interrupted', 0)}",
        "",
    ]
    for item in report["items"]:
        lines += [
            f"[{item['index']}] {_STATUS_LABELS.get(item['status'], item['status'])} "
            f"({item['status']})",
            f"开始 / Started: {item['started_at']}",
            f"结束 / Finished: {item['finished_at'] or '-'}",
            f"来源 / Source: {item['source']} / {item['source_id']}",
            f"原链接 / Source URL: {item['source_url'] or '-'}",
            f"标题 / Title: {item['title'] or '-'}",
            "原因 / Errors: " + ("; ".join(_ERROR_LABELS.get(error, error)
                                          for error in item["errors"]) or "-"),
            f"店铺商品 ID / Store ID: {item['store_id'] or '-'}",
            f"店铺链接 / Store URL: {item['store_url'] or '-'}",
            f"本地预览 / Preview file: {item['artifact_path'] or '-'}", "",
        ]
    return "\n".join(lines) + "\n"
