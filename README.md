# refcheck — LLM 학술 초안 참고문헌 검증 도구

## 설치

``` bash
git clone <repo>
cd refcheck
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# .env 편집: OPENAI_API_KEY, UNPAYWALL_EMAIL 설정
```

## 사용

``` bash
# PDF 입력
refcheck --input draft.pdf --output ./report --level precise

# 텍스트 입력
refcheck --input draft.txt --output ./report --level fast
```

출력: `report.json` (구조화 데이터), `report.md` (사람 친화적 리포트)

## 검증 레벨

- `fast`: gpt-5.4-mini + gpt-5.4, 논문당 ~$1~2, 2~3분
- `precise` (기본): gpt-5.4-mini + gpt-5.4-thinking, ~$3~5, 5~8분
- `ultra`: gpt-5.4 + gpt-5.4-pro, ~$8~12, 10~15분

## 테스트

``` bash
pytest                      # 전체 (빠른 것만)
pytest -m slow              # 실 API 호출 포함
```

## 한계

이 도구는 **보조 도구**입니다. 모든 판정은 LLM·API 출력이며 오판 가능성이 있습니다.
특히 🟡 (인용 내용 불일치), 🟢 (맥락 약함), ⚪ (초록 기반), ❓ (확인 불가), 🔒 (접근 불가)
항목은 최종 사용자 확인이 필수입니다.

## Streamlit UI

CLI 외에도 웹 UI로 실행할 수 있습니다.

### 시스템 요구사항 (macOS)

PDF 다운로드에는 weasyprint가 필요하며, 다음 시스템 라이브러리를 먼저 설치해야 합니다:

``` bash
brew install cairo pango gdk-pixbuf libffi
```

### 실행

``` bash
streamlit run src/refcheck/ui/app.py
```

브라우저에서 http://localhost:8501 접속.

- 초안 PDF·TXT 업로드
- 검증 레벨 선택 (fast / precise / ultra)
- 실시간 단계별 진행 바
- 심각도별 접힌 Finding 목록 + side-by-side 근거 비교
- JSON / Markdown / HTML / PDF 리포트 다운로드

## 검증 동작 방식

이 도구는 **항상 LLM 에이전트 기반**으로 동작합니다. 파이프라인 단계:

1. **메타데이터 에이전트** — 각 참고문헌마다 4개 학술 DB(Crossref, OpenAlex, Semantic Scholar, PubMed)를 순차 조회. 최소 2개 DB에서 miss나면 **DuckDuckGo 백업 검색**으로 DOI/arXiv ID를 회수해 재조회. 그래도 못 찾으면 hallucination 판정. 제목·저자 매칭은 유니코드 정규화 + 저자 집합 교집합으로 관용도 높임 (한 글자/띄어쓰기 차이로 떨어지지 않음).
2. **본문 확보** — DOI/제목으로 **arXiv → Europe PMC → Unpaywall** 순으로 OA 본문 다운로드. 실패 시 초록만 사용.
3. **컨텐츠 에이전트** — 본문(없으면 초록)을 검색하여 인용이 실제로 뒷받침되는지 판정. 초록만으로 부족하면 에이전트가 직접 `fetch_full_text` 호출해 본문을 받아오고 다시 검색합니다.

### 비용·시간 (45개 참고문헌 기준)

| 레벨 | 비용 | 시간 |
|---|---|---|
| fast | ~$8~12 | 5~8분 |
| precise (기본) | ~$15~25 | 8~15분 |
| ultra | ~$30~50 | 15~25분 |

캐시(`./.cache`)가 살아있으면 메타데이터·본문 다운로드 결과는 재사용됩니다.
