"""화면 꾸밈(디자인 A안). 색·글꼴·모서리는 .streamlit/config.toml에 두고,
여기에는 key를 붙인 영역(머리띠·신호등 카드·해석 문단)의 CSS만 둔다. 분석·판정 로직은 건드리지 않는다."""
from __future__ import annotations

import streamlit as st

CSS = """
/* 머리띠: 남색 바탕, 아래 청록 선, 오른쪽 점무늬 */
.st-key-ji_head {position:relative; overflow:hidden; padding:22px 30px 20px; background:#0A223C;
  border-radius:12px; border-bottom:3px solid #069E91;}
.st-key-ji_head::after {content:""; position:absolute; inset:0 0 0 auto; width:18%; pointer-events:none;
  background:radial-gradient(#367186 1px, transparent 1.4px) 0 0/12px 12px;}
.st-key-ji_head h1 {color:#FFFFFF !important; padding:0 !important; line-height:1.25;}
.st-key-ji_head p {color:#D7E3EC !important; max-width:80%; line-height:1.65;}
/* 신호등 카드: 판정 색마다 바탕·테두리·글자색. 색만이 아니라 아이콘·글자로도 알린다 */
.st-key-ji_verdict_green {background:#EBF6E9; border-color:#2C713E !important; color:#215E31;}
.st-key-ji_verdict_yellow {background:#FFF3D3; border-color:#956000 !important; color:#724700;}
.st-key-ji_verdict_red {background:#FBEDEE; border-color:#B33942 !important; color:#922731;}
.st-key-ji_verdict_green *, .st-key-ji_verdict_yellow *, .st-key-ji_verdict_red * {color:inherit !important;}
/* 긴 해석 문단은 읽기 편한 줄 길이로 */
.st-key-ji_text {max-width:80ch; line-height:1.7; word-break:keep-all;}
"""

# 판정 → (카드 key 접미사, Material 아이콘)
LIGHTS = {"초록": ("green", "check_circle"), "노랑": ("yellow", "error"), "빨강": ("red", "cancel")}


def load_style() -> None:
    st.html(f"<style>{CSS}</style>")


def header(title: str, subtitle: str) -> None:
    with st.container(key="ji_head"):
        st.title(title, anchor=False)
        st.caption(subtitle)


def verdict(light: str, reason_md: str) -> None:
    """신호등 판정 카드. light는 엔진이 낸 '초록'·'노랑'·'빨강' 그대로."""
    state, icon = LIGHTS.get(light, ("yellow", "help"))
    with st.container(border=True, key=f"ji_verdict_{state}"):
        st.markdown("**신뢰도 신호등**")
        st.subheader(f":material/{icon}: {light}", anchor=False)
        st.markdown(reason_md)


def data_badges(synthetic: bool) -> None:
    if synthetic:
        st.badge("가상 데이터", icon=":material/science:", color="blue")
