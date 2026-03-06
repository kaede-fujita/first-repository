# 患者調査（二次医療圏編）再現分析 Runbook（最新版）

## 1. 目的
厚生労働省「患者調査（二次医療圏編）」のCSVから、OD行列を作らずに以下を再現する。

1. 入院完結率（圏内割合）
2. 県内流出・県外流出
3. 県内流入・県外流入
4. 病床種別ごとの流入構造

出力:
- `medical_area_flow_summary.csv`
- `medical_area_bed_inflow_structure.csv`
- `medical_area_inpref_balance_check.csv`
- `reproducibility_report.md`（任意）

## 2. 入力データ
- N1: `n0001.csv`（患者住所地）
- N2: `n0002.csv`（施設所在地）

想定配置:
- `/Users/fujitakaede/Downloads/n0001.csv`
- `/Users/fujitakaede/Downloads/n0002.csv`

## 3. スクリプト
- `/Users/fujitakaede/Documents/monet_202603/reproduce_medical_flow_complete.py`

本スクリプトで実施する処理:
- 生CSVの文字コード自動判定（cp932優先）
- 先頭注記/多段ヘッダを除去して tidy 化
- 欠損・`-` を0処理
- N1由来指標（D_i, C_i, O_inpref_i, O_outpref_i, 完結率）
- N2由来指標（S_i, I_inpref_i, I_outpref_i, 流入率）
- 県内流出入整合チェック（誤差率）
- 病床種別流入構造テーブル作成

## 4. 実行前準備
```bash
source "/Users/fujitakaede/Documents/monet_202603/.venv/bin/activate"
```

必要ライブラリ（未導入時のみ）:
```bash
python -m pip install pandas
```

## 5. 実行コマンド
### 実行（出力は常に人単位）
```bash
python "/Users/fujitakaede/Documents/monet_202603/reproduce_medical_flow_complete.py" \
  --n1 "/Users/fujitakaede/Downloads/n0001.csv" \
  --n2 "/Users/fujitakaede/Downloads/n0002.csv" \
  --outdir "/Users/fujitakaede/Downloads" \
  --report
```

## 6. 出力ファイル
- `/Users/fujitakaede/Downloads/n0001_tidy.csv`
- `/Users/fujitakaede/Downloads/n0002_tidy.csv`
- `/Users/fujitakaede/Downloads/medical_area_flow_summary.csv`
- `/Users/fujitakaede/Downloads/medical_area_bed_inflow_structure.csv`
- `/Users/fujitakaede/Downloads/medical_area_inpref_balance_check.csv`
- `/Users/fujitakaede/Downloads/reproducibility_report.md`（`--report`指定時）

## 7. 指標定義
- 入院需要: `D_i = C_i + O_inpref_i + O_outpref_i`
- 入院完結率: `p_stay_i = C_i / D_i`
- 流出率: `p_out_i = 1 - p_stay_i`
- 受入総数: `S_i = 圏内住所患者 + I_inpref_i + I_outpref_i`
- 流入率: `p_inflow_i = (I_inpref_i + I_outpref_i) / S_i`

整合チェック:
- `Σ(O_inpref_i) ≈ Σ(I_inpref_i)`
- `誤差率 = |Σ(O_inpref_i)-Σ(I_inpref_i)| / Σ(O_inpref_i)`

## 8. 実装上の注意
- N2の`受入総数`は病床種別`病院`を採用（病床別単純合算の二重計上を回避）
- 欠損値は0
- 数値列は整数化（出力単位: 人、元データ千人を×1000換算）
- 率は小数第4位
- マージキーは`二次医療圏名`

## 9. 年度更新時チェックリスト
1. 当年度のN1/N2を同じパスに置く（またはコマンド引数を変更）
2. 実行後に`medical_area_inpref_balance_check.csv`の誤差率を確認
3. 前年度との差分確認（対象医療圏数、合計D/S、完結率・流入率の分布）
4. 論文本文には`reproducibility_report.md`の方法・結果を転記
