import pandas as pd
import streamlit as st
from pathlib import Path

st.set_page_config(page_title='医療圏流動ダッシュボード', layout='wide')

BASE = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE
ALT_DATA_DIR = Path('/Users/fujitakaede/Documents/monet_202603')

def pick_file(name: str) -> Path:
    p1 = DEFAULT_DATA_DIR / name
    if p1.exists():
        return p1
    p2 = ALT_DATA_DIR / name
    return p2

FLOW = pick_file('medical_area_flow_summary.csv')
BED = pick_file('medical_area_bed_inflow_structure.csv')
CHECK = pick_file('medical_area_inpref_balance_check.csv')

st.title('R5 病院の推計入院患者数（二次医療圏編）')

missing = [p.name for p in [FLOW, BED, CHECK] if not p.exists()]
if missing:
    st.error(f'必要ファイルが見つかりません: {", ".join(missing)}')
    st.stop()

flow = pd.read_csv(FLOW)
bed = pd.read_csv(BED)
chk = pd.read_csv(CHECK)

st.caption('単位: 人（元データ千人を×1000換算）')

c1, c2, c3, c4 = st.columns(4)
c1.metric('医療圏数', f"{len(flow):,}")
c2.metric('総入院需要', f"{int(flow['入院需要'].sum()):,}")
c3.metric('総受入数', f"{int(flow['受入総数'].sum()):,}")
c4.metric('整合誤差率', f"{float(chk.loc[0, '誤差率']):.6f}")

st.subheader('医療圏サマリー')
q = st.text_input('医療圏名で検索', '')
view = flow.copy()
if q:
    view = view[view['二次医療圏名'].astype(str).str.contains(q, na=False)]
st.dataframe(view, use_container_width=True, height=420)

left, right = st.columns(2)
with left:
    st.subheader('完結率が低い上位20')
    st.dataframe(
        flow.sort_values('完結率').head(20)[['二次医療圏名', '完結率', '入院需要', '県内流出', '県外流出']],
        use_container_width=True,
        height=380,
    )
with right:
    st.subheader('流入率が高い上位20')
    st.dataframe(
        flow.sort_values('流入率', ascending=False).head(20)[['二次医療圏名', '流入率', '受入総数', '県内流入', '県外流入']],
        use_container_width=True,
        height=380,
    )

st.subheader('病床種別ごとの流入構造（全医療圏合計）')
bed_agg = (
    bed.groupby('病床種別', as_index=False)[['受入総数', '県内流入', '県外流入']]
    .sum()
    .sort_values('受入総数', ascending=False)
)
bed_agg['流入率'] = ((bed_agg['県内流入'] + bed_agg['県外流入']) / bed_agg['受入総数']).round(4)
st.dataframe(bed_agg, use_container_width=True)

with st.expander('整合チェック詳細'):
    st.dataframe(chk, use_container_width=True)
