# refcheck — LLM 학술 초안 참고문헌 검증 도구

LLM이 작성한 학술 문서 초안의 참고문헌·인용을 자동 검증합니다.
존재하지 않는 논문(환각), 잘못된 메타데이터(저자/연도/저널/DOI 등),
인용한 논문이 실제로 주장을 뒷받침하는지를 LLM 에이전트가 4개 학술 DB를
교차 조회해서 판정합니다.

## 빠른 시작

``` bash
git clone git@github.com:Cezanne-01/refcheck.git
cd refcheck
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
# .env 편집: OPENAI_API_KEY, UNPAYWALL_EMAIL 설정
.venv/bin/streamlit run src/refcheck/ui/app.py
```

브라우저에서 http://localhost:8501 접속 → PDF/TXT 업로드 → 검증 시작.

## 시스템 요구사항 (macOS)

PDF 리포트 생성에는 weasyprint가 필요합니다:

``` bash
brew install cairo pango gdk-pixbuf libffi
```

(weasyprint가 없어도 JSON 다운로드 + 웹 UI는 정상 동작합니다.)

## CLI 사용 (선택)

웹 UI 외에 CLI로도 실행 가능합니다:

``` bash
# PDF 입력
refcheck --input draft.pdf --output ./report --level precise

# 텍스트 입력
refcheck --input draft.txt --output ./report --level fast
```

출력: `report.json` (구조화 데이터) + `report.pdf` (가독성 좋은 리포트)

캐시(`./.cache/`)가 살아있으면 메타데이터·본문 다운로드 결과를 재사용합니다.

## 결과 화면 구성

각 참고문헌은 카드 1개로 표시되며 다음 정보를 담습니다:

- **상태 배지** — `✅ 검증됨` / `🟠 메타데이터 오류` / `🔴 환각 의심` / `❓ 확인 불가`
- **한 줄 평결** — 무엇이 틀렸는지 요약
- **메타데이터 diff 테이블** — 사용자 인용(빨강) vs 실제 논문(초록), 심각도 색상
  - 🔴 critical: DOI 다름, 저자 완전 다름
  - 🟠 major: 제목 substantially different, 저널 완전 다름, 연도 ≥2년 차이
  - ⚪ minor: 권/호/페이지 차이
  - 🔵 info: preprint vs published 1년 차이
  - (저널 약어 vs 풀네임, 제목 punctuation/typo 등은 무시)
- **인용 내용 검증** — 초안 인용 vs 원문 근거 side-by-side, 같은 ref의 유사 finding 자동 합침

다운로드: **JSON** (raw 데이터) + **PDF** (가독성 좋은 리포트). 두 형식 모두 한국어 explanation/suggestion.

## 검증 동작 방식

LLM 에이전트 기반 파이프라인:

1. **메타데이터 에이전트** — 각 참고문헌마다 4개 학술 DB(Crossref, OpenAlex, Semantic Scholar, PubMed)를 조회. 사용자 메타데이터에 오류가 있어도 찾도록 strict year filter 없이 검색하고, 후보를 title-similarity로 재정렬해 best match 선택. 매칭 실패 시 year=null로 retry, topic-keyword 변형, 마지막에 DuckDuckGo 백업 검색.
2. **본문 확보** — DOI 있으면 EuropePMC → Unpaywall 순으로 OA 본문 시도. DOI 없으면 EuropePMC → arXiv. arXiv 결과는 title similarity ≥0.55인지 검증해서 무관 페이퍼 거부. 실패 시 초록 기반.
3. **컨텐츠 에이전트** — 본문(없으면 초록)에서 인용 주장이 실제로 뒷받침되는지 판정. 초록만으로 부족하면 에이전트가 `fetch_full_text` 도구로 본문 다시 받아옴.

메타데이터 차이는 deterministic comparator(`compare_metadata`)가 산출하므로
LLM이 어떻게 답하든 일관됩니다. 같은 root cause로 발생하는 finding (예: 한 ref가
본문에서 3번 인용 → 같은 wrong-source 판정 3번)은 aggregator가 자동으로 1건으로
합쳐서 표시합니다.

## 테스트

``` bash
pytest                      # 전체 (빠른 것만, 183 tests)
pytest -m slow              # 실 API 호출 포함
```

## 한계

이 도구는 **보조 도구**입니다. 모든 판정은 LLM·API 출력이며 오판 가능성이 있습니다.
특히 다음 케이스는 최종 사용자 확인이 필수:

- 🟡 인용 내용 불일치 — 본문 검색 결과만으로는 결정적이지 않을 수 있음
- 🟢 맥락 약함 / ⚪ 초록 기반 — 본문 전문 미확보 상태
- 🔒 접근 불가 / ❓ 확인 불가 — DB 매칭 실패
- 사용자 인용에 가짜 제목이 있는 경우 — 같은 첫 저자의 다른 논문과 매칭될 수 있음 (diff 테이블의 canonical을 직접 검토)
