"""공통 도구: HTTP 요청, 파일 읽기/쓰기, 텍스트 정리 (파이썬 기본 라이브러리만 사용)."""
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KST = timezone(timedelta(hours=9))

PAPERS_PATH = os.path.join(ROOT, "docs", "papers.json")      # 웹사이트가 읽는 논문 저장소
STATE_PATH = os.path.join(ROOT, "data", "state.json")         # 노션 DB id 등 상태
JOURNALS_PATH = os.path.join(ROOT, "data", "journals.json")   # 저널 IF 캐시
LAST_RUN_PATH = os.path.join(ROOT, "data", "last_run.json")   # 오늘 새로 추가된 논문 목록


def now_kst():
    return datetime.now(KST)


def today_str():
    return now_kst().strftime("%Y-%m-%d")


def log(*args):
    print(f"[{now_kst().strftime('%H:%M:%S')}]", *args, flush=True)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_config():
    return load_json(os.path.join(ROOT, "config.json"), {})


class HttpError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {str(body)[:500]}")
        self.status = status
        self.body = body


def http(method, url, *, params=None, headers=None, json_body=None, form=None,
         timeout=40, retries=3):
    """JSON을 주고받는 간단한 HTTP 함수. 429/5xx는 잠깐 기다렸다 다시 시도."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = dict(headers or {})
    headers.setdefault("User-Agent", "sib-paper-bot/1.0 (GitHub Actions)")
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"

    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_err = HttpError(e.code, body)
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise last_err
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise last_err


def strip_tags(text):
    """Crossref 초록에 섞인 <jats:p> 같은 태그 제거."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def norm_doi(doi):
    if not doi:
        return ""
    doi = doi.strip().lower()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi)
    return doi


def norm_title(title):
    """제목 비교용: 소문자 + 영문/숫자만 남김 → 같은 논문이 다른 DOI로 와도 걸러냄."""
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def truncate(text, n):
    text = text or ""
    return text if len(text) <= n else text[: n - 1] + "…"
