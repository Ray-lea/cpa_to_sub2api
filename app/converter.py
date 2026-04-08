from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


VALID_PROXY_PROTOCOLS = ("http", "https", "socks5", "socks5h")
WINDOWS_INVALID_FILENAME_CHARS = '<>:"/\\|?*'


class ConversionError(ValueError):
    """Raised when a source file or export setting is invalid."""


@dataclass(slots=True)
class SourceRecord:
    path: Path
    selected: bool
    is_valid: bool
    variant: str
    email: str
    target_name: str
    plan_type: str
    status_text: str
    raw_data: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""

    @property
    def file_name(self) -> str:
        return self.path.name


@dataclass(slots=True)
class ProxyConfig:
    enabled: bool = False
    name: str = "批量导入代理"
    protocol: str = "http"
    host: str = ""
    port: int = 7890
    username: str = ""
    password: str = ""
    status: str = "active"

    def validate(self) -> None:
        if not self.enabled:
            return
        if self.protocol not in VALID_PROXY_PROTOCOLS:
            raise ConversionError("代理协议无效。")
        if not self.host.strip():
            raise ConversionError("已启用代理，但代理地址为空。")
        if not isinstance(self.port, int) or self.port <= 0 or self.port > 65535:
            raise ConversionError("代理端口无效。")
        if self.status not in {"active", "inactive"}:
            raise ConversionError("代理状态只能是 active 或 inactive。")

    @property
    def proxy_key(self) -> str:
        return (
            f"{self.protocol.strip()}|{self.host.strip()}|{self.port}|"
            f"{self.username.strip()}|{self.password.strip()}"
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload: dict[str, Any] = {
            "proxy_key": self.proxy_key,
            "name": self.name.strip() or "批量导入代理",
            "protocol": self.protocol.strip(),
            "host": self.host.strip(),
            "port": self.port,
            "status": self.status,
        }
        if self.username.strip():
            payload["username"] = self.username.strip()
        if self.password.strip():
            payload["password"] = self.password.strip()
        return payload


@dataclass(slots=True)
class ExportSettings:
    output_filename: str
    concurrency: int = 10
    priority: int = 1
    rate_multiplier: float = 1.0
    auto_pause_on_expired: bool = True
    proxy: ProxyConfig = field(default_factory=ProxyConfig)

    def validate(self) -> None:
        validate_output_filename(self.output_filename)
        if self.concurrency < 0:
            raise ConversionError("并发数不能小于 0。")
        if self.priority < 0:
            raise ConversionError("优先级不能小于 0。")
        if self.rate_multiplier < 0:
            raise ConversionError("倍率不能小于 0。")
        self.proxy.validate()


@dataclass(slots=True)
class NormalizedAccount:
    name: str
    platform: str
    type: str
    credentials: dict[str, Any]
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    proxy_key: str | None = None
    concurrency: int = 10
    priority: int = 1
    rate_multiplier: float = 1.0
    auto_pause_on_expired: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "platform": self.platform,
            "type": self.type,
            "credentials": self.credentials,
            "concurrency": self.concurrency,
            "priority": self.priority,
            "rate_multiplier": self.rate_multiplier,
            "auto_pause_on_expired": self.auto_pause_on_expired,
        }
        if self.notes:
            payload["notes"] = self.notes
        if self.extra:
            payload["extra"] = self.extra
        if self.proxy_key:
            payload["proxy_key"] = self.proxy_key
        return payload


@dataclass(slots=True)
class ExportPayload:
    exported_at: str
    proxies: list[dict[str, Any]]
    accounts: list[NormalizedAccount]

    def to_dict(self) -> dict[str, Any]:
        return {
            "exported_at": self.exported_at,
            "proxies": self.proxies,
            "accounts": [account.to_dict() for account in self.accounts],
        }


def generate_default_filename(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return f"sub2api-account-{current.strftime('%Y%m%d%H%M%S')}.json"


def validate_output_filename(filename: str) -> str:
    name = filename.strip()
    if not name:
        raise ConversionError("输出文件名不能为空。")
    if any(char in name for char in WINDOWS_INVALID_FILENAME_CHARS):
        raise ConversionError("输出文件名包含 Windows 不允许的字符。")
    if not name.lower().endswith(".json"):
        name = f"{name}.json"
    return name


def collect_json_files_from_folder(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        raise ConversionError("选择的文件夹不存在。")
    return sorted(path for path in folder.rglob("*.json") if path.is_file())


def load_source_record(path: Path) -> SourceRecord:
    try:
        if path.suffix.lower() != ".json":
            raise ConversionError("只支持 JSON 文件。")
        raw_data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(raw_data, dict):
            raise ConversionError("JSON 顶层必须是对象。")
        normalized = normalize_source_data(raw_data)
        return SourceRecord(
            path=path,
            selected=True,
            is_valid=True,
            variant=detect_variant(raw_data),
            email=normalized["email"],
            target_name=normalized["base_name"],
            plan_type=normalized["plan_type"],
            status_text="可转换",
            raw_data=raw_data,
        )
    except json.JSONDecodeError:
        return SourceRecord(
            path=path,
            selected=False,
            is_valid=False,
            variant="无效 JSON",
            email="",
            target_name="",
            plan_type="",
            status_text="JSON 解析失败",
            error_message="JSON 解析失败",
        )
    except ConversionError as exc:
        return SourceRecord(
            path=path,
            selected=False,
            is_valid=False,
            variant=detect_variant({}),
            email="",
            target_name="",
            plan_type="",
            status_text=str(exc),
            error_message=str(exc),
        )


def merge_source_records(
    existing_records: Sequence[SourceRecord],
    new_paths: Iterable[Path],
) -> list[SourceRecord]:
    records = list(existing_records)
    index_by_path = {record.path.resolve(): idx for idx, record in enumerate(records)}
    for path in new_paths:
        resolved = path.resolve()
        record = load_source_record(path)
        if resolved in index_by_path:
            old_record = records[index_by_path[resolved]]
            if record.is_valid:
                record.selected = old_record.selected
            records[index_by_path[resolved]] = record
        else:
            index_by_path[resolved] = len(records)
            records.append(record)
    refresh_target_names(records)
    return records


def refresh_target_names(records: Sequence[SourceRecord]) -> None:
    ordered = [record for record in records if record.is_valid and record.selected]
    ordered.extend(record for record in records if record.is_valid and not record.selected)
    used_names: dict[str, int] = {}
    for record in ordered:
        base_name = derive_name_from_email(record.email) or record.path.stem
        index = used_names.get(base_name, 0) + 1
        used_names[base_name] = index
        record.target_name = base_name if index == 1 else f"{base_name}-{index}"


def export_records(
    records: Sequence[SourceRecord],
    settings: ExportSettings,
    exported_at: datetime | None = None,
) -> ExportPayload:
    settings.validate()
    refresh_target_names(records)
    selected_records = [record for record in records if record.is_valid and record.selected]
    if not selected_records:
        raise ConversionError("没有可导出的有效文件。")

    proxy_payloads: list[dict[str, Any]] = []
    proxy_key: str | None = None
    if settings.proxy.enabled:
        proxy_payload = settings.proxy.to_dict()
        proxy_payloads.append(proxy_payload)
        proxy_key = proxy_payload["proxy_key"]

    accounts = [
        build_normalized_account(record, settings, proxy_key)
        for record in selected_records
    ]
    timestamp = (exported_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return ExportPayload(
        exported_at=timestamp.isoformat().replace("+00:00", "Z"),
        proxies=proxy_payloads,
        accounts=accounts,
    )


def export_to_file(
    records: Sequence[SourceRecord],
    settings: ExportSettings,
    output_dir: Path,
    exported_at: datetime | None = None,
) -> Path:
    if not str(output_dir).strip():
        raise ConversionError("输出目录不能为空。")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not output_dir.exists() or not output_dir.is_dir():
        raise ConversionError("输出目录无效。")

    output_name = validate_output_filename(settings.output_filename)
    payload = export_records(records, settings, exported_at)
    output_path = output_dir / output_name
    output_path.write_text(
        json.dumps(payload.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def build_normalized_account(
    record: SourceRecord,
    settings: ExportSettings,
    proxy_key: str | None,
) -> NormalizedAccount:
    normalized = normalize_source_data(record.raw_data)
    credentials = dict(normalized["credentials"])
    return NormalizedAccount(
        name=record.target_name,
        notes=normalized["notes"],
        platform="openai",
        type="oauth",
        credentials=credentials,
        proxy_key=proxy_key,
        concurrency=settings.concurrency,
        priority=settings.priority,
        rate_multiplier=settings.rate_multiplier,
        auto_pause_on_expired=settings.auto_pause_on_expired,
    )


def normalize_source_data(raw_data: dict[str, Any]) -> dict[str, Any]:
    access_token = require_string(raw_data, "access_token")
    refresh_token = require_string(raw_data, "refresh_token")
    expired_value = raw_data.get("expired")
    expires_at = normalize_datetime_value(expired_value, "expired")
    id_token = clean_string(raw_data.get("id_token"))

    access_claims = decode_jwt_payload(access_token)
    id_claims = decode_jwt_payload(id_token) if id_token else {}
    access_auth = get_nested_dict(access_claims, "https://api.openai.com/auth")
    id_auth = get_nested_dict(id_claims, "https://api.openai.com/auth")
    access_profile = get_nested_dict(access_claims, "https://api.openai.com/profile")

    email = first_non_empty(
        raw_data.get("email"),
        access_profile.get("email"),
        id_claims.get("email"),
    )
    if not email:
        raise ConversionError("缺少可用的邮箱信息。")

    base_name = derive_name_from_email(email)
    if not base_name:
        raise ConversionError("邮箱格式无效。")

    client_id = first_non_empty(
        raw_data.get("client_id"),
        access_claims.get("client_id"),
        first_audience_value(id_claims.get("aud")),
    )
    chatgpt_account_id = first_non_empty(
        raw_data.get("chatgpt_account_id"),
        raw_data.get("account_id"),
        access_auth.get("chatgpt_account_id"),
        id_auth.get("chatgpt_account_id"),
    )
    chatgpt_user_id = first_non_empty(
        raw_data.get("chatgpt_user_id"),
        access_auth.get("chatgpt_user_id"),
        id_auth.get("chatgpt_user_id"),
        access_auth.get("user_id"),
        id_auth.get("user_id"),
    )
    organization_id = first_non_empty(
        raw_data.get("organization_id"),
        extract_organization_id(id_auth.get("organizations")),
        access_auth.get("poid"),
        id_auth.get("poid"),
    )
    plan_type = first_non_empty(
        raw_data.get("plan_type"),
        access_auth.get("chatgpt_plan_type"),
        id_auth.get("chatgpt_plan_type"),
    )
    subscription_expires_at = normalize_optional_datetime(
        first_non_empty(
            raw_data.get("subscription_expires_at"),
            access_auth.get("chatgpt_subscription_active_until"),
            id_auth.get("chatgpt_subscription_active_until"),
        )
    )

    credentials: dict[str, Any] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "email": email,
    }
    if id_token:
        credentials["id_token"] = id_token
    if client_id:
        credentials["client_id"] = client_id
    if chatgpt_account_id:
        credentials["chatgpt_account_id"] = chatgpt_account_id
    if chatgpt_user_id:
        credentials["chatgpt_user_id"] = chatgpt_user_id
    if organization_id:
        credentials["organization_id"] = organization_id
    if plan_type:
        credentials["plan_type"] = plan_type
    if subscription_expires_at:
        credentials["subscription_expires_at"] = subscription_expires_at

    notes = clean_string(raw_data.get("note"))

    return {
        "email": email,
        "base_name": base_name,
        "plan_type": plan_type,
        "notes": notes,
        "credentials": credentials,
    }


def detect_variant(raw_data: dict[str, Any]) -> str:
    keys = set(raw_data.keys())
    if "device_id" in keys:
        return "含 device_id"
    if "session_token" in keys or "chatgpt_account_id" in keys:
        return "含 ChatGPT 标识"
    if "note" in keys or "websockets" in keys:
        return "含 note/websockets"
    if keys:
        return "通用格式"
    return "未知格式"


def require_string(raw_data: dict[str, Any], key: str) -> str:
    value = clean_string(raw_data.get(key))
    if not value:
        raise ConversionError(f"缺少必要字段：{key}")
    return value


def clean_string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def decode_jwt_payload(token: str) -> dict[str, Any]:
    if not token or token.count(".") < 2:
        return {}
    payload = token.split(".")[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding).decode("utf-8")
        parsed = json.loads(decoded)
    except (ValueError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_nested_dict(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def first_non_empty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def first_audience_value(audience: Any) -> str:
    if isinstance(audience, str):
        return audience.strip()
    if isinstance(audience, list):
        for item in audience:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def extract_organization_id(raw_organizations: Any) -> str:
    if not isinstance(raw_organizations, list):
        return ""
    default_org = ""
    first_org = ""
    for org in raw_organizations:
        if not isinstance(org, dict):
            continue
        org_id = clean_string(org.get("id"))
        if not org_id:
            continue
        if not first_org:
            first_org = org_id
        if org.get("is_default") is True:
            default_org = org_id
            break
    return default_org or first_org


def derive_name_from_email(email: str) -> str:
    text = email.strip()
    if "@" not in text:
        return ""
    local_part = text.split("@", 1)[0].strip()
    return local_part


def normalize_datetime_value(value: Any, field_name: str) -> str:
    if value is None or value == "":
        raise ConversionError(f"缺少必要字段：{field_name}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ConversionError(f"缺少必要字段：{field_name}")
        if text.isdigit():
            unix_value = int(text)
            return datetime.fromtimestamp(unix_value, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ConversionError(f"{field_name} 不是有效时间。") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat().replace("+00:00", "Z")

    raise ConversionError(f"{field_name} 不是有效时间。")


def normalize_optional_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return normalize_datetime_value(value, "subscription_expires_at")
