"""제미나이: 후보 논문이 정말 'SIB 하드카본 음극재' 주제인지 판단하고 한국어로 요약."""
import json
import os

from common import HttpError, http, log, truncate

BASE = "https://generativelanguage.googleapis.com/v1beta"

PROMPT = """너는 나트륨이온전지(SIB) 하드카본 음극재를 연구하는 화공생물공학과 학부연구생의 논문 비서야.
아래 논문 후보들을 보고 각각 판단해서 JSON 배열로만 답해.

판단 기준
- relevant: SIB(또는 SIB와 LIB 비교) 하드카본 음극재가 논문의 핵심 주제면 true. 단순 언급, 양극재, 전해질만 다루면 false.
- score: 0~10. 주제 적합도 + 새로운 아이디어/메커니즘 규명/성능 개선 정도. 리뷰 논문도 좋으면 높게.
- summary_ko: 한국어 한 줄 요약(80자 이내). 전구체, 합성 조건(탄화 온도 등), 핵심 성능(용량, ICE, 사이클)을 숫자 위주로. 초록에 없는 숫자는 지어내지 마.
- key_points: 한국어 핵심 포인트 2~4개(각 60자 이내). 초록에 근거한 내용만.
- why_read: 이 논문을 읽으면 좋은 이유 한 문장(한국어).
- 초록이 비어 있으면 제목만 보고 판단하고 summary_ko 앞에 "(초록 없음)"을 붙여.

출력 형식: [{{"id": "...", "relevant": true, "score": 8, "summary_ko": "...", "key_points": ["..."], "why_read": "..."}}]

논문 후보:
{items}
"""


def _pick_model(key):
    """설정한 모델이 없어졌을 때(이름 변경 등) 사용 가능한 flash 모델을 자동으로 고름."""
    data = http("GET", f"{BASE}/models", headers={"x-goog-api-key": key}, params={"pageSize": 200})
    names = [m["name"].split("/")[-1] for m in data.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    flash = [n for n in names if "flash" in n and "lite" not in n and "image" not in n
             and "tts" not in n and "live" not in n]
    choice = (flash or names or [None])[0]
    log("제미나이 모델 자동 선택:", choice)
    return choice


def _generate(key, model, prompt):
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    data = http("POST", f"{BASE}/models/{model}:generateContent",
                headers={"x-goog-api-key": key}, json_body=body, timeout=120)
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def review(papers, cfg):
    """papers 리스트를 받아 각 논문에 relevant/score/summary_ko 등을 붙여서 돌려줌.
    제미나이 키가 없거나 실패하면 키워드 필터 결과만 사용(요약 없이)."""
    key = os.environ.get("GEMINI_API_KEY")
    if not papers:
        return []
    if not key:
        log("GEMINI_API_KEY 없음 → 요약 없이 진행")
        for p in papers:
            p.update(relevant=True, score=None, summary_ko="", key_points=[], why_read="")
        return papers

    model = cfg.get("gemini_model", "gemini-flash-latest")
    results = {}
    for start in range(0, len(papers), 15):  # 15편씩 나눠서 요청
        chunk = papers[start:start + 15]
        items = "\n\n".join(
            f"id: {p['doi']}\n제목: {p['title']}\n저널: {p['journal']}\n초록: {truncate(p['abstract'], 1800) or '(없음)'}"
            for p in chunk)
        prompt = PROMPT.format(items=items)
        try:
            try:
                text = _generate(key, model, prompt)
            except HttpError as e:
                if e.status != 404:
                    raise
                model = _pick_model(key)
                text = _generate(key, model, prompt)
            for r in json.loads(text):
                results[str(r.get("id", "")).lower()] = r
        except Exception as e:
            log("제미나이 요청 실패 → 이 묶음은 요약 없이 진행:", e)

    out = []
    for p in papers:
        r = results.get(p["doi"])
        if r is None:
            p.update(relevant=True, score=None, summary_ko="", key_points=[], why_read="")
        else:
            p.update(relevant=bool(r.get("relevant")),
                     score=r.get("score"),
                     summary_ko=r.get("summary_ko", ""),
                     key_points=r.get("key_points", [])[:4],
                     why_read=r.get("why_read", ""))
        out.append(p)
    return out
