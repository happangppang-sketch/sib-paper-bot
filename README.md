# 📚 SIB 하드카본 논문 비서

매일 아침 자동으로 하는 일:
1. **Crossref**(실제 출판 DB)에서 최근 3주 안에 나온 SIB 하드카본 논문 검색
2. 이미 저장된 논문은 **DOI와 제목 두 가지로 비교해서 제외** → 중복 없음
3. **제미나이**가 주제에 맞는지 판단(0~10점) + 한국어 요약
4. 새 논문이 하나도 없으면 → 최근 5년 안에 **많이 인용된 관련 논문**을 대신 추천
5. 웹사이트(`docs/papers.json`)에 차곡차곡 쌓고, **노션**에 논문별 요약 페이지 생성
6. **카카오톡 나에게 보내기**로 알림

모두 GitHub Actions(무료)에서 돌아가므로 컴퓨터를 켜 둘 필요가 없습니다.

## 폴더 구조
```
config.json              검색어, 하루 최대 개수, 추천 조건 등 설정
docs/index.html          웹사이트 (GitHub Pages)
docs/papers.json         모은 논문 저장소 (중복 검사 기준)
data/                    저널 IF 캐시, 노션 DB id 등
scripts/run_daily.py     본체 (collect / notify)
scripts/kakao_setup.py   카카오 토큰 처음 발급용 (내 컴퓨터에서 1회)
.github/workflows/daily.yml  매일 오전 7:47 자동 실행
```

## 설정 순서
| 단계 | 할 일 | 넣을 GitHub Secret |
|---|---|---|
| 1 | 제미나이 API 키 발급 | `GEMINI_API_KEY` |
| 2 | 카카오 앱 만들기 + 토큰 발급 | `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`, `KAKAO_REFRESH_TOKEN` |
| 3 | GitHub 저장소 만들고 업로드 + Pages 켜기 | `GH_PAT` (카카오 토큰 자동 교체용) |
| 4 | (선택) OpenAlex 키 → IF 근사값 표시 | `OPENALEX_API_KEY` |
| 5 | 노션 통합 만들기 | `NOTION_TOKEN`, `NOTION_PARENT_PAGE_ID` |

Secret 넣는 곳: 저장소 → **Settings → Secrets and variables → Actions → New repository secret**

### 키가 없으면?
없는 기능만 건너뛰고 나머지는 돌아갑니다. (예: 노션 키가 없으면 웹사이트+카톡만 동작)

## 임팩트팩터에 대해
공식 JIF(Clarivate JCR)는 유료 데이터라 자동으로 가져올 수 없습니다. 그래서
- 기본: OpenAlex의 **2년 평균 인용수**(JIF와 같은 계산 방식의 근사값) → 웹에 `IF*`로 표시
- 공식 값을 알면 `config.json`의 `impact_factor_override`에 `"저널이름": 숫자`로 적으면 그 값이 우선

## 직접 실행해 보기
Actions 탭 → "매일 SIB 하드카본 논문 수집" → **Run workflow**
