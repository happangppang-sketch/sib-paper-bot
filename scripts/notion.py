"""노션: 논문마다 페이지 하나씩 만들어 요약을 정리.

- NOTION_TOKEN: 노션 통합(Integration)의 시크릿
- NOTION_PARENT_PAGE_ID: 데이터베이스를 만들 노션 페이지 ID (처음 한 번만 필요)
  → 처음 실행 때 '논문 데이터베이스'를 자동으로 만들고 그 ID를 data/state.json에 저장
- 이미 만든 DB가 있으면 NOTION_DATABASE_ID로 지정해도 됨
"""
import os

from common import STATE_PATH, HttpError, http, load_json, log, save_json, truncate

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"


def _h(token):
    return {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}


def _txt(s):
    return [{"type": "text", "text": {"content": truncate(s or "", 1900)}}]


def _create_database(token, parent_id, title):
    body = {
        "parent": {"type": "page_id", "page_id": parent_id},
        "title": _txt(title),
        "is_inline": True,
        "properties": {
            "제목": {"title": {}},
            "저널": {"rich_text": {}},
            "IF": {"number": {"format": "number"}},
            "게재일": {"date": {}},
            "수집일": {"date": {}},
            "구분": {"select": {"options": [{"name": "최신", "color": "blue"},
                                           {"name": "추천", "color": "yellow"}]}},
            "관련도": {"number": {"format": "number"}},
            "DOI": {"url": {}},
            "읽음": {"checkbox": {}},
        },
    }
    data = http("POST", f"{API}/databases", headers=_h(token), json_body=body)
    log("노션 데이터베이스 생성:", data["id"])
    return data["id"]


def _database_id(token, cfg):
    if os.environ.get("NOTION_DATABASE_ID"):
        return os.environ["NOTION_DATABASE_ID"]
    state = load_json(STATE_PATH, {})
    if state.get("notion_database_id"):
        return state["notion_database_id"]
    parent = os.environ.get("NOTION_PARENT_PAGE_ID")
    if not parent:
        log("NOTION_PARENT_PAGE_ID 없음 → 노션 정리 건너뜀")
        return None
    db = _create_database(token, parent, f"📚 {cfg['topic_name']} 논문")
    state["notion_database_id"] = db
    save_json(STATE_PATH, state)
    return db


def _page_body(p):
    blocks = []

    def heading(t):
        blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": _txt(t)}})

    def para(t):
        blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": _txt(t)}})

    if p.get("summary_ko"):
        heading("📝 한 줄 요약")
        para(p["summary_ko"])
    if p.get("key_points"):
        heading("🔑 핵심 포인트")
        for k in p["key_points"]:
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": _txt(k)}})
    if p.get("why_read"):
        heading("💡 읽을 가치")
        para(p["why_read"])
    heading("📄 서지 정보")
    para(f"저자: {', '.join(p.get('authors') or []) or '-'}")
    imp = f"{p['impact']} ({p.get('impact_source')})" if p.get("impact") is not None else "-"
    para(f"저널: {p.get('journal') or '-'}  |  IF*: {imp}  |  게재일: {p.get('published') or '-'}")
    if p.get("abstract"):
        heading("🧾 원문 초록")
        para(p["abstract"])
    blocks.append({"object": "block", "type": "bookmark", "bookmark": {"url": p["url"]}})
    return blocks


def publish(new_papers, cfg):
    """새 논문들을 노션에 올리고, 성공한 논문에는 notion_url을 붙여 둔다."""
    token = os.environ.get("NOTION_TOKEN")
    if not token or not new_papers:
        if not token:
            log("NOTION_TOKEN 없음 → 노션 정리 건너뜀")
        return
    try:
        db = _database_id(token, cfg)
    except HttpError as e:
        log("노션 DB 준비 실패(페이지에 통합을 연결했는지 확인):", e)
        return
    if not db:
        return
    for p in new_papers:
        props = {
            "제목": {"title": _txt(p["title"])},
            "저널": {"rich_text": _txt(p.get("journal"))},
            "구분": {"select": {"name": "최신" if p.get("kind") == "new" else "추천"}},
            "DOI": {"url": p["url"]},
            "수집일": {"date": {"start": p["added"]}},
        }
        if p.get("impact") is not None:
            props["IF"] = {"number": p["impact"]}
        if isinstance(p.get("score"), (int, float)):
            props["관련도"] = {"number": p["score"]}
        if p.get("published"):
            props["게재일"] = {"date": {"start": p["published"]}}
        try:
            page = http("POST", f"{API}/pages", headers=_h(token), json_body={
                "parent": {"database_id": db}, "properties": props, "children": _page_body(p)})
            p["notion_url"] = page.get("url")
        except HttpError as e:
            log("노션 페이지 생성 실패:", p["title"][:40], e)
    log("노션 정리 완료")
