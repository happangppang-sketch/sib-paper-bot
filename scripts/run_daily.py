"""매일 실행되는 본체.

  python scripts/run_daily.py collect   # 논문 수집 → 중복 제거 → 제미나이 요약 → 저장 → 노션
  python scripts/run_daily.py notify    # (웹사이트 반영 후) 카카오톡 알림
"""
import sys
from datetime import timedelta

import gemini
import kakao
import notion
import sources
from common import (LAST_RUN_PATH, PAPERS_PATH, load_config, load_json, log,
                    norm_doi, norm_title, now_kst, save_json, today_str)


def load_store():
    return load_json(PAPERS_PATH, {"updated": None, "papers": []})


def is_duplicate(p, seen_dois, seen_titles):
    return norm_doi(p["doi"]) in seen_dois or norm_title(p["title"]) in seen_titles


def pick(candidates, cfg, seen_dois, seen_titles, limit, kind):
    """중복 제거 → 제미나이 판단 → 점수순으로 limit개."""
    fresh, batch_titles = [], set()
    for p in candidates:
        t = norm_title(p["title"])
        if is_duplicate(p, seen_dois, seen_titles) or t in batch_titles:
            continue
        batch_titles.add(t)
        fresh.append(p)
    log(f"[{kind}] 저장소와 겹치지 않는 후보 {len(fresh)}편")
    if not fresh:
        return []
    # 제미나이 요청량을 아끼기 위해 상위 일부만 검토
    fresh = fresh[: max(limit * 6, 15)]
    reviewed = gemini.review(fresh, cfg)
    min_score = cfg.get("min_relevance_score", 6)
    good = [p for p in reviewed if p["relevant"] and (p["score"] is None or p["score"] >= min_score)]
    if kind == "new":
        good.sort(key=lambda p: ((p["score"] or 0), p["published"]), reverse=True)
    else:
        good.sort(key=lambda p: ((p["score"] or 0), p["citations"]), reverse=True)
    return good[:limit]


def attach_impact(papers, cfg, cache):
    """IF 붙이기: 1순위 config.json 직접 입력값, 2순위 제미나이가 아는 JCR 값.
    제미나이 답은 저널별로 data/journals.json에 저장해 두고 180일 동안 재사용
    (매일 숫자가 바뀌지 않게)."""
    override = {k.lower(): v for k, v in cfg.get("impact_factor_override", {}).items()
                if not k.startswith("_")}
    stale_before = (now_kst() - timedelta(days=180)).strftime("%Y-%m-%d")
    need = sorted({p["journal"] for p in papers if p["journal"]
                   and p["journal"].lower() not in override
                   and cache.get("gemini:" + p["journal"].lower(), {}).get("checked", "") < stale_before})
    for name, val in gemini.journal_ifs(need, cfg).items():
        cache["gemini:" + name.lower()] = {"value": val, "journal": name, "checked": today_str()}
    for p in papers:
        j = p["journal"].lower()
        if j in override:
            p["impact"], p["impact_source"] = round(float(override[j]), 1), "JCR(직접 입력)"
        else:
            val = cache.get("gemini:" + j, {}).get("value")
            p["impact"] = val
            p["impact_source"] = "JCR 임팩트팩터(제미나이 답변, 추정)" if val is not None else None


def collect():
    cfg = load_config()
    store = load_store()
    seen_dois = {norm_doi(p["doi"]) for p in store["papers"]}
    seen_titles = {norm_title(p["title"]) for p in store["papers"]}

    chosen = pick(sources.search_recent(cfg), cfg, seen_dois, seen_titles,
                  cfg["max_new_per_day"], "new")
    for p in chosen:
        p["kind"] = "new"

    if not chosen and cfg.get("fallback_when_no_new", True):
        log("새 논문 없음 → 읽을 가치 있는 관련 논문을 찾음")
        classics = pick(sources.search_classics(cfg), cfg, seen_dois, seen_titles,
                        cfg["fallback_count"], "classic")
        for p in classics:
            p["kind"] = "classic"
        chosen = classics

    cache = sources.load_journal_cache()
    today = today_str()
    # 오늘 논문 + 예전에 IF가 비어 있던 논문까지 같이 채움
    attach_impact(chosen + [p for p in store["papers"] if p.get("impact") is None], cfg, cache)
    for p in chosen:
        p["added"] = today
        p["id"] = norm_title(p["title"])[:60]
        p.pop("relevant", None)
    sources.save_journal_cache(cache)

    notion.publish(chosen, cfg)

    store["papers"] = chosen + store["papers"]   # 최신이 위로
    store["updated"] = today
    save_json(PAPERS_PATH, store)
    save_json(LAST_RUN_PATH, {"date": today, "ids": [p["id"] for p in chosen]})
    log(f"완료: 새로 추가 {len(chosen)}편 / 누적 {len(store['papers'])}편")


def notify():
    cfg = load_config()
    store = load_store()
    last = load_json(LAST_RUN_PATH, {})
    if last.get("date") != today_str():
        log("오늘 수집 기록이 없음 → 알림 건너뜀")
        return
    ids = set(last.get("ids", []))
    new_papers = [p for p in store["papers"] if p["id"] in ids]
    kakao.notify(new_papers, cfg)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    {"collect": collect, "notify": notify}[cmd]()
