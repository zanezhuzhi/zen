from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import logging
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
VAULT_DIR = Path(r"D:\==我的学习库==")
CONFIG_FILE = VAULT_DIR / "90_系统" / "config" / "wechat.yaml"


def parse_simple_yaml(path: Path) -> dict[str, str | int]:
    data: dict[str, str | int] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip('"').strip("'")
        if value.isdigit():
            data[key.strip()] = int(value)
        else:
            data[key.strip()] = value
    return data


CONFIG = parse_simple_yaml(CONFIG_FILE)
TOKEN = str(CONFIG["token"])
CALLBACK_PATH = str(CONFIG.get("callback_path", "/wechat/callback"))
HOST = str(CONFIG.get("host", "127.0.0.1"))
PORT = int(CONFIG.get("port", 8000))
INBOX_DIR = Path(str(CONFIG["inbox_dir"]))
LOG_FILE = Path(str(CONFIG["log_file"]))

INBOX_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


def verify_signature(signature: str, timestamp: str, nonce: str) -> bool:
    values = [TOKEN, timestamp, nonce]
    digest = hashlib.sha1("".join(sorted(values)).encode("utf-8")).hexdigest()
    return digest == signature


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def safe_text(value: str | None) -> str:
    return html.unescape(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>\"]+", text)


def parse_message(xml_body: bytes) -> dict[str, str]:
    root = ET.fromstring(xml_body)
    data = {child.tag: safe_text(child.text) for child in root}
    return data


def markdown_escape_block(text: str) -> str:
    if not text:
        return ""
    return text.replace("```", "` ` `")


def append_message_to_daily_note(message: dict[str, str]) -> Path:
    received_at = now_local()
    note_path = INBOX_DIR / f"{received_at:%Y-%m-%d}.md"
    msg_type = message.get("MsgType", "unknown")
    from_user = message.get("FromUserName", "")
    to_user = message.get("ToUserName", "")
    content = message.get("Content", "")
    title = message.get("Title", "")
    description = message.get("Description", "")
    url = message.get("Url", "")
    pic_url = message.get("PicUrl", "")
    media_id = message.get("MediaId", "")
    urls = extract_urls("\n".join([content, url, description, pic_url]))

    if not note_path.exists():
        note_path.write_text(
            f"# 公众号同步 {received_at:%Y-%m-%d}\n\n",
            encoding="utf-8",
        )

    lines = [
        "---",
        f"## {received_at:%H:%M:%S} {msg_type}",
        "",
        f"- received_at: {received_at.isoformat(timespec='seconds')}",
        f"- from_openid: `{from_user}`",
        f"- to_account: `{to_user}`",
        f"- msg_id: `{message.get('MsgId', '')}`",
        f"- status: received",
    ]
    if title:
        lines.append(f"- title: {title}")
    if url:
        lines.append(f"- url: {url}")
    if pic_url:
        lines.append(f"- pic_url: {pic_url}")
    if media_id:
        lines.append(f"- media_id: `{media_id}`")
    if urls:
        lines.extend(["", "### Links"])
        lines.extend(f"- {item}" for item in sorted(set(urls)))
    if description:
        lines.extend(["", "### Description", markdown_escape_block(description)])
    if content:
        lines.extend(["", "### Content", "```text", markdown_escape_block(content), "```"])
    lines.append("")

    with note_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
        f.write("\n")
    return note_path


def wechat_text_response(to_user: str, from_user: str, content: str) -> bytes:
    created = int(time.time())
    escaped = html.escape(content)
    xml = f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{created}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{escaped}]]></Content>
</xml>"""
    return xml.encode("utf-8")


class WeChatHandler(BaseHTTPRequestHandler):
    server_version = "KnowledgeWechatReceiver/0.1"

    def log_message(self, format: str, *args: object) -> None:
        logging.info("%s - %s", self.address_string(), format % args)

    def send_plain(self, status: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            payload = {
                "ok": True,
                "service": "wechat_receiver",
                "callback_path": CALLBACK_PATH,
                "inbox_dir": str(INBOX_DIR),
                "time": now_local().isoformat(timespec="seconds"),
            }
            self.send_plain(200, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if parsed.path != CALLBACK_PATH:
            self.send_plain(404, "not found")
            return

        query = urllib.parse.parse_qs(parsed.query)
        signature = query.get("signature", [""])[0]
        timestamp = query.get("timestamp", [""])[0]
        nonce = query.get("nonce", [""])[0]
        echostr = query.get("echostr", [""])[0]

        if verify_signature(signature, timestamp, nonce):
            logging.info("wechat GET verification passed")
            self.send_plain(200, echostr)
        else:
            logging.warning("wechat GET verification failed: signature=%s timestamp=%s nonce=%s", signature, timestamp, nonce)
            self.send_plain(403, "signature verification failed")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_plain(404, "not found")
            return

        query = urllib.parse.parse_qs(parsed.query)
        signature = query.get("signature", [""])[0]
        timestamp = query.get("timestamp", [""])[0]
        nonce = query.get("nonce", [""])[0]
        if signature and not verify_signature(signature, timestamp, nonce):
            logging.warning("wechat POST verification failed")
            self.send_plain(403, "signature verification failed")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            message = parse_message(body)
            note_path = append_message_to_daily_note(message)
            logging.info("saved message type=%s to %s", message.get("MsgType", "unknown"), note_path)
            reply = wechat_text_response(
                to_user=message.get("FromUserName", ""),
                from_user=message.get("ToUserName", ""),
                content="已收录",
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)
        except Exception:
            logging.exception("failed to handle wechat POST")
            self.send_plain(500, "failed")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), WeChatHandler)
    logging.info("wechat receiver listening on http://%s:%s", HOST, PORT)
    logging.info("callback path: %s", CALLBACK_PATH)
    server.serve_forever()


if __name__ == "__main__":
    main()
