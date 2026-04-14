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
