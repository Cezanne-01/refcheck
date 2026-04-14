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

## 🤖 에이전트 모드 (정밀 검증)

기본 모드는 "파이프라인 기반" 검증이지만, `use_agents=True` 또는 Streamlit UI의 **"에이전트 모드" 체크박스**를 활성화하면 각 참고문헌과 인용을 LLM 에이전트가 스스로 검색 전략을 조정하며 검증합니다.

### 언제 사용?

- False positive가 많이 보일 때
- 저널 약어가 섞인 학술 논문
- 고정된 검색 전략으로는 놓치는 edge case가 있을 때
- 교수님·학술 투고 전 최종 점검

### 비용/시간

| 모드 | 45개 참고문헌 | 비용 | 시간 |
|---|---|---|---|
| 기본 (파이프라인) | - | $3~5 | 3~5분 |
| 에이전트 | - | **$15~30** | **8~15분** |

에이전트 모드는 비용이 2~3배 들지만 false positive가 크게 줄어들고, 판정 근거도 명확합니다.

### 설정 팁

- 처음엔 **기본 모드로 실행** → 결과 확인 → false positive가 많다 싶으면 **에이전트 모드로 재검증**
- 캐시가 살아있으면 (`./.cache` 유지) 메타데이터 조회 결과는 재사용됨
