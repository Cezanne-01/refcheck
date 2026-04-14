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
