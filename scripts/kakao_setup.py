"""[처음 한 번만] 카카오 refresh token 발급 + 테스트 메시지 보내기.

내 컴퓨터에서 실행:  python scripts/kakao_setup.py
(파이썬 기본 기능만 써서 따로 설치할 것 없음)
"""
import json
import urllib.error
import urllib.parse
import urllib.request

print("=== 카카오 '나에게 보내기' 토큰 발급 ===\n")
rest_key = input("1) REST API 키: ").strip()
secret = input("2) 클라이언트 시크릿 코드 (없으면 그냥 엔터): ").strip()
redirect = input("3) 등록한 리다이렉트 URI [기본값 https://localhost:3000]: ").strip() or "https://localhost:3000"

auth_url = "https://kauth.kakao.com/oauth/authorize?" + urllib.parse.urlencode({
    "client_id": rest_key, "redirect_uri": redirect,
    "response_type": "code", "scope": "talk_message"})
print("\n4) 아래 주소를 브라우저에 붙여넣고 카카오 로그인 → '카카오톡 메시지 전송'에 동의하세요.")
print("   (동의 후 '사이트에 연결할 수 없음'이 떠도 정상이에요. 주소창만 보면 됩니다)\n")
print(auth_url, "\n")
back = input("5) 이동한 페이지의 주소창 전체를 복사해서 붙여넣기: ").strip()
code = urllib.parse.parse_qs(urllib.parse.urlparse(back).query).get("code", [back])[0]

form = {"grant_type": "authorization_code", "client_id": rest_key,
        "redirect_uri": redirect, "code": code}
if secret:
    form["client_secret"] = secret


def post(url, data, headers=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print("\n❌ 오류:", e.code, e.read().decode())
        raise SystemExit(1)


tok = post("https://kauth.kakao.com/oauth/token", form)
print("\n✅ 토큰 발급 성공! 테스트 메시지를 보냅니다...")

tmpl = {"object_type": "text",
        "text": "🔔 SIB 하드카본 논문 비서 연결 완료!\n내일부터 매일 아침 새 논문을 알려드릴게요.",
        "link": {"web_url": "https://developers.kakao.com",
                 "mobile_web_url": "https://developers.kakao.com"}}
res = post("https://kapi.kakao.com/v2/api/talk/memo/default/send",
           {"template_object": json.dumps(tmpl, ensure_ascii=False)},
           {"Authorization": "Bearer " + tok["access_token"]})
print("카카오톡 확인해 보세요! (결과:", res, ")")

print("\n================ GitHub Secret에 넣을 값 ================")
print("KAKAO_REST_API_KEY   =", rest_key)
if secret:
    print("KAKAO_CLIENT_SECRET  =", secret)
print("KAKAO_REFRESH_TOKEN  =", tok["refresh_token"])
print("==========================================================")
print("※ 이 값들은 비밀번호처럼 다루세요. 채팅이나 공개 저장소에 올리지 마세요.")
