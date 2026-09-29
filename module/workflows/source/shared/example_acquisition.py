"""Immutable source acquisition. Model-authored prose is never a webpage original."""
from __future__ import annotations

import hashlib
import html
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

CONTRACT = "frontmind-acquired-source/v1"

class AcquisitionError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def normalized(text):
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def public_url(url):
    """Disallow local endpoints, credentials and unsupported schemes, including redirects."""
    parsed = urlsplit(str(url))
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise AcquisitionError("web URL must be a public HTTP(S) URL without credentials")
    if parsed.port and parsed.port not in {80, 443}:
        raise AcquisitionError("web URL port is not allowed")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise AcquisitionError("web hostname could not be resolved") from exc
    for entry in addresses:
        address = ipaddress.ip_address(entry[4][0])
        if not address.is_global:
            raise AcquisitionError("web URL resolves to a non-public address")
    return str(url)


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, public_url(newurl))


class ArticleParser(HTMLParser):
    """Extract an explicitly delimited article; do not infer completeness by word count."""
    BLOCKS = {"p", "div", "section", "article", "main", "h1", "h2", "h3", "h4", "li", "br", "tr"}
    SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "button", "noscript"}
    TOKENS = {"article-body", "article-content", "entry-content", "post-content", "blog-content", "content-body", "richtext", "rich-content"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.candidates = []
        self.title = []
        self.body_text = []
        self.in_title = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tokens = set(re.split(r"\s+", attrs.get("class", "") + " " + attrs.get("id", "")))
        selected = tag in {"article", "main"} or attrs.get("itemprop") == "articleBody" or bool(tokens & self.TOKENS)
        skip = tag in self.SKIP or bool(tokens & {"comments", "comment-list", "advertisement", "advert", "ads"})
        node = {"tag": tag, "selected": selected, "skip": skip, "text": [], "closed": False}
        if tag not in {"br", "img", "meta", "input", "link", "hr", "source"}:
            self.stack.append(node)
        if selected:
            self.candidates.append(node)
        if tag == "title":
            self.in_title = True
        if tag in self.BLOCKS:
            self._text("\n\n")
    def _text(self, text):
        if any(n["skip"] for n in self.stack):
            return
        for node in self.stack:
            if node["selected"]:
                node["text"].append(text)
        self.body_text.append(text)
    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        self._text(data)
    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in self.BLOCKS:
            self._text("\n\n")
        for index in range(len(self.stack)-1, -1, -1):
            if self.stack[index]["tag"] == tag:
                self.stack[index]["closed"] = True
                del self.stack[index:]
                break
    def result(self):
        candidates = [n for n in self.candidates if n["closed"]]
        # Prefer an inner explicit article body over an enclosing navigation-bearing main.
        chosen = max(candidates, key=lambda n: (n["tag"] not in {"main", "article"}, len("".join(n["text"])))) if candidates else None
        text = "".join(chosen["text"] if chosen else self.body_text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()
        return text, bool(chosen), "".join(self.title).strip()


def page_problem(text, title="", status=200):
    if status != 200:
        return "HTTP status %s" % status
    if not str(text).strip():
        return "empty body"
    # Check page identity and prominent gates; not individual mentions inside an article.
    lead = (str(title) + "\n" + str(text)[:300]).lower()
    patterns = [r"^\s*(403|404|500)\b", r"access denied", r"forbidden", r"page not found", r"checking your browser", r"just a moment", r"verify (?:you are|that you are) human", r"请登录后(?:查看|阅读)", r"登录后继续阅读", r"扫码登录后", r"页面不存在", r"访问过于频繁", r"安全验证", r"enable javascript and cookies"]
    if any(re.search(p, lead, re.M) for p in patterns):
        return "error, login, or anti-bot page"
    if re.search(r"阅读全文|read (?:the )?full article|subscribe to (?:continue|read)|继续阅读请", str(text)[-500:], re.I):
        return "article ending indicates omitted content"
    return ""


class ExampleStore:
    def __init__(self, job_root):
        self.job_root = Path(job_root).resolve()
        self.root = self.job_root / "artifacts" / "acquired_sources"
        for candidate in [self.job_root / "artifacts", self.root]:
            if candidate.is_symlink():
                raise AcquisitionError("source store cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)

    def _save(self, raw, text, metadata):
        text = normalized(text)
        identity = {k: metadata.get(k) for k in ["obtained_via", "original_url", "final_url", "title", "http_status", "completeness", "integrity_note"]}
        identity.update(raw_sha256=digest(raw), text_sha256=digest(text))
        artifact_id = "src_" + digest(json.dumps(identity, sort_keys=True, ensure_ascii=False))[:24]
        destination = self.root / artifact_id
        if destination.is_symlink():
            raise AcquisitionError("source destination cannot be a symlink")
        if destination.exists():
            return self.resolve(artifact_id, require_complete=False)
        raw_path, text_path = destination / "raw.bin", destination / "body.md"
        record = dict(metadata, source_date=metadata.get("source_date"), published_at=metadata.get("published_at"), schema=CONTRACT, artifact_id=artifact_id, acquired_at=datetime.now(timezone.utc).isoformat(),
                      raw_path=raw_path.relative_to(self.job_root).as_posix(), text_path=text_path.relative_to(self.job_root).as_posix(),
                      raw_sha256=digest(raw), text_sha256=digest(text), char_count=len(text), beginning=text[:200], ending=text[-200:])
        staging = Path(tempfile.mkdtemp(prefix=".source-", dir=self.root))
        try:
            (staging / "raw.bin").write_bytes(raw)
            (staging / "body.md").write_text(text, encoding="utf-8")
            atomic_json(staging / "record.json", record)
            for p in staging.iterdir():
                p.chmod(0o444)
            os.replace(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return record

    def import_user_text(self, text, title="User supplied example", source_url=None, completeness="complete"):
        if not isinstance(text, str) or not text.strip():
            raise AcquisitionError("user text is empty")
        if completeness not in {"complete", "partial"}:
            raise AcquisitionError("unsupported user completeness")
        problem = page_problem(text, title)
        return self._save(text.encode("utf-8"), normalized(text), dict(
            obtained_via="user_text", original_url=source_url, final_url=None, title=title,
            content_type="text/markdown", http_status=None,
            completeness="partial" if problem else completeness,
            acquisition_status="complete" if completeness == "complete" and not problem else "incomplete",
            integrity_note=problem or "User supplied full text; line endings normalized only. Attached URL is attribution, not proof of webpage acquisition."))

    def import_user_file(self, path, title=None, source_url=None, completeness="complete"):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise AcquisitionError("user example must be a regular file")
        if path.suffix.lower() not in {".md", ".txt"}:
            raise AcquisitionError("submit an extracted plain-text example (.md or .txt)")
        return self.import_user_text(path.read_text(encoding="utf-8-sig"), title or path.stem, source_url, completeness)

    def acquire_http(self, url, *, encoding=None, article_tokens=()):
        url = public_url(url)
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 FrontMind/4.11.5", "Accept": "text/html,text/plain;q=0.8"})
        try:
            with build_opener(SafeRedirect).open(request, timeout=300) as response:
                raw, status, final_url, content_type = response.read(), response.status, response.geturl(), response.headers.get("Content-Type", "")
        except HTTPError as exc:
            raw, status, final_url, content_type = exc.read(), exc.code, exc.geturl(), exc.headers.get("Content-Type", "")
        except (URLError, TimeoutError, OSError) as exc:
            raise AcquisitionError("HTTP acquisition failed (%s)" % type(exc).__name__) from exc
        public_url(final_url)
        charset = re.search(r"charset=([\w-]+)", content_type, re.I)
        try:
            body = raw.decode(encoding or (charset.group(1) if charset else "utf-8"))
        except (UnicodeDecodeError, LookupError):
            return self._save(raw, "", dict(obtained_via="http", original_url=url, final_url=final_url, title="", http_status=status, content_type=content_type, completeness="partial", acquisition_status="incomplete", integrity_note="Unsupported or invalid text encoding"))
        parser = ArticleParser()
        if article_tokens:
            parser.TOKENS = parser.TOKENS | set(article_tokens)
        parser.feed(body)
        text, article_closed, title = parser.result()
        problem = page_problem(text, title, status)
        if not article_closed and not problem:
            problem = "No complete, explicitly delimited article region found"
        return self._save(raw, text, dict(obtained_via="http", original_url=url, final_url=final_url, title=title, http_status=status, content_type=content_type, article_region_closed=article_closed, completeness="partial" if problem else "complete", acquisition_status="incomplete" if problem else "complete", integrity_note=problem or "Text extracted from a closed article region; menus, scripts and page controls removed, no rewriting."))

    def acquire_reader(self, url, request_json):
        public_url(url)
        response = request_json("reader", {"url": url, "return_format": "markdown", "retain_images": False, "with_links_summary": False, "with_images_summary": False})
        # Official Reader supplies reader_result/content; tolerate wrapper versions without silently using summaries.
        value = response.get("reader_result", response.get("data", response))
        if isinstance(value, list):
            value = value[0] if len(value) == 1 else {}
        if isinstance(value, str):
            value = {"content": value}
        text = value.get("content", value.get("markdown", "")) if isinstance(value, dict) else ""
        if not isinstance(text, str):
            text = ""
        title = value.get("title", "") if isinstance(value, dict) else ""
        final_url = value.get("url", url) if isinstance(value, dict) else url
        public_url(final_url)
        problem = page_problem(text, title)
        if isinstance(value, dict) and (value.get("is_truncated") or value.get("truncated") or value.get("is_summary") or value.get("content_type") in {"summary", "snippet", "search_result"} or value.get("status") in {"partial", "error", "failed"}):
            problem = "Reader reported incomplete or failed content"
        # Reader is extraction; retain complete text and provenance, never claim raw HTML.
        return self._save(json.dumps(response, ensure_ascii=False).encode("utf-8"), text, dict(obtained_via="zhipu_reader", original_url=url, final_url=final_url, title=title, http_status=None, content_type="application/json", completeness="partial" if problem else "complete", acquisition_status="incomplete" if problem else "complete", integrity_note=problem or "Reader returned article text with summaries disabled; raw artifact is the Reader JSON response, not origin HTML."))

    def resolve(self, artifact_id, require_complete=True):
        if not isinstance(artifact_id, str) or not re.fullmatch(r"src_[a-f0-9]{24}", artifact_id):
            raise AcquisitionError("invalid acquired artifact ID")
        destination = self.root / artifact_id
        if destination.is_symlink():
            raise AcquisitionError("acquired artifact is a symlink")
        try:
            record = json.loads((destination / "record.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AcquisitionError("acquired artifact record is missing or invalid") from exc
        for key, hash_key in [("raw_path", "raw_sha256"), ("text_path", "text_sha256")]:
            path = self.job_root / record.get(key, "")
            if path.is_symlink() or not path.is_file() or path.resolve().parent != destination:
                raise AcquisitionError("acquired artifact path escaped its immutable record")
            if digest(path.read_bytes()) != record.get(hash_key):
                raise AcquisitionError("acquired artifact hash changed")
        if record.get("schema") != CONTRACT or record.get("artifact_id") != artifact_id:
            raise AcquisitionError("invalid acquired source contract")
        if require_complete and (record.get("completeness") != "complete" or record.get("acquisition_status") != "complete"):
            raise AcquisitionError("example acquisition is incomplete: " + record.get("integrity_note", "unknown"))
        return record
