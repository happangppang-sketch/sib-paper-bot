"""논문 출처: Crossref(실제 출판 기록 DB, 키 불필요)에서 논문을 찾고,
OpenAlex에서 저널의 '2년 평균 인용수'(임팩트팩터와 같은 방식의 근사값)를 가져온다.

※ 제미나이가 기억으로 논문을 '지어내는' 일을 막기 위해, 논문 목록 자체는
   반드시 Crossref 같은 실제 DB에서 가져오고 제미나이는 판단·요약만 맡는다.
"""
import os
from datetime import timedelta

from common import (JOURNALS_PATH, HttpError, http, load_json, log, now_kst,
                    norm_doi, save_json, strip_tags)

CROSSREF = "https://api.crossref.org/works"
SELECT = "DOI,title,container-title,ISSN,published,published-online,published-print,issued,author,abstract,URL,is-referenced-by-count,type"


def _date_of(item):
    for key in ("published-online", "published-print", "published", "issued"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            p = parts[0] + [1, 1]
            return f"{p[0]:04d}-{p[1]:02d}-{p[2]:02d}"
    return ""


def _to_paper(item):
    title = strip_tags(" ".join(item.get("title") or []))
    authors = []
    for a in (item.get("author") or [])[:6]:
        name = " ".join(x for x in (a.get("given"), a.get("family")) if x)
        if name:
            authors.append(name)
    if len(item.get("author") or []) > 6:
        authors.append("et al.")
    doi = norm_doi(item.get("DOI"))
    return {
        "doi": doi,
        "title": title,
        "journal": strip_tags(" ".join(item.get("container-title") or [])),
        "issn": (item.get("ISSN") or [""])[0],
        "published": _date_of(item),
        "authors": authors,
        "abstract": strip_tags(item.get("abstract") or ""),
        "url": f"https://doi.org/{doi}" if doi else item.get("URL", ""),
        "citations": item.get("is-referenced-by-count", 0),
    }


def _crossref(query, rows, sort, from_date, until_date=None):
    filt = f"from-pub-date:{from_date},type:journal-article"
    if until_date:
        filt += f",until-pub-date:{until_date}"
    params = {
        "query.bibliographic": query,
        "filter": filt,
        "sort": sort,
        "order": "desc",
        "rows": rows,
        "select": SELECT,
    }
    mailto = os.environ.get("CROSSREF_MAILTO")
    if mailto:
        params["mailto"] = mailto  # Crossref 'polite pool' (더 안정적)
    data = http("GET", CROSSREF, params=params)
    return [_to_paper(it) for it in data.get("message", {}).get("items", [])]


def keyword_ok(paper, cfg):
    text = f"{paper['title']} {paper['abstract']}".lower()
    a = any(k in text for k in cfg["must_have_any"])
    b = any(k in text for k in cfg["and_any"])
    return a and b and bool(paper["title"]) and bool(paper["doi"])


def search_recent(cfg):
    """최근 lookback_days 일 안에 나온 논문 검색."""
    from_date = (now_kst() - timedelta(days=cfg["lookback_days"])).strftime("%Y-%m-%d")
    found = {}
    for q in cfg["search_queries"]:
        try:
            for p in _crossref(q, rows=60, sort="published", from_date=from_date):
                if keyword_ok(p, cfg):
                    found.setdefault(p["doi"], p)
        except Exception as e:  # 하나 실패해도 나머지 검색은 계속
            log("Crossref 검색 실패:", q, e)
    log(f"최신 후보 {len(found)}편 (키워드 1차 필터 통과)")
    return list(found.values())


def search_classics(cfg):
    """새 논문이 없을 때: 최근 N년 안의 많이 인용된(읽을 가치 있는) 논문."""
    now = now_kst()
    from_date = f"{now.year - cfg['fallback_years']}-01-01"
    until = (now - timedelta(days=cfg["lookback_days"])).strftime("%Y-%m-%d")
    found = {}
    for q in cfg["search_queries"]:
        try:
            for p in _crossref(q, rows=60, sort="is-referenced-by-count",
                               from_date=from_date, until_date=until):
                if keyword_ok(p, cfg):
                    found.setdefault(p["doi"], p)
        except Exception as e:
            log("Crossref(추천) 검색 실패:", q, e)
    papers = sorted(found.values(), key=lambda p: p["citations"], reverse=True)
    log(f"추천 후보 {len(papers)}편")
    return papers


# ---------------- 임팩트팩터 ----------------

def impact_for(paper, cfg, cache):
    """1순위: config.json의 공식 IF 직접 입력값 / 2순위: OpenAlex 2년 평균 인용수."""
    override = cfg.get("impact_factor_override", {})
    for name, val in override.items():
        if not name.startswith("_") and name.lower() == paper["journal"].lower():
            return round(float(val), 1), "JCR(직접 입력)"

    issn = paper.get("issn")
    if not issn:
        return None, None
    entry = cache.get(issn)
    fresh = entry and entry.get("checked", "") >= (now_kst() - timedelta(days=90)).strftime("%Y-%m-%d")
    if not fresh:
        key = os.environ.get("OPENALEX_API_KEY")
        if not key:
            return (entry or {}).get("value"), "OpenAlex 2년 평균 인용수" if entry else None
        try:
            data = http("GET", f"https://api.openalex.org/sources/issn:{issn}",
                        params={"api_key": key, "select": "display_name,summary_stats"})
            val = (data.get("summary_stats") or {}).get("2yr_mean_citedness")
            entry = {"value": round(val, 1) if val is not None else None,
                     "journal": data.get("display_name"),
                     "checked": now_kst().strftime("%Y-%m-%d")}
        except HttpError as e:
            log("OpenAlex 조회 실패:", issn, e.status)
            entry = {"value": None, "checked": now_kst().strftime("%Y-%m-%d")}
        cache[issn] = entry
    if entry.get("value") is None:
        return None, None
    return entry["value"], "OpenAlex 2년 평균 인용수"


def load_journal_cache():
    return load_json(JOURNALS_PATH, {})


def save_journal_cache(cache):
    save_json(JOURNALS_PATH, cache)
