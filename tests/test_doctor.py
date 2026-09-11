from catalogflow import doctor


def test_doctor_does_not_require_an_ai_request(monkeypatch) -> None:
    monkeypatch.setattr(doctor, "find_cli", lambda *_args: None)

    report = doctor.doctor_report()

    assert report["ok"] is True
    assert "does not make an AI request" in report["note"]
    assert [item["provider"] for item in report["providers"]] == ["codex", "claude"]
    assert all(item["installed"] is False for item in report["providers"])
