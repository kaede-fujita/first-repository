# monet_202603

患者調査（二次医療圏編）の再現分析とStreamlit可視化。

## 主要ファイル
- `reproduce_medical_flow_complete.py`: 元CSVから再現集計を実行
- `RUNBOOK_PATIENT_FLOW.md`: 再現手順
- `streamlit_app.py`: 可視化アプリ

## 再現実行
```bash
python reproduce_medical_flow_complete.py --n1 n0001.csv --n2 n0002.csv --outdir . --report
```

## Streamlit起動（ローカル）
```bash
streamlit run streamlit_app.py
```
