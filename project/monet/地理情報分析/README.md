# 地理情報分析（施設座標ベース）

目的: **医療圏内の医療体制評価**を、施設ごとの`緯度`・`経度`で実施する。

## 方針
- 入力: `r5rokko1.xlsx`（`年間値`シート）
- 既存クリーニングは維持
  - `header=4`
  - `病診区分` と `医療機関名` が欠損の行を除外
  - `*` / `-` / 空文字は欠損扱い
- 地理評価は都道府県平均ではなく、**施設ポイント**を直接利用

## 主な評価指標（医療圏単位）
- `平均中心距離_km`: 施設から医療圏重心までの平均距離
- `最大中心距離_km`: 施設分布の外縁距離
- `平均最近接距離_km`: 施設間の近接性（低いほど密）
- `施設空間カバー面積_km2`: 重心最大距離から推定した空間カバー
- `施設密度_10km2あたり`: 上記面積に対する施設密度
- `救急受入上位3施設集中度`: 救急受入の集中構造
- `圏内体制評価スコア`: 構造・救急対応・機器保有・地理分散を統合

## 出力ファイル
- `output/facility_cleaned.csv`: クリーニング後施設データ
- `output/facility_geoeval.csv`: 施設評価スコア、中心距離付き
- `output/medical_area_evaluation.csv`: 医療圏評価指標
- `output/medical_area_summary.csv`: 医療圏評価（同内容）
- `output/top10_medical_areas.csv`: 医療圏評価上位
- `output/map_facility_emergency.html`: 施設別救急受入マップ（MapLibre）
- `output/map_facility_structure.html`: 施設別構造スコア偏差値マップ（MapLibre）

## 実行
```bash
'/Users/fujitakaede/Documents/Visual Studio Code/first-repository/project/monet/.venv/bin/python' \
  '/Users/fujitakaede/Documents/Visual Studio Code/first-repository/project/monet/地理情報分析/geo_medical_analysis.py' \
  --input '/Users/fujitakaede/Downloads/r5rokko1.xlsx' \
  --outdir '/Users/fujitakaede/Documents/Visual Studio Code/first-repository/project/monet/地理情報分析/output'
```

ダッシュボード:

```bash
'/Users/fujitakaede/Documents/Visual Studio Code/first-repository/project/monet/.venv/bin/streamlit' run \
  '/Users/fujitakaede/Documents/Visual Studio Code/first-repository/project/monet/地理情報分析/streamlit_geo_dashboard.py'
```

## 今回の実行結果（2026-03-08）
- 対象医療圏: `鹿行`
- 施設数: `18`（緯度経度あり `18`）
- 救急受入件数（年間）: `7,362`
- 医療圏重心: `緯度 35.960643` / `経度 140.629868`
- 平均中心距離: `10.64 km`
- 最大中心距離: `24.76 km`
- 平均最近接距離: `2.37 km`
- 施設密度: `0.093 / 10km²`
- 救急受入上位3施設集中度: `0.876`
