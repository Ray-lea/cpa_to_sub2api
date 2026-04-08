from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.converter import (
    ConversionError,
    ExportSettings,
    ProxyConfig,
    export_records,
    export_to_file,
    generate_default_filename,
    load_source_record,
    merge_source_records,
)


def fake_jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


def build_source(
    email: str = "user@example.com",
    *,
    access_auth: dict | None = None,
    id_auth: dict | None = None,
    extra: dict | None = None,
) -> dict:
    access_payload = {
        "client_id": "app_client",
        "https://api.openai.com/profile": {"email": email},
        "https://api.openai.com/auth": access_auth
        or {
            "chatgpt_account_id": "jwt-account",
            "chatgpt_user_id": "jwt-user",
            "chatgpt_plan_type": "free",
        },
    }
    id_payload = {
        "email": email,
        "aud": ["app_from_id_token"],
        "https://api.openai.com/auth": id_auth
        or {
            "chatgpt_account_id": "id-account",
            "chatgpt_user_id": "id-user",
            "chatgpt_plan_type": "plus",
            "chatgpt_subscription_active_until": "2026-05-01T22:09:36+08:00",
            "organizations": [
                {"id": "org-first", "is_default": False},
                {"id": "org-default", "is_default": True},
            ],
        },
    }
    payload = {
        "access_token": fake_jwt(access_payload),
        "account_id": "source-account-id",
        "disabled": False,
        "email": email,
        "expired": "2026-04-18T12:20:50+08:00",
        "id_token": fake_jwt(id_payload),
        "last_refresh": "2026-04-08T12:20:50+08:00",
        "refresh_token": "refresh-token",
        "type": "codex",
    }
    if extra:
        payload.update(extra)
    return payload


@pytest.mark.parametrize(
    ("extra", "variant"),
    [
        ({"device_id": "device-1"}, "含 device_id"),
        (
            {
                "chatgpt_account_id": "preferred-account",
                "chatgpt_user_id": "preferred-user",
                "session_token": "",
            },
            "含 ChatGPT 标识",
        ),
        ({"note": "个人", "websockets": False}, "含 note/websockets"),
    ],
)
def test_load_source_record_supports_all_variants(tmp_path: Path, extra: dict, variant: str) -> None:
    source_path = tmp_path / "sample.json"
    source_path.write_text(json.dumps(build_source(extra=extra)), encoding="utf-8")

    record = load_source_record(source_path)

    assert record.is_valid is True
    assert record.selected is True
    assert record.variant == variant
    assert record.email == "user@example.com"
    assert record.target_name == "user"


def test_load_source_record_enriches_credentials_from_jwt(tmp_path: Path) -> None:
    source_path = tmp_path / "plus.json"
    source = build_source(
        email="plus@example.com",
        extra={"note": "个人", "chatgpt_account_id": "preferred-account"},
    )
    source_path.write_text(json.dumps(source), encoding="utf-8")

    record = load_source_record(source_path)
    payload = export_records([record], ExportSettings(output_filename="out.json")).to_dict()
    account = payload["accounts"][0]
    credentials = account["credentials"]

    assert account["name"] == "plus"
    assert account["notes"] == "个人"
    assert credentials["chatgpt_account_id"] == "preferred-account"
    assert credentials["chatgpt_user_id"] == "jwt-user"
    assert credentials["client_id"] == "app_client"
    assert credentials["organization_id"] == "org-default"
    assert credentials["plan_type"] == "free"
    assert credentials["subscription_expires_at"] == "2026-05-01T22:09:36+08:00"
    assert credentials["expires_at"] == "2026-04-18T12:20:50+08:00"


def test_duplicate_target_names_are_suffixed(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps(build_source(email="same@example.com")), encoding="utf-8")
    second.write_text(json.dumps(build_source(email="same@other.com")), encoding="utf-8")

    records = merge_source_records([], [first, second])

    assert [record.target_name for record in records] == ["same", "same-2"]


def test_export_records_without_proxy_omits_proxy_key(tmp_path: Path) -> None:
    source_path = tmp_path / "sample.json"
    source_path.write_text(json.dumps(build_source()), encoding="utf-8")
    record = load_source_record(source_path)

    payload = export_records(
        [record],
        ExportSettings(output_filename="accounts.json"),
        exported_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    ).to_dict()

    assert set(payload.keys()) == {"exported_at", "proxies", "accounts"}
    assert payload["proxies"] == []
    assert "proxy_key" not in payload["accounts"][0]
    assert "extra" not in payload["accounts"][0]
    assert "privacy_mode" not in payload["accounts"][0]["credentials"]
    assert "model_mapping" not in payload["accounts"][0]["credentials"]


def test_export_records_with_proxy_includes_proxy_block(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps(build_source(email="a@example.com")), encoding="utf-8")
    second.write_text(json.dumps(build_source(email="b@example.com")), encoding="utf-8")
    records = merge_source_records([], [first, second])
    settings = ExportSettings(
        output_filename="accounts.json",
        proxy=ProxyConfig(
            enabled=True,
            name="测试代理",
            protocol="http",
            host="127.0.0.1",
            port=7890,
        ),
    )

    payload = export_records(records, settings).to_dict()

    assert payload["proxies"] == [
        {
            "proxy_key": "http|127.0.0.1|7890||",
            "name": "测试代理",
            "protocol": "http",
            "host": "127.0.0.1",
            "port": 7890,
            "status": "active",
        }
    ]
    assert payload["accounts"][0]["proxy_key"] == "http|127.0.0.1|7890||"
    assert payload["accounts"][1]["proxy_key"] == "http|127.0.0.1|7890||"


def test_export_to_file_writes_json(tmp_path: Path) -> None:
    source_path = tmp_path / "sample.json"
    source_path.write_text(json.dumps(build_source()), encoding="utf-8")
    record = load_source_record(source_path)
    output_dir = tmp_path / "output"

    output_path = export_to_file(
        [record],
        ExportSettings(output_filename=generate_default_filename()),
        output_dir,
        exported_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
    )

    exported = json.loads(output_path.read_text(encoding="utf-8"))
    assert exported["accounts"][0]["name"] == "user"


def test_invalid_json_is_marked_invalid(tmp_path: Path) -> None:
    source_path = tmp_path / "bad.json"
    source_path.write_text("{bad json", encoding="utf-8")

    record = load_source_record(source_path)

    assert record.is_valid is False
    assert record.selected is False
    assert record.status_text == "JSON 解析失败"


def test_missing_required_field_is_invalid(tmp_path: Path) -> None:
    source_path = tmp_path / "missing.json"
    broken = build_source()
    broken.pop("refresh_token")
    source_path.write_text(json.dumps(broken), encoding="utf-8")

    record = load_source_record(source_path)

    assert record.is_valid is False
    assert "refresh_token" in record.status_text


def test_invalid_time_is_invalid(tmp_path: Path) -> None:
    source_path = tmp_path / "time.json"
    broken = build_source()
    broken["expired"] = "not-a-time"
    source_path.write_text(json.dumps(broken), encoding="utf-8")

    record = load_source_record(source_path)

    assert record.is_valid is False
    assert "有效时间" in record.status_text


def test_invalid_proxy_port_blocks_export(tmp_path: Path) -> None:
    source_path = tmp_path / "sample.json"
    source_path.write_text(json.dumps(build_source()), encoding="utf-8")
    record = load_source_record(source_path)
    settings = ExportSettings(
        output_filename="accounts.json",
        proxy=ProxyConfig(enabled=True, protocol="http", host="127.0.0.1", port=70000),
    )

    with pytest.raises(ConversionError, match="代理端口无效"):
        export_records([record], settings)
