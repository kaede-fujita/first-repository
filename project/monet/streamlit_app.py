from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="R5 外来機能・外来（二次医療圏編）", layout="wide")

BASE = Path(__file__).resolve().parent
AREA_CSV = BASE / "r5_outpatient_emergency_by_area.csv"
PREF_CSV = BASE / "r5_prefecture_care_rates.csv"

st.title("R5 外来機能・外来（二次医療圏編）")
st.caption("主指標: 地域別外来・入院受療率（%）と救急発生率（%）")

missing = [p.name for p in [AREA_CSV, PREF_CSV] if not p.exists()]
if missing:
    st.error(f"必要ファイルが見つかりません: {', '.join(missing)}")
    st.stop()


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.read_csv(AREA_CSV), pd.read_csv(PREF_CSV)


def ensure_columns(df: pd.DataFrame, defaults: dict[str, object]) -> pd.DataFrame:
    out = df.copy()
    for col, default in defaults.items():
        if col not in out.columns:
            out[col] = default
    return out


area, pref = load_data()

area = ensure_columns(
    area,
    {
        "都道府県コード": "",
        "二次医療圏コード": "",
        "二次医療圏名": "",
        "人口_R5推計": 0,
        "外来患者延べ数_年間": 0,
        "救急車の受入件数（年間）": 0,
        "救急発生率_人口10万対": 0,
        "救急発生率_pct": 0,
        "紹介受診重点外来率_pct": 0,
    },
)

pref = ensure_columns(
    pref,
    {
        "地域": "",
        "入院受療率_人口10万対": 0,
        "外来受療率_人口10万対": 0,
        "入院受療率_pct": 0,
        "外来受療率_pct": 0,
        "入院受療率_変化率_pct": 0,
        "外来受療率_変化率_pct": 0,
    },
)

for col in [
    "人口_R5推計",
    "外来患者延べ数_年間",
    "救急車の受入件数（年間）",
    "救急発生率_人口10万対",
    "救急発生率_pct",
    "紹介受診重点外来率_pct",
]:
    area[col] = pd.to_numeric(area[col], errors="coerce").fillna(0)

for col in [
    "入院受療率_人口10万対",
    "外来受療率_人口10万対",
    "入院受療率_pct",
    "外来受療率_pct",
    "入院受療率_変化率_pct",
    "外来受療率_変化率_pct",
]:
    pref[col] = pd.to_numeric(pref[col], errors="coerce").fillna(0)

tab1, tab2 = st.tabs(["二次医療圏 救急発生率", "地域別 外来・入院受療率"])

with tab1:
    c1, c2, c3 = st.columns(3)
    c1.metric("二次医療圏数", f"{area['二次医療圏名'].nunique():,}")
    c2.metric("総外来患者延べ数", f"{int(area['外来患者延べ数_年間'].sum()):,}")
    c3.metric("総救急車受入件数", f"{int(area['救急車の受入件数（年間）'].sum()):,}")

    left, right = st.columns([1, 2])
    with left:
        pref_code = st.selectbox(
            "都道府県コードで絞り込み",
            options=["すべて"] + sorted(area["都道府県コード"].astype(str).unique().tolist()),
        )
        keyword = st.text_input("二次医療圏名で検索", "")

    filtered = area.copy()
    if pref_code != "すべて":
        filtered = filtered[filtered["都道府県コード"].astype(str) == pref_code]
    if keyword:
        filtered = filtered[filtered["二次医療圏名"].astype(str).str.contains(keyword, na=False)]

    with right:
        chart_cols = [c for c in ["救急発生率_pct", "紹介受診重点外来率_pct"] if c in filtered.columns]
        if chart_cols:
            chart_data = filtered.sort_values("救急発生率_pct", ascending=False).head(20).set_index("二次医療圏名")[chart_cols]
            st.bar_chart(chart_data)
        else:
            st.info("表示可能な率データ列がありません。")

    show_cols = [
        "都道府県コード",
        "二次医療圏コード",
        "二次医療圏名",
        "人口_R5推計",
        "外来患者延べ数_年間",
        "救急車の受入件数（年間）",
        "救急発生率_人口10万対",
        "救急発生率_pct",
        "紹介受診重点外来率_pct",
    ]
    safe_show_cols = [c for c in show_cols if c in filtered.columns]
    st.dataframe(filtered.sort_values("救急発生率_pct", ascending=False)[safe_show_cols], use_container_width=True, height=500)

with tab2:
    c1, c2 = st.columns(2)
    c1.metric("地域数", f"{pref['地域'].nunique():,}")
    c2.metric("全国 外来受療率（%）", f"{pref.loc[pref['地域'] == '全国', '外来受療率_pct'].sum():.3f}")

    top = pref[pref["地域"] != "全国"].copy().sort_values("外来受療率_pct", ascending=False).head(20)

    st.subheader("外来受療率（%）上位20地域")
    st.bar_chart(top.set_index("地域")[["外来受療率_pct", "入院受療率_pct"]])

    st.subheader("地域別 外来・入院受療率（% と人口10万対）")
    cols = [
        "地域",
        "入院受療率_pct",
        "外来受療率_pct",
        "入院受療率_人口10万対",
        "外来受療率_人口10万対",
        "入院受療率_変化率_pct",
        "外来受療率_変化率_pct",
    ]
    st.dataframe(pref[[c for c in cols if c in pref.columns]].sort_values("外来受療率_pct", ascending=False), use_container_width=True, height=520)

st.caption("注: 受療率(%)は人口10万対を1000で除して換算。救急発生率は救急車受入件数 ÷ 二次医療圏人口(R5推計) ×100。人口は2020年→2025年の線形補間。")
