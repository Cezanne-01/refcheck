"""Streamlit entry point for refcheck.

Run: `streamlit run src/refcheck/ui/app.py`
"""
from __future__ import annotations
import streamlit as st


def main() -> None:
    st.set_page_config(page_title="refcheck", layout="wide")
    st.title("📚 refcheck — 참고문헌 검증")
    st.caption("LLM이 작성한 학술 문서 초안의 참고문헌·인용을 검증합니다.")
    st.info("초안을 업로드하고 '검증 시작' 버튼을 눌러주세요.")


if __name__ == "__main__":
    main()
