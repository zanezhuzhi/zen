from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
VAULT_DIR = BASE_DIR.parent.parent
CONFIG_DIR = VAULT_DIR / "90_系统" / "config"
FEEDBACK_PATH = CONFIG_DIR / "daily_collect_feedback.json"
OUTPUT_DIR = VAULT_DIR / "00_入口收件箱" / "每日信息候选"
SUMMARY_PATH = OUTPUT_DIR / "筛选反馈.md"


def today_string() -> str:
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def parse_scalar(body: str, key: str) -> str:
    pattern = re.compile(rf"^- {re.escape(key)}: (.*)$", re.M)
    match = pattern.search(body)
    return match.group(1).strip().strip("`") if match else ""


def parse_list_value(value: str) -> list[str]:
    if not value or value == "-":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def checked(body: str, label: str, item_id: str) -> bool:
    pattern = re.compile(rf"^- \[[xX]\] {re.escape(label)} `{re.escape(item_id)}`\s*$", re.M)
    return bool(pattern.search(body))


def parse_candidates(note_text: str) -> list[dict[str, Any]]:
    blocks = re.finditer(r"^### \d+\. (?P<title>.*?)\n(?P<body>.*?)(?=^### \d+\. |^## |\Z)", note_text, re.M | re.S)
    candidates: list[dict[str, Any]] = []
    for match in blocks:
        body = match.group("body")
        item_id = parse_scalar(body, "id")
        if not item_id:
            continue
        keep = checked(body, "收录", item_id)
        drop = checked(body, "移除", item_id)
        if keep and drop:
            decision = "conflict"
        elif keep:
            decision = "keep"
        elif drop:
            decision = "drop"
        else:
            decision = ""
        candidates.append(
            {
                "id": item_id,
                "title": match.group("title").strip(),
                "domain": parse_scalar(body, "domain"),
                "host": parse_scalar(body, "host"),
                "source": parse_scalar(body, "source"),
                "url": parse_scalar(body, "url"),
                "matched_keywords": parse_list_value(parse_scalar(body, "matched_keywords")),
                "cautious_keywords": parse_list_value(parse_scalar(body, "cautious_keywords")),
                "decision": decision,
            }
        )
    return candidates


def increment(bucket: dict[str, Any], key: str, decision: str) -> None:
    if not key or key == "-":
        return
    stat = bucket.setdefault(key, {"keep": 0, "drop": 0})
    stat[decision] = int(stat.get(decision, 0)) + 1


def apply_candidate(feedback: dict[str, Any], candidate: dict[str, Any], date: str) -> bool:
    decision = candidate.get("decision")
    if decision not in {"keep", "drop"}:
        return False

    item_id = candidate["id"]
    decisions = feedback.setdefault("decisions", {})
    previous = decisions.get(item_id, {}).get("decision")
    if previous == decision:
        return False

    if previous in {"keep", "drop"}:
        # Keep the data monotonic and auditable: changed opinions are recorded
        # as a new event instead of subtracting old counters.
        feedback.setdefault("changed_decisions", []).append(
            {
                "id": item_id,
                "from": previous,
                "to": decision,
                "changed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )

    decisions[item_id] = {
        "decision": decision,
        "date": date,
        "title": candidate.get("title", ""),
        "domain": candidate.get("domain", ""),
        "host": candidate.get("host", ""),
        "url": candidate.get("url", ""),
    }

    increment(feedback.setdefault("domains", {}), candidate.get("domain", ""), decision)
    increment(feedback.setdefault("hosts", {}), candidate.get("host", ""), decision)
    for keyword in candidate.get("matched_keywords", []):
        increment(feedback.setdefault("terms", {}), keyword, decision)
    for keyword in candidate.get("cautious_keywords", []):
        increment(feedback.setdefault("cautious_terms", {}), keyword, decision)
    feedback.setdefault("events", []).append(
        {
            "date": date,
            "decision": decision,
            "id": item_id,
            "domain": candidate.get("domain", ""),
            "host": candidate.get("host", ""),
            "title": candidate.get("title", ""),
        }
    )
    return True


def sort_stats(stats: dict[str, Any]) -> list[tuple[str, int, int]]:
    rows = []
    for key, value in stats.items():
        keep = int(value.get("keep", 0))
        drop = int(value.get("drop", 0))
        rows.append((key, keep, drop))
    return sorted(rows, key=lambda item: (-(item[1] + item[2]), item[0]))


def render_summary(feedback: dict[str, Any]) -> str:
    lines = [
        "---",
        "type: filter-feedback",
        "status: private",
        "tags:",
        "  - daily-domain-brief",
        "---",
        "",
        "# 筛选反馈",
        "",
        f"- updated_at: {feedback.get('updated_at', '-')}",
        f"- total_decisions: {len(feedback.get('decisions', {}))}",
        "",
        "## 领域偏好",
        "| 领域 | 收录 | 移除 |",
        "| --- | ---: | ---: |",
    ]
    for key, keep, drop in sort_stats(feedback.get("domains", {}))[:20]:
        lines.append(f"| {key} | {keep} | {drop} |")
    lines.extend(["", "## 来源偏好", "| 来源 | 收录 | 移除 |", "| --- | ---: | ---: |"])
    for key, keep, drop in sort_stats(feedback.get("hosts", {}))[:30]:
        lines.append(f"| {key} | {keep} | {drop} |")
    lines.extend(["", "## 关键词偏好", "| 关键词 | 收录 | 移除 |", "| --- | ---: | ---: |"])
    for key, keep, drop in sort_stats(feedback.get("terms", {}))[:40]:
        lines.append(f"| {key} | {keep} | {drop} |")
    lines.append("")
    return "\n".join(lines)


def apply_feedback(date: str) -> tuple[Path, str]:
    note_path = OUTPUT_DIR / f"{date}.md"
    if not note_path.exists():
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        message = f"daily domain brief not found, skipped: {note_path}"
        SUMMARY_PATH.write_text(message + "\n", encoding="utf-8", newline="\n")
        return SUMMARY_PATH, "skipped=missing-brief"

    feedback = load_json(
        FEEDBACK_PATH,
        {
            "version": 1,
            "decisions": {},
            "domains": {},
            "hosts": {},
            "terms": {},
            "cautious_terms": {},
            "events": [],
        },
    )
    candidates = parse_candidates(note_path.read_text(encoding="utf-8"))
    changed = 0
    conflicts = 0
    for candidate in candidates:
        if candidate.get("decision") == "conflict":
            conflicts += 1
            continue
        if apply_candidate(feedback, candidate, date):
            changed += 1

    feedback["updated_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    write_json(FEEDBACK_PATH, feedback)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(render_summary(feedback), encoding="utf-8", newline="\n")
    return SUMMARY_PATH, f"candidates={len(candidates)} changed={changed} conflicts={conflicts}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply keep/drop decisions from the daily domain brief.")
    parser.add_argument("--date", default=today_string(), help="Date in YYYY-MM-DD format. Defaults to today.")
    args = parser.parse_args()
    output_path, summary = apply_feedback(args.date)
    print(f"updated {output_path} ({summary})")


if __name__ == "__main__":
    main()
