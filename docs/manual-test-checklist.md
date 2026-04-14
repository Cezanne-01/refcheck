# Manual E2E Test Checklist

Plan 1+2 전체 동작을 실제 API 호출로 검증합니다. 실행에 비용이 발생합니다 (테스트당 ~$1-3).

## 사전 준비

- [ ] `.env` 파일에 `OPENAI_API_KEY`, `UNPAYWALL_EMAIL` 설정
- [ ] `brew install cairo pango gdk-pixbuf libffi` 완료
- [ ] `pip install -e ".[dev]"` 완료
- [ ] `pytest` 통과 (단위·통합 테스트 모두 녹색)

## CLI 검증

- [ ] 빈 텍스트 파일 → 에러 메시지 명확 (섹션 분리 실패)
- [ ] 참고문헌 0개 → `ValueError("참고문헌이 감지되지 않았습니다")`
- [ ] 참고문헌 200개 초과 → `ValueError(제한 초과)`
- [ ] 정상 초안 (예: tests/fixtures/drafts/injected_errors.txt) → JSON + MD 생성 확인

## Streamlit UI 검증

- [ ] `streamlit run src/refcheck/ui/app.py` 서버 시작
- [ ] 홈에서 타이틀·배너 정상 표시
- [ ] OPENAI_API_KEY 없으면 에러 카드 표시 (+ `.env` 안내)
- [ ] .txt 업로드 → 업로드 성공 메시지 + 글자수 표시
- [ ] PDF 업로드 → 동일 동작 (스캔 PDF는 에러 메시지)
- [ ] 검증 레벨 드롭다운: fast / precise / ultra 선택 가능
- [ ] "검증 시작" 클릭 → st.status 열림
- [ ] 각 단계별 progress bar 업데이트 (ingest → extract → metadata → fetch → content → aggregate)
- [ ] 완료 후 요약 카드 + 심각도별 expander 표시
- [ ] 🔴 severity 5 expander는 기본 펼쳐짐
- [ ] 🟡 finding 클릭 시 side-by-side 근거 표시
- [ ] 수동 확인 권장 리스트가 있는 경우 접을 수 있음
- [ ] JSON 다운로드 → 파일 열어서 구조 확인
- [ ] Markdown 다운로드 → 한글 깨지지 않음
- [ ] HTML 다운로드 → 브라우저에서 스타일 정상
- [ ] PDF 다운로드 → Adobe/Preview에서 열림, 한글 정상 출력
- [ ] PDF 다운로드 (weasyprint 실패 환경): 버튼 disabled + 안내 메시지

## 오류 경로

- [ ] OpenAI API 키가 잘못됨 → 적절한 에러 메시지
- [ ] 네트워크 단절 중 실행 → retry 후 실패 메시지 (traceback 없이)
- [ ] 같은 초안 재실행 → 캐시 hit으로 API 호출 수 감소 (총 비용 표시로 확인)

## 품질 체크

- [ ] 실제 LLM 초안 (ChatGPT에게 의학 논문 초안 생성 요청) 1편 검증
  - 🔴 환각이 실제로 있으면 감지되는지
  - 🟡 인용 내용 불일치 사례가 잡히는지
  - 비용이 예상 범위 내인지
