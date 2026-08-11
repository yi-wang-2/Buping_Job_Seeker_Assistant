"""Local-first job source import, deduplication and recommendation scoring."""

from __future__ import annotations

import csv
import base64
import hashlib
import io
import json
import re
import sqlite3
import zipfile
import time
import threading
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from xml.etree import ElementTree as ET

import yaml


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data_folder"
DB_PATH = DATA_DIR / "job_radar.sqlite3"
DEFAULT_TENCENT_SOURCE = "https://docs.qq.com/smartsheet/DZkdPVGtGb1ZvaG5R?tab=t00i2h"
_SYNC_LOCK = threading.Lock()

_HEADER_ALIASES = {
    "company": ("公司", "公司名称", "企业", "企业名称", "单位", "单位名称"),
    "role": ("岗位", "岗位名称", "职位", "职位名称", "招聘岗位", "职位类别"),
    "location": ("地点", "工作地点", "城市", "base", "base地", "办公地点"),
    "industry": ("行业", "行业类型", "所属行业"),
    "recruitment_type": ("招聘类型", "招聘批次", "批次", "届次", "校招类型"),
    "link": ("链接", "岗位链接", "招聘链接", "投递链接", "网申链接", "官网链接", "内推链接", "申请链接"),
    "referral": ("内推", "内推码", "内推信息", "推荐码"),
    "deadline": ("截止时间", "截止日期", "网申截止", "截止"),
    "description": ("岗位描述", "职位描述", "jd", "要求", "岗位要求", "备注"),
}

_TECH_TERMS = {
    "python", "java", "c++", "c#", "javascript", "typescript", "react", "vue", "node.js",
    "golang", "go", "rust", "linux", "sql", "mysql", "postgresql", "redis", "mongodb",
    "docker", "kubernetes", "aws", "azure", "pytorch", "tensorflow", "机器学习", "深度学习",
    "大模型", "llm", "nlp", "计算机视觉", "推荐系统", "数据分析", "数据开发", "后端", "前端",
    "算法", "测试", "运维", "产品", "运营", "嵌入式", "自动驾驶", "机器人", "控制", "硬件",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS job_postings (
            id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL UNIQUE,
            content_hash TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            industry TEXT NOT NULL DEFAULT '',
            recruitment_type TEXT NOT NULL DEFAULT '',
            link TEXT NOT NULL DEFAULT '',
            referral TEXT NOT NULL DEFAULT '',
            deadline TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            raw_json TEXT NOT NULL DEFAULT '{}',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
        );
        CREATE INDEX IF NOT EXISTS idx_job_postings_seen ON job_postings(last_seen_at DESC);
        CREATE INDEX IF NOT EXISTS idx_job_postings_company ON job_postings(company);
        CREATE TABLE IF NOT EXISTS job_sync_runs (
            id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            filename TEXT NOT NULL,
            imported INTEGER NOT NULL,
            created INTEGER NOT NULL,
            updated INTEGER NOT NULL,
            unchanged INTEGER NOT NULL,
            skipped INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS job_radar_actions (
            job_id TEXT PRIMARY KEY,
            favorite INTEGER NOT NULL DEFAULT 0,
            not_interested INTEGER NOT NULL DEFAULT 0,
            applied INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES job_postings(id)
        );
        CREATE TABLE IF NOT EXISTS job_radar_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    return db


def _normalize_header(value: Any) -> str:
    return re.sub(r"[\s\-_/（）()【】\[\]:：]+", "", str(value or "").strip().lower())


def _header_field(value: Any) -> str | None:
    normalized = _normalize_header(value)
    exact = [(field, alias) for field, aliases in _HEADER_ALIASES.items() for alias in aliases
             if normalized == _normalize_header(alias)]
    if exact:
        return max(exact, key=lambda item: len(_normalize_header(item[1])))[0]
    matches = [(field, alias) for field, aliases in _HEADER_ALIASES.items() for alias in aliases
               if _normalize_header(alias) in normalized]
    if matches:
        return max(matches, key=lambda item: len(_normalize_header(item[1])))[0]
    return None


def _decode_csv(raw: bytes) -> list[list[str]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            delimiter = "\t" if text.count("\t") > text.count(",") else ","
            return [[str(cell).strip() for cell in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError("CSV 文件编码无法识别，请导出为 UTF-8 CSV") from last_error


def _cell_column(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    value = 0
    for char in letters.group(0) if letters else "A":
        value = value * 26 + ord(char) - 64
    return value - 1


def _xlsx_rows(raw: bytes) -> list[list[str]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError("无效的 XLSX 文件") from exc

    with archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", ns):
                shared.append("".join(node.text or "" for node in item.iterfind(".//m:t", ns)))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in relationships.findall("pr:Relationship", ns)}
        all_rows: list[list[str]] = []
        for sheet in workbook.findall("m:sheets/m:sheet", ns):
            target = targets.get(sheet.attrib.get(f"{{{ns['r']}}}id", ""), "")
            sheet_path = str(PurePosixPath("xl") / target).replace("xl/xl/", "xl/")
            if sheet_path not in archive.namelist():
                continue
            sheet_root = ET.fromstring(archive.read(sheet_path))
            hyperlink_targets: dict[str, str] = {}
            rel_path = str(PurePosixPath(sheet_path).parent / "_rels" / f"{PurePosixPath(sheet_path).name}.rels")
            if rel_path in archive.namelist():
                sheet_rels = ET.fromstring(archive.read(rel_path))
                rel_targets = {node.attrib["Id"]: node.attrib.get("Target", "") for node in sheet_rels.findall("pr:Relationship", ns)}
                for link in sheet_root.findall("m:hyperlinks/m:hyperlink", ns):
                    hyperlink_targets[link.attrib.get("ref", "")] = rel_targets.get(link.attrib.get(f"{{{ns['r']}}}id", ""), "")
            for row in sheet_root.findall("m:sheetData/m:row", ns):
                values: dict[int, str] = {}
                for cell in row.findall("m:c", ns):
                    ref = cell.attrib.get("r", "A1")
                    cell_type = cell.attrib.get("t", "")
                    value_node = cell.find("m:v", ns)
                    inline = cell.find("m:is", ns)
                    value = ""
                    if inline is not None:
                        value = "".join(node.text or "" for node in inline.iterfind(".//m:t", ns))
                    elif value_node is not None:
                        value = value_node.text or ""
                        if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                            value = shared[int(value)]
                    if ref in hyperlink_targets and (not value or not re.match(r"https?://", value)):
                        value = hyperlink_targets[ref]
                    values[_cell_column(ref)] = value.strip()
                if values:
                    all_rows.append([values.get(index, "") for index in range(max(values) + 1)])
        return all_rows


def _map_rows(rows: list[list[str]]) -> list[dict[str, str]]:
    rows = [row for row in rows if any(str(cell).strip() for cell in row)]
    if not rows:
        return []

    best_index = -1
    best_mapping: dict[int, str] = {}
    for index, row in enumerate(rows[:20]):
        mapping = {column: field for column, cell in enumerate(row) if (field := _header_field(cell))}
        if len(set(mapping.values())) > len(set(best_mapping.values())):
            best_index, best_mapping = index, mapping
    if best_index < 0 or "company" not in best_mapping.values():
        raise ValueError("未识别到公司列，请确保表格包含“公司/公司名称”表头")

    headers = [str(cell).strip() or f"column_{index + 1}" for index, cell in enumerate(rows[best_index])]
    parsed: list[dict[str, str]] = []
    inherited: dict[str, str] = {}
    for values in rows[best_index + 1:]:
        raw_record = {headers[index] if index < len(headers) else f"column_{index + 1}": str(value).strip()
                      for index, value in enumerate(values) if str(value).strip()}
        record = {field: str(values[column]).strip() if column < len(values) else ""
                  for column, field in best_mapping.items()}
        for field in ("company", "industry", "recruitment_type"):
            if record.get(field):
                inherited[field] = record[field]
            elif inherited.get(field):
                record[field] = inherited[field]
        record["raw_json"] = json.dumps(raw_record, ensure_ascii=False, sort_keys=True)
        if record.get("company") and any(record.get(key) for key in ("role", "link", "description", "referral")):
            parsed.append(record)
    return parsed


def parse_tabular_file(filename: str, raw: bytes) -> list[dict[str, str]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        rows = _decode_csv(raw)
    elif suffix == ".xlsx":
        rows = _xlsx_rows(raw)
    else:
        raise ValueError("仅支持 .xlsx 和 .csv 文件")
    return _map_rows(rows)


def parse_copied_table(text: str) -> list[dict[str, str]]:
    """Parse tab/newline data copied from the Tencent Smart Sheet canvas."""
    rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text), delimiter="\t")]
    return _map_rows(rows)


def _decode_smartsheet_payload(encoded: str) -> list[dict[str, Any]]:
    """Decode the compressed operation stream used by Tencent's sheet viewer."""
    if not encoded:
        return []
    encoded += "=" * (-len(encoded) % 4)
    decoded = zlib.decompress(base64.b64decode(encoded)).decode("utf-8")
    value = json.loads(decoded)
    return value if isinstance(value, list) else []


def _response_smartsheet_streams(response_text: str) -> list[str]:
    text = response_text.strip()
    if text.startswith("clientVarsCallback("):
        text = text[len("clientVarsCallback("):]
        if text.endswith(");"):
            text = text[:-2]
        elif text.endswith(")"):
            text = text[:-1]
    payload = json.loads(text)
    entries = (
        payload.get("clientVars", {})
        .get("collab_client_vars", {})
        .get("initialAttributedText", {})
        .get("text", [])
    )
    if not entries:
        entries = payload.get("data", {}).get("initialAttributedText", {}).get("text", [])
    return [entry.get("smartsheet", "") for entry in entries if isinstance(entry, dict) and entry.get("smartsheet")]


def _option_labels(field: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            option_id, label = value.get("k1"), value.get("k2")
            if isinstance(option_id, str) and isinstance(label, str) and option_id.startswith("o"):
                labels[option_id] = label
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(field)
    return labels


def _cell_text(cell: Any, options: dict[str, str]) -> str:
    if not isinstance(cell, dict):
        return str(cell or "").strip()
    rich_text = cell.get("k1")
    if isinstance(rich_text, list):
        parts = []
        for item in rich_text:
            if isinstance(item, dict):
                parts.append(str(item.get("k3") or item.get("k2") or ""))
        if any(parts):
            return "".join(parts).strip()
    links = cell.get("k8")
    if isinstance(links, list):
        values = [str(item.get("k3") or item.get("k2") or "") for item in links if isinstance(item, dict)]
        if any(values):
            return "\n".join(value for value in values if value).strip()
    selected = cell.get("k9")
    if isinstance(selected, list):
        return " / ".join(options.get(str(value), str(value)) for value in selected).strip()
    timestamp = cell.get("k4")
    if isinstance(timestamp, str) and timestamp.isdigit():
        return datetime.fromtimestamp(int(timestamp) / 1000, timezone.utc).date().isoformat()
    for value in cell.values():
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def parse_tencent_sheet_responses(response_texts: Iterable[str]) -> list[dict[str, str]]:
    """Turn Tencent's read-only viewer responses into normalized job records."""
    operations: list[dict[str, Any]] = []
    for response_text in response_texts:
        for stream in _response_smartsheet_streams(response_text):
            operations.extend(_decode_smartsheet_payload(stream))

    fields: dict[str, dict[str, Any]] = {}
    rows: dict[str, dict[str, Any]] = {}
    for batch in operations:
        items = batch if isinstance(batch, list) else [batch]
        for operation in items:
            if not isinstance(operation, dict):
                continue
            content = operation.get("c", {})
            if operation.get("t") == 3005:
                candidates = content.get("k3", {}).get("k3", {})
                if isinstance(candidates, dict):
                    fields.update({key: value for key, value in candidates.items() if isinstance(value, dict)})
            elif operation.get("t") == 3028:
                candidates = content.get("k2", {}).get("k1", {})
                if isinstance(candidates, dict):
                    rows.update({key: value for key, value in candidates.items() if isinstance(value, dict)})

    # Smart Sheet field titles currently use k30. Keep k2 as a fallback for
    # older response versions.
    names = {field_id: str(field.get("k30") or field.get("k2") or "").strip() for field_id, field in fields.items()}
    option_maps = {field_id: _option_labels(field) for field_id, field in fields.items()}
    exact_mapping = {
        "企业名称": "company", "行业类型": "industry", "招聘类型": "recruitment_type",
        "工作地点": "location", "内推码(区分大小写)": "referral", "内推链接": "link",
        "整体文案": "description",
    }
    parsed: list[dict[str, str]] = []
    for row_id, row in rows.items():
        cells = row.get("k1", {})
        if not isinstance(cells, dict):
            continue
        source_row = {
            names.get(field_id, field_id): _cell_text(cell, option_maps.get(field_id, {}))
            for field_id, cell in cells.items()
        }
        record = {target: source_row.get(source, "") for source, target in exact_mapping.items()}
        notes = source_row.get("备注", "")
        if notes:
            record["description"] = "\n".join(filter(None, (record.get("description", ""), notes)))
        record["role"] = source_row.get("岗位名称", "") or source_row.get("职位名称", "")
        record["raw_json"] = json.dumps({"row_id": row_id, **source_row}, ensure_ascii=False, sort_keys=True)
        if record.get("company") and any(record.get(key) for key in ("role", "link", "description", "referral")):
            parsed.append(record)
    return parsed


def read_tencent_sheet(source_url: str) -> list[dict[str, str]]:
    """Read data that Tencent's public/read-only page fetches for rendering."""
    from urllib.parse import urlparse
    from selenium.webdriver.support.ui import WebDriverWait
    from src.utils.chrome_utils import init_browser

    parsed_url = urlparse(source_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "docs.qq.com" or "/smartsheet/" not in parsed_url.path:
        raise ValueError("第一版仅允许同步 https://docs.qq.com/smartsheet/ 只读链接")

    # Tencent Smart Sheet deliberately defers its canvas grid in headless
    # Chromium. Use a visible, short-lived browser for this user-triggered
    # read operation; PDF generation keeps the default headless mode.
    driver = init_browser(headless=False)
    try:
        driver.set_window_size(1440, 1000)
        driver.set_page_load_timeout(90)
        driver.get(source_url)
        WebDriverWait(driver, 60).until(lambda current: "smartsheet" in current.current_url and current.title)

        def data_urls(current):
            resources = current.execute_script(
                "return performance.getEntriesByType('resource').map(function(x){return x.name})"
            )
            matches = [url for url in resources if "/dop-api/opendoc?" in url or "/dop-api/get/sheet?" in url]
            # The first response contains schema/initial rows; the second one
            # contains the remainder of larger sheets.
            return list(dict.fromkeys(matches)) if any("/dop-api/opendoc?" in url for url in matches) else False

        urls = WebDriverWait(driver, 90).until(data_urls)
        # Give the viewer a short window to request the remaining row range.
        end = time.monotonic() + 15
        while time.monotonic() < end and not any("/dop-api/get/sheet?" in url for url in urls):
            time.sleep(1)
            urls = data_urls(driver) or urls
        responses = []
        for url in urls:
            response = driver.execute_async_script(
                """
                const url = arguments[0], done = arguments[arguments.length - 1];
                fetch(url, {credentials: 'include'})
                  .then(r => r.ok ? r.text() : Promise.reject(new Error('HTTP ' + r.status)))
                  .then(text => done({ok: true, text}))
                  .catch(error => done({ok: false, error: String(error)}));
                """,
                url,
            )
            if response.get("ok"):
                responses.append(response["text"])
        records = parse_tencent_sheet_responses(responses)
        if not records:
            raise RuntimeError("腾讯文档已打开，但未读取到岗位数据；请确认该链接仍可匿名查看")
        return records
    finally:
        driver.quit()


def sync_tencent_sheet(source_url: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    with _SYNC_LOCK:
        records = read_tencent_sheet(source_url)
    if not records:
        raise ValueError("表格中没有识别到岗位记录")
    # Reuse the exact database upsert contract without fabricating an export.
    timestamp = _now()
    stats = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "deactivated": 0}
    seen_fingerprints: set[str] = set()
    with _connect(db_path) as db:
        for record in records:
            fingerprint = _fingerprint(record)
            seen_fingerprints.add(fingerprint)
            content_hash = hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            existing = db.execute("SELECT id, content_hash, updated_at FROM job_postings WHERE fingerprint=?", (fingerprint,)).fetchone()
            if existing:
                changed = existing["content_hash"] != content_hash
                db.execute(
                    """UPDATE job_postings SET content_hash=?, source_name=?, source_url=?, company=?, role=?, location=?,
                       industry=?, recruitment_type=?, link=?, referral=?, deadline=?, description=?, raw_json=?,
                       last_seen_at=?, updated_at=?, status='active' WHERE fingerprint=?""",
                    (content_hash, "腾讯文档岗位表", source_url, record.get("company", ""), record.get("role", ""),
                     record.get("location", ""), record.get("industry", ""), record.get("recruitment_type", ""),
                     record.get("link", ""), record.get("referral", ""), record.get("deadline", ""),
                     record.get("description", ""), record.get("raw_json", "{}"), timestamp,
                     timestamp if changed else existing["updated_at"], fingerprint),
                )
                stats["updated" if changed else "unchanged"] += 1
            else:
                job_id = hashlib.sha256(f"{fingerprint}|{timestamp}".encode()).hexdigest()[:24]
                db.execute(
                    """INSERT INTO job_postings(id,fingerprint,content_hash,source_name,source_url,company,role,location,
                       industry,recruitment_type,link,referral,deadline,description,raw_json,first_seen_at,last_seen_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (job_id, fingerprint, content_hash, "腾讯文档岗位表", source_url, record.get("company", ""),
                     record.get("role", ""), record.get("location", ""), record.get("industry", ""),
                     record.get("recruitment_type", ""), record.get("link", ""), record.get("referral", ""),
                     record.get("deadline", ""), record.get("description", ""), record.get("raw_json", "{}"),
                     timestamp, timestamp, timestamp),
                )
                stats["created"] += 1
        stats["deactivated"] = _deactivate_missing(db, source_url, seen_fingerprints)
        run_id = hashlib.sha256(f"{source_url}|{timestamp}".encode()).hexdigest()[:24]
        db.execute("INSERT INTO job_sync_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (run_id, "腾讯文档岗位表", source_url, "direct-read", len(records), stats["created"],
                    stats["updated"], stats["unchanged"], stats["skipped"], timestamp))
    set_radar_setting("source_url", source_url, db_path)
    return {"status": "ok", "imported": len(records), **stats, "filename": "direct-read", "synced_at": timestamp}


def _fingerprint(record: dict[str, str]) -> str:
    identity = "|".join(record.get(key, "").strip().lower() for key in ("company", "role", "location", "link"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _deactivate_missing(db: sqlite3.Connection, source_url: str, fingerprints: set[str]) -> int:
    if not source_url or not fingerprints:
        return 0
    placeholders = ",".join("?" for _ in fingerprints)
    result = db.execute(
        f"UPDATE job_postings SET status='inactive' WHERE source_url=? AND status='active' AND fingerprint NOT IN ({placeholders})",
        (source_url, *sorted(fingerprints)),
    )
    return max(0, result.rowcount)


def import_file(filename: str, raw: bytes, source_url: str = "", source_name: str = "腾讯文档岗位表",
                db_path: Path = DB_PATH) -> dict[str, Any]:
    records = parse_tabular_file(filename, raw)
    timestamp = _now()
    stats = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "deactivated": 0}
    seen_fingerprints: set[str] = set()
    with _connect(db_path) as db:
        for record in records:
            fingerprint = _fingerprint(record)
            seen_fingerprints.add(fingerprint)
            content_hash = hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            existing = db.execute("SELECT id, content_hash FROM job_postings WHERE fingerprint=?", (fingerprint,)).fetchone()
            if existing:
                changed = existing["content_hash"] != content_hash
                db.execute(
                    """UPDATE job_postings SET content_hash=?, source_name=?, source_url=?, company=?, role=?, location=?,
                       industry=?, recruitment_type=?, link=?, referral=?, deadline=?, description=?, raw_json=?,
                       last_seen_at=?, updated_at=?, status='active' WHERE fingerprint=?""",
                    (content_hash, source_name, source_url, record.get("company", ""), record.get("role", ""),
                     record.get("location", ""), record.get("industry", ""), record.get("recruitment_type", ""),
                     record.get("link", ""), record.get("referral", ""), record.get("deadline", ""),
                     record.get("description", ""), record.get("raw_json", "{}"), timestamp,
                     timestamp if changed else db.execute("SELECT updated_at FROM job_postings WHERE fingerprint=?", (fingerprint,)).fetchone()[0],
                     fingerprint),
                )
                stats["updated" if changed else "unchanged"] += 1
            else:
                job_id = hashlib.sha256(f"{fingerprint}|{timestamp}".encode()).hexdigest()[:24]
                db.execute(
                    """INSERT INTO job_postings(id,fingerprint,content_hash,source_name,source_url,company,role,location,
                       industry,recruitment_type,link,referral,deadline,description,raw_json,first_seen_at,last_seen_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (job_id, fingerprint, content_hash, source_name, source_url, record.get("company", ""),
                     record.get("role", ""), record.get("location", ""), record.get("industry", ""),
                     record.get("recruitment_type", ""), record.get("link", ""), record.get("referral", ""),
                     record.get("deadline", ""), record.get("description", ""), record.get("raw_json", "{}"),
                     timestamp, timestamp, timestamp),
                )
                stats["created"] += 1
        stats["deactivated"] = _deactivate_missing(db, source_url, seen_fingerprints)
        run_id = hashlib.sha256(f"{filename}|{timestamp}".encode()).hexdigest()[:24]
        db.execute(
            "INSERT INTO job_sync_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
            (run_id, source_name, source_url, filename, len(records), stats["created"], stats["updated"],
             stats["unchanged"], stats["skipped"], timestamp),
        )
    return {"status": "ok", "imported": len(records), **stats, "filename": filename, "synced_at": timestamp}


def _flatten(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for child in value.values():
            yield from _flatten(child)
    elif isinstance(value, list):
        for child in value:
            yield from _flatten(child)
    elif value is not None:
        yield str(value)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text("utf-8")) if path.exists() else {}
        return value if isinstance(value, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


@dataclass(frozen=True)
class UserProfile:
    resume_text: str
    roles: tuple[str, ...]
    locations: tuple[str, ...]
    acceptable_locations: tuple[str, ...]
    company_blacklist: tuple[str, ...]
    title_blacklist: tuple[str, ...]
    location_blacklist: tuple[str, ...]
    industries: tuple[str, ...]
    company_types: tuple[str, ...]
    recruitment_types: tuple[str, ...]
    preferred_keywords: tuple[str, ...]
    excluded_keywords: tuple[str, ...]
    weights: dict[str, float]
    technologies: frozenset[str]


DEFAULT_SCORE_WEIGHTS = {
    "skills": 25.0, "role": 25.0, "location": 15.0, "industry": 10.0,
    "company": 10.0, "recruitment": 10.0, "referral": 5.0,
}


def _string_list(value: Any) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in (value or []) if str(item).strip()))


def get_user_preferences(db_path: Path = DB_PATH, data_dir: Path = DATA_DIR) -> dict[str, Any]:
    preferences_path = data_dir / "work_preferences_zh.yaml"
    if not preferences_path.exists():
        preferences_path = data_dir / "work_preferences.yaml"
    legacy = _load_yaml(preferences_path)
    defaults: dict[str, Any] = {
        "target_roles": _string_list(legacy.get("positions", [])),
        "preferred_locations": _string_list(legacy.get("locations", [])),
        "acceptable_locations": [],
        "excluded_locations": _string_list(legacy.get("location_blacklist", [])),
        "recruitment_types": [], "industries": [], "company_types": [],
        "preferred_keywords": [],
        "excluded_keywords": _string_list(legacy.get("title_blacklist", [])),
        "company_blacklist": _string_list(legacy.get("company_blacklist", [])),
        "weights": dict(DEFAULT_SCORE_WEIGHTS),
    }
    with _connect(db_path) as db:
        row = db.execute("SELECT value FROM job_radar_settings WHERE key='user_preferences'").fetchone()
    if not row:
        return defaults
    try:
        saved = json.loads(row["value"])
    except (TypeError, json.JSONDecodeError):
        return defaults
    if not isinstance(saved, dict):
        return defaults
    merged = {**defaults, **saved}
    merged["weights"] = {**DEFAULT_SCORE_WEIGHTS, **(saved.get("weights") or {})}
    return merged


def save_user_preferences(preferences: dict[str, Any], db_path: Path = DB_PATH) -> dict[str, Any]:
    list_fields = (
        "target_roles", "preferred_locations", "acceptable_locations", "excluded_locations",
        "recruitment_types", "industries", "company_types", "preferred_keywords",
        "excluded_keywords", "company_blacklist",
    )
    cleaned = {field: _string_list(preferences.get(field, [])) for field in list_fields}
    weights = preferences.get("weights") or {}
    cleaned["weights"] = {
        key: max(0.0, min(100.0, float(weights.get(key, default))))
        for key, default in DEFAULT_SCORE_WEIGHTS.items()
    }
    set_radar_setting("user_preferences", json.dumps(cleaned, ensure_ascii=False), db_path)
    return cleaned


def load_user_profile(data_dir: Path = DATA_DIR, db_path: Path = DB_PATH) -> UserProfile:
    resume_path = data_dir / "plain_text_resume_zh.yaml"
    if not resume_path.exists():
        resume_path = data_dir / "plain_text_resume.yaml"
    resume = _load_yaml(resume_path)
    preferences = get_user_preferences(db_path=db_path, data_dir=data_dir)
    resume_text = " ".join(_flatten(resume)).lower()
    roles = _string_list(preferences.get("target_roles", []))
    if not roles:
        roles.extend(str(item.get("position", "")).strip() for item in resume.get("experience_details", []) if isinstance(item, dict))
    technologies = frozenset(term for term in _TECH_TERMS if term.lower() in resume_text)
    return UserProfile(
        resume_text=resume_text,
        roles=tuple(filter(None, roles)),
        locations=tuple(_string_list(preferences.get("preferred_locations", []))),
        acceptable_locations=tuple(_string_list(preferences.get("acceptable_locations", []))),
        company_blacklist=tuple(item.lower() for item in _string_list(preferences.get("company_blacklist", []))),
        title_blacklist=tuple(item.lower() for item in _string_list(preferences.get("excluded_keywords", []))),
        location_blacklist=tuple(item.lower() for item in _string_list(preferences.get("excluded_locations", []))),
        industries=tuple(_string_list(preferences.get("industries", []))),
        company_types=tuple(_string_list(preferences.get("company_types", []))),
        recruitment_types=tuple(_string_list(preferences.get("recruitment_types", []))),
        preferred_keywords=tuple(_string_list(preferences.get("preferred_keywords", []))),
        excluded_keywords=tuple(item.lower() for item in _string_list(preferences.get("excluded_keywords", []))),
        weights={key: float(value) for key, value in preferences.get("weights", DEFAULT_SCORE_WEIGHTS).items()},
        technologies=technologies,
    )


def _keywords(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z][a-z0-9+#.]{1,20}", lowered))
    words.update(term for term in _TECH_TERMS if term.lower() in lowered)
    words.update(re.findall(r"[\u4e00-\u9fff]{2,6}", lowered))
    return words


def score_job(job: dict[str, Any], profile: UserProfile) -> dict[str, Any]:
    text = " ".join(str(job.get(key, "")) for key in ("company", "role", "location", "industry", "recruitment_type", "description")).lower()
    hard_risks: list[str] = []
    if any(term and term in str(job.get("company", "")).lower() for term in profile.company_blacklist):
        hard_risks.append("公司在排除列表中")
    if any(term and term in str(job.get("role", "")).lower() for term in profile.title_blacklist):
        hard_risks.append("岗位名称命中排除词")
    if any(term and term in str(job.get("location", "")).lower() for term in profile.location_blacklist):
        hard_risks.append("地点在排除列表中")
    if "岗位名称命中排除词" not in hard_risks and any(term and term in text for term in profile.excluded_keywords):
        hard_risks.append("招聘信息命中排除关键词")

    job_tech = {term for term in _TECH_TERMS if term.lower() in text}
    matched_tech = sorted(job_tech & profile.technologies)
    missing_tech = sorted(job_tech - profile.technologies)
    skill_rate = min(1.0, 0.35 + len(matched_tech) * 0.2) if matched_tech else (0.45 if not job_tech else 0.0)

    role_words = _keywords(text)
    preferred_words = _keywords(" ".join(profile.roles))
    role_matches = sorted(role_words & preferred_words)
    keyword_matches = [item for item in profile.preferred_keywords if item.lower() in text]
    role_rate = min(1.0, 0.55 + len(role_matches) * 0.15 + len(keyword_matches) * 0.1) if (role_matches or keyword_matches) else (0.45 if not profile.roles and not profile.preferred_keywords else 0.0)

    location = str(job.get("location", "")).lower()
    matched_locations = [item for item in profile.locations if item.lower() in location or location in item.lower()]
    acceptable_locations = [item for item in profile.acceptable_locations if item.lower() in location or location in item.lower()]
    location_rate = 1.0 if matched_locations else (0.65 if acceptable_locations else (0.45 if not profile.locations or not location else 0.0))

    industry = str(job.get("industry", "")).lower()
    matched_industries = [item for item in profile.industries if item.lower() in industry or item.lower() in text]
    industry_rate = 1.0 if matched_industries else (0.5 if not profile.industries else 0.0)
    company_type = _company_type(job)
    company_rate = 1.0 if company_type in profile.company_types else (0.5 if not profile.company_types else 0.0)
    recruitment_tags = _recruitment_tags(job)
    matched_recruitment = [item for item in profile.recruitment_types if item in recruitment_tags]
    recruitment_rate = 1.0 if matched_recruitment else (0.5 if not profile.recruitment_types else 0.0)
    referral_rate = 1.0 if job.get("referral") else 0.35

    weights = {**DEFAULT_SCORE_WEIGHTS, **profile.weights}
    weight_total = sum(max(0.0, value) for value in weights.values()) or 1.0
    rates = {"skills": skill_rate, "role": role_rate, "location": location_rate,
             "industry": industry_rate, "company": company_rate,
             "recruitment": recruitment_rate, "referral": referral_rate}
    breakdown = {key: round(max(0.0, weights[key]) / weight_total * 100 * rates[key], 1) for key in rates}
    total = sum(breakdown.values())
    if hard_risks:
        total = min(total, 20.0)

    reasons: list[str] = []
    if matched_tech:
        reasons.append(f"简历技能匹配：{', '.join(matched_tech[:5])}")
    if role_matches:
        reasons.append(f"岗位方向匹配：{', '.join(role_matches[:4])}")
    if matched_locations:
        reasons.append(f"地点符合偏好：{', '.join(matched_locations[:3])}")
    elif acceptable_locations:
        reasons.append(f"地点在可接受范围：{', '.join(acceptable_locations[:3])}")
    if matched_industries:
        reasons.append(f"行业符合偏好：{', '.join(matched_industries[:3])}")
    if company_type in profile.company_types:
        reasons.append(f"公司类型符合偏好：{company_type}")
    if matched_recruitment:
        reasons.append(f"招聘类型符合偏好：{', '.join(matched_recruitment)}")
    if keyword_matches:
        reasons.append(f"命中期望关键词：{', '.join(keyword_matches[:4])}")
    if job.get("referral"):
        reasons.append("包含内推信息")
    if not reasons:
        reasons.append("信息有限，建议打开招聘链接核实具体岗位")
    return {
        "score": round(max(0.0, min(100.0, total)), 1),
        "reasons": reasons,
        "matched_skills": matched_tech,
        "missing_skills": missing_tech[:8],
        "hard_risks": hard_risks,
        "breakdown": breakdown,
    }


def _recruitment_tags(job: dict[str, Any]) -> list[str]:
    text = " ".join(str(job.get(key, "")) for key in ("recruitment_type", "description"))
    rules = (
        ("秋招", ("秋招", "秋季招聘")),
        ("实习", ("实习", "intern")),
        ("提前批", ("提前批", "早鸟批")),
        ("正式批", ("正式批", "正式校招")),
        ("夏令营", ("夏令营",)),
    )
    lowered = text.lower()
    return [label for label, terms in rules if any(term.lower() in lowered for term in terms)]


def _company_type(job: dict[str, Any]) -> str:
    text = " ".join(str(job.get(key, "")) for key in ("company", "industry", "description")).lower()
    if any(term in text for term in ("央企", "国企", "国有企业", "国资委")):
        return "国企/央企"
    if any(term in text for term in ("外企", "外资", "跨国公司", "foreign")):
        return "外企"
    if any(term in text for term in ("研究院", "研究所", "科学院", "大学", "事业单位")):
        return "科研/事业单位"
    if any(term in text for term in ("上市公司", "上市企业", "证券交易所")):
        return "上市公司"
    return "其他企业"


def _match_level(score: float) -> str:
    if score >= 70:
        return "高匹配"
    if score >= 50:
        return "中匹配"
    return "低匹配"


def list_recommendations(limit: int = 100, min_score: float = 0, query: str = "",
                         company_type: str = "", match_level: str = "", recruitment_type: str = "",
                         favorite_only: bool = False,
                         db_path: Path = DB_PATH, data_dir: Path = DATA_DIR) -> dict[str, Any]:
    profile = load_user_profile(data_dir, db_path)
    with _connect(db_path) as db:
        rows = [dict(row) for row in db.execute(
            """SELECT p.*, COALESCE(a.favorite, 0) AS favorite, COALESCE(a.not_interested, 0) AS not_interested,
                      COALESCE(a.applied, 0) AS applied
               FROM job_postings p LEFT JOIN job_radar_actions a ON a.job_id=p.id
               WHERE p.status='active' ORDER BY p.last_seen_at DESC"""
        ).fetchall()]
    query_lower = query.strip().lower()
    items = []
    for row in rows:
        if query_lower and query_lower not in " ".join(str(value).lower() for value in row.values()):
            continue
        result = score_job(row, profile)
        if result["score"] < min_score:
            continue
        tags = _recruitment_tags(row)
        row_company_type = _company_type(row)
        level = _match_level(result["score"])
        if company_type and row_company_type != company_type:
            continue
        if match_level and level != match_level:
            continue
        if recruitment_type and recruitment_type not in tags:
            continue
        if favorite_only and not row["favorite"]:
            continue
        row.pop("raw_json", None)
        row.pop("fingerprint", None)
        row.pop("content_hash", None)
        for action_name in ("favorite", "not_interested", "applied"):
            row[action_name] = bool(row[action_name])
        items.append({**row, **result, "company_type": row_company_type,
                      "match_level": level, "recruitment_tags": tags})
    items.sort(key=lambda item: (item["score"], item["last_seen_at"]), reverse=True)
    return {"items": items[:limit], "count": len(items), "profile": {
        "preferred_roles": list(profile.roles[:10]), "preferred_locations": list(profile.locations),
        "resume_skills": sorted(profile.technologies),
    }}


def set_job_action(job_id: str, action: str, enabled: bool = True, db_path: Path = DB_PATH) -> dict[str, Any]:
    columns = {"favorite": "favorite", "not_interested": "not_interested", "applied": "applied"}
    column = columns.get(action)
    if not column:
        raise ValueError("不支持的岗位操作")
    with _connect(db_path) as db:
        exists = db.execute("SELECT 1 FROM job_postings WHERE id=?", (job_id,)).fetchone()
        if not exists:
            raise LookupError("岗位不存在")
        db.execute(
            "INSERT OR IGNORE INTO job_radar_actions(job_id, updated_at) VALUES(?, ?)",
            (job_id, _now()),
        )
        db.execute(
            f"UPDATE job_radar_actions SET {column}=?, updated_at=? WHERE job_id=?",
            (int(enabled), _now(), job_id),
        )
        if enabled and action == "favorite":
            db.execute("UPDATE job_radar_actions SET not_interested=0 WHERE job_id=?", (job_id,))
        elif enabled and action == "not_interested":
            db.execute("UPDATE job_radar_actions SET favorite=0 WHERE job_id=?", (job_id,))
        state = db.execute("SELECT favorite, not_interested, applied FROM job_radar_actions WHERE job_id=?", (job_id,)).fetchone()
    return {key: bool(state[key]) for key in ("favorite", "not_interested", "applied")}


def daily_recommendations(limit: int = 3, db_path: Path = DB_PATH,
                          data_dir: Path = DATA_DIR) -> dict[str, Any]:
    result = list_recommendations(limit=10000, db_path=db_path, data_dir=data_dir)
    selected: list[dict[str, Any]] = []
    companies: set[str] = set()
    blocked_companies = {
        item["company"].strip().lower() for item in result["items"]
        if item["favorite"] or item["not_interested"] or item["applied"]
    }
    for item in result["items"]:
        company_key = item["company"].strip().lower()
        if not company_key or company_key in companies or company_key in blocked_companies:
            continue
        companies.add(company_key)
        selected.append(item)
        if len(selected) >= limit:
            break
    return {"items": selected, "count": len(selected), "date": datetime.now().astimezone().date().isoformat()}


def get_job(job_id: str, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    with _connect(db_path) as db:
        row = db.execute("SELECT * FROM job_postings WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def set_radar_setting(key: str, value: str, db_path: Path = DB_PATH) -> None:
    with _connect(db_path) as db:
        db.execute(
            "INSERT INTO job_radar_settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_radar_settings(db_path: Path = DB_PATH) -> dict[str, Any]:
    with _connect(db_path) as db:
        values = {row["key"]: row["value"] for row in db.execute("SELECT key, value FROM job_radar_settings")}
    return {
        "source_url": values.get("source_url", DEFAULT_TENCENT_SOURCE),
        "auto_sync": values.get("auto_sync", "true").lower() == "true",
        "auto_sync_time": "06:00",
    }


def get_stats(db_path: Path = DB_PATH) -> dict[str, Any]:
    with _connect(db_path) as db:
        total = db.execute("SELECT COUNT(*) FROM job_postings WHERE status='active'").fetchone()[0]
        companies = db.execute("SELECT COUNT(DISTINCT company) FROM job_postings WHERE status='active'").fetchone()[0]
        last_run = db.execute("SELECT * FROM job_sync_runs ORDER BY created_at DESC LIMIT 1").fetchone()
        favorites = db.execute("SELECT COUNT(*) FROM job_radar_actions WHERE favorite=1").fetchone()[0]
    return {"total": total, "companies": companies, "favorites": favorites,
            "last_sync": dict(last_run) if last_run else None, "schedule": get_radar_settings(db_path)}
