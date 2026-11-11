"""카카오톡 '나에게 보내기'.

토큰 규칙(카카오 공식):
- access token은 몇 시간이면 만료 → 매번 refresh token으로 새로 받음
- refresh token은 2달 유효, 만료 1달 전부터 갱신 요청 시 새 refresh token이 같이 옴
  → 새 값이 오면 파일에 써 두고, GitHub Actions가 그 값으로 Secret을 자동 교체
"""
import json
import os

from common import http, log, truncate

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def get_access_token():
    rest_key = os.environ.get("KAKAO_REST_API_KEY")
    refresh = os.environ.get("KAKAO_REFRESH_TOKEN")
    if not rest_key or not refresh:
        log("카카오 키/토큰 없음 → 알림 건너뜀")
        return None
    form = {"grant_type": "refresh_token", "client_id": rest_key, "refresh_token": refresh}
    secret = os.environ.get("KAKAO_CLIENT_SECRET")
    if secret:
        form["client_secret"] = secret
    data = http("POST", TOKEN_URL, form=form)
    new_refresh = data.get("refresh_token")
    if new_refresh:
        # 워크플로가 이 파일을 보고 GitHub Secret(KAKAO_REFRESH_TOKEN)을 교체함
        path = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "new_refresh_token")
        with open(path, "w") as f:
            f.write(new_refresh)
        log("카카오 refresh token이 갱신되어 저장함")
    return data["access_token"]


def send_text(access_token, text, link_url, button="논문 보러가기"):
    template = {
        "object_type": "text",
        "text": truncate(text, 200),  # 텍스트 템플릿은 200자 제한
        "link": {"web_url": link_url, "mobile_web_url": link_url},
        "button_title": button,
    }
    res = http("POST", SEND_URL,
               headers={"Authorization": f"Bearer {access_token}"},
               form={"template_object": json.dumps(template, ensure_ascii=False)})
    if isinstance(res, dict) and res.get("result_code") != 0:
        raise RuntimeError(f"카카오 전송 실패: {res}")


def notify(new_papers, cfg):
    token = get_access_token()
    if not token:
        return
    site = cfg["site_url"]
    if not new_papers:
        send_text(token, f"📭 [{cfg['topic_name']}]\n오늘은 새로 올라온 논문이 없어요.\n지금까지 모은 논문은 웹사이트에서 볼 수 있어요.", site, "웹사이트 열기")
        return
    n = min(len(new_papers), cfg.get("kakao_max_messages", 5))
    for i, p in enumerate(new_papers[:n], 1):
        tag = "🆕 최신" if p.get("kind") == "new" else "⭐ 추천"
        imp = f"IF* {p['impact']}" if p.get("impact") is not None else "IF* -"
        text = (f"{tag} 논문 {i}/{n}\n"
                f"{truncate(p['title'], 90)}\n"
                f"📖 {truncate(p['journal'], 40)} | {imp}\n"
                f"{p.get('summary_ko') or ''}")
        send_text(token, text, site + "#" + p["id"])
    log(f"카카오톡 {n}건 전송 완료")
