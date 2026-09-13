import base64
import json
import threading
import urllib.error
import urllib.request
from dataclasses import asdict

import pytest

from catalogflow import queue_workflow as workflow_module
from catalogflow.collector import pairing_code
from catalogflow.queue_workflow import QueueWorkflow, QueueWorkflowError
from catalogflow.selection_queue import SelectionQueue, normalize_selection


def selected(source="cj"):
    url = ("https://www.cjdropshipping.com/product/clock-p-123456789012.html?tracking=gone"
           if source == "cj" else "https://www.alibaba.com/product-detail/Clock_123456.html")
    return normalize_selection(source, url, "Synthetic Clock")


def decode_pairing(state):
    code = state["active"]["pairing_code"].split(":")[1]
    return json.loads(base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)))


def send(pairing, source="cj", *, token=None, origin=None, declared=None):
    item = selected(source)
    actual = origin or ("https://www.cjdropshipping.com" if source == "cj"
                        else "https://www.alibaba.com")
    data = {"version": 1, "source": source, "product_url": item.product_url,
            "page_title": item.page_title}
    request = urllib.request.Request(  # noqa: S310 - isolated loopback test
        pairing["endpoint"] + "/api/selections", data=json.dumps(data).encode(), method="POST",
        headers={"Content-Type": "application/json", "Origin": actual,
                 "X-CatalogFlow-Page-Origin": declared or actual,
                 "X-CatalogFlow-Token": pairing["token"] if token is None else token},
    )
    with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
        return json.load(response)


def test_embedded_collector_requires_pairing_freeze_and_never_imports_or_calls_ai(tmp_path):
    workflow = QueueWorkflow(tmp_path)
    try:
        state = workflow.start()
        pairing = decode_pairing(state)
        assert pairing["endpoint"] == state["active"]["endpoint"]
        result = send(pairing)
        assert result["created"]
        state = workflow.state()
        assert state["items"][0]["frozen"] is False
        assert state["items"][0]["importable"] is False
        with pytest.raises(QueueWorkflowError, match="queue_not_frozen"):
            workflow.select(result["id"])
        frozen = workflow.freeze()
        assert frozen["active"] is None
        assert frozen["items"][0]["importable"] is True
        assert workflow.select(result["id"])["url"].endswith("123456789012.html")
        assert not (tmp_path / "reports").exists()
        assert not (tmp_path / "import-history.sqlite3").exists()
        stored = next((tmp_path / "queues").glob("*.json")).read_text(encoding="utf-8")
        assert pairing["token"] not in stored and "CATALOGFLOW1:" not in stored
        with pytest.raises(urllib.error.URLError):
            send(pairing)
    finally:
        workflow.close()


def test_separate_collection_token_and_exact_origins(tmp_path):
    workflow = QueueWorkflow(tmp_path)
    try:
        pairing = decode_pairing(workflow.start())
        for kwargs in (
            {"token": "dashboard-token-is-not-collection-token"},
            {"origin": "https://untrusted.example"},
            {"origin": "https://www.alibaba.com", "declared": "https://www.cjdropshipping.com"},
        ):
            with pytest.raises(urllib.error.HTTPError) as error:
                send(pairing, **kwargs)
            assert error.value.code == 403
        assert workflow.state()["items"] == []
    finally:
        workflow.close()


def test_close_keeps_queue_unapproved_until_explicit_freeze_after_restart(tmp_path):
    first = QueueWorkflow(tmp_path)
    pairing = decode_pairing(first.start())
    item_id = send(pairing)["id"]
    queue_id = first.state()["active"]["queue_id"]
    first.close()
    with pytest.raises(QueueWorkflowError, match="queue_unavailable"):
        first.start()
    restored = QueueWorkflow(tmp_path)
    try:
        assert restored.state()["active"] is None
        with pytest.raises(QueueWorkflowError, match="queue_not_frozen"):
            restored.select(item_id)
        restored.freeze({"queue_id": queue_id})
        assert restored.select(item_id)["importable"]
        again = QueueWorkflow(tmp_path)
        assert again.select(item_id)["frozen"]
        again.close()
    finally:
        restored.close()


def test_explicit_legacy_file_import_is_frozen_but_alibaba_is_manual_only(tmp_path):
    workflow = QueueWorkflow(tmp_path)
    try:
        payload = {"version": 1, "items": [asdict(selected("alibaba")), asdict(selected())]}
        state = workflow.import_payload(payload)
        assert state["active"] is None
        assert len(state["items"]) == 2
        assert all(item["frozen"] for item in state["items"])
        alibaba = next(item for item in state["items"] if item["source"] == "alibaba")
        cj = next(item for item in state["items"] if item["source"] == "cj")
        assert workflow.select(alibaba["id"])["importable"] is False
        assert workflow.select(cj["id"])["importable"] is True
        assert alibaba["id"] != payload["items"][0]["id"]
    finally:
        workflow.close()


def test_legacy_archive_loaded_from_disk_is_not_implicitly_frozen(tmp_path):
    directory = tmp_path / "queues"
    directory.mkdir()
    path = directory / "selection-legacy.json"
    path.write_text(json.dumps({"version": 1, "items": [asdict(selected())]}), encoding="utf-8")
    workflow = QueueWorkflow(tmp_path)
    state = workflow.state()
    assert not state["items"][0]["frozen"]
    workflow.freeze({"queue_id": state["queues"][0]["id"]})
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2
    workflow.close()


@pytest.mark.parametrize("payload", [
    "C:/private/file.json", {"path": "C:/private/file.json"},
    {"version": True, "items": []}, {"version": 1, "items": [{}]},
    {"version": 1, "items": [], "token": "must-not-save"},
    {"version": 1, "items": [{**asdict(selected()), "cookie": "must-not-save"}]},
    {"version": 1, "items": [asdict(selected())] * 101},
    {"version": 1, "items": [{**asdict(selected()), "page_title": "x" * 50000}]},
])
def test_legacy_import_rejects_extra_data_paths_and_unbounded_files(tmp_path, payload):
    workflow = QueueWorkflow(tmp_path)
    with pytest.raises(QueueWorkflowError, match="queue_invalid_request"):
        workflow.import_payload(payload)
    assert workflow.state()["items"] == []
    assert not (tmp_path / "queues").exists()
    workflow.close()


def test_corrupt_or_oversized_archives_are_not_loaded_or_echoed(tmp_path):
    directory = tmp_path / "queues"
    directory.mkdir()
    (directory / "selection-corrupt.json").write_text("private-secret", encoding="utf-8")
    (directory / "selection-large.json").write_bytes(b"x" * (512 * 1024 + 1))
    workflow = QueueWorkflow(tmp_path)
    state = workflow.state()
    assert state["items"] == [] and state["warnings"] == ["queue_invalid_archive"]
    assert "private-secret" not in json.dumps(state)
    workflow.close()


def test_archive_file_count_is_bounded_and_prevents_new_sessions(tmp_path, monkeypatch):
    directory = tmp_path / "queues"
    directory.mkdir()
    for index in range(4):
        (directory / f"selection-{index}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(workflow_module, "MAX_QUEUE_FILES", 3)
    workflow = QueueWorkflow(tmp_path)
    assert "queue_archive_limit" in workflow.state()["warnings"]
    with pytest.raises(QueueWorkflowError, match="queue_archive_limit"):
        workflow.start()
    workflow.close()


def test_symlink_queue_file_is_not_read(tmp_path):
    directory = tmp_path / "queues"
    directory.mkdir()
    target = tmp_path / "private.json"
    target.write_text("private-secret", encoding="utf-8")
    try:
        (directory / "selection-link.json").symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable for this account")
    workflow = QueueWorkflow(tmp_path)
    assert workflow.state()["warnings"] == ["queue_invalid_archive"]
    workflow.close()


def test_add_and_freeze_share_one_atomic_boundary(tmp_path):
    queue = SelectionQueue(tmp_path / "queue.json")
    queue.add(selected())
    queue.freeze()
    errors = []

    def add():
        try:
            queue.add(selected("alibaba"))
        except ValueError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=add) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == ["queue_frozen"] * 4
    assert len(SelectionQueue(queue.path).list()) == 1


def test_pairing_code_contains_only_endpoint_and_collection_token():
    code = pairing_code("http://127.0.0.1:45678", "synthetic-token-012345678901234567890")
    state = {"active": {"pairing_code": code}}
    assert set(decode_pairing(state)) == {"endpoint", "token"}
