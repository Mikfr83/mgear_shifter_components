# ymt_skirt_01 ガイド改善契約: grid loc の配置と設定 UI の整理

Status: Implemented（2026-09-23。gpt-6-luna high が 1 回で完走。オーケストレータの修正 2 点: T24 の panel_columns の期待値が T1 からの写しで配置に依存していた（並び順でなく集合で判定に変更）、grid.py の front の直交化で単位ベクトルの長さを axis_length 比の epsilon と比べていた（axis_length で尺度合わせ）。Maya 2026 で T1〜T15、T17〜T24 合格。UI の配置は手動未確認）
用語は plans/cut-panels-wiring.md のとおり（row は腰から裾 0..rows-1、col は周方向、hip_half は hip_L と hip_R の距離の半分、E 空間）。
本書の対象は guide 側（配置と UI）のみ。plugin、component の構築、rig の配線は変えない。

## 0. 範囲と所有権

| 所有 | 変更対象 |
| --- | --- |
| component（本リポジトリ） | python/ymt_components/ymt_skirt_01/grid.py（新規、純関数と定数のみ）、guide.py、settingsUI.py、README.md、tests/ymt_skirt_01/test_cut_panels.py |
| 変更しないもの | plugin、__init__.py、plans/、adr/、既存テスト T1〜T21 の本文と Fixture の配置式（1.8 + 0.8v）、guide 属性 ringScaleX/Y/Z の名前と意味、既存 widget の objectName |

## 1. 現状の不具合（根拠）

既定 guide は hip が x=±1.0（hip_half=1.0）、ringScaleX=1.0、leg profile の全半径 1.0。脚の輪は腰の高さで半径 1.0 なので脚は x∈[0, ±2.0] を占める。
「rebuild_grid_locators」は行の半径を hip_half × (1 + 0.6 × row_ratio) とするので最上行 1.0、裾 1.6 で、全行が脚の内側に入る。

## 2. 配置規則（grid.py の純関数）

### 2.1 入力

「grid_locator_positions(rows, cols, references, front, profile, ring_scale_x, ring_scale_z, clearance=GRID_CLEARANCE, flare=GRID_FLARE)」を grid.py にモジュール関数として置く。GRID_CLEARANCE=0.15、GRID_FLARE=0.3 はモジュール定数で、guide パラメータにも UI にも出さない。maya、pymel、Qt を import しない（math のみ）。
- rows、cols: 整数（rows>=2、cols>=3。範囲外は ValueError）。
- references: 7 参照名（waist、hip_L、knee_L、heel_L、hip_R、knee_R、heel_R）から (x, y, z) の tuple への dict（guide の world または E の位置。両者の差は呼び出し側の責任）。
- front: root の前方向 (x, y, z)。
- profile: LEG_PROFILE_RADIUS_NAMES と LEG_PROFILE_POSITION_NAMES の 10 値の dict（validated 済み）。
- ring_scale_x、ring_scale_z: guide の ringScaleX、ringScaleZ（正）。
- clearance、flare: 0 以上の実数（既定は定数。テストが別値を渡せるように引数に残す）。
戻り値: (col, row, (x, y, z)) の list。col 昇順、その中で row 昇順。

### 2.2 幾何

1. axis_vector = heel 中点 − waist、axis_length = |axis_vector|、epsilon = 1.0e-3 × axis_length。axis_length <= epsilon なら ValueError。axis = 正規化。
2. front_axis = front を axis に直交化して正規化したもの（長さ <= epsilon なら ValueError）。side = axis × front_axis（外積。現行 rebuild と同じ向き）。以後の front は front_axis を指す。
3. hip_half = |hip_L − hip_R| / 2（<= epsilon なら ValueError）。
4. 行の中心: 現行どおり center(row) = waist + axis × axial_length × (0.15 + 0.75 × row_ratio)、row_ratio = row / (rows − 1)。
5. 脚の高さパラメータ s(row): ADR-0001 と component（_fit_chain_height）と同じ弦長の累積で d_hip = |hip 中点 − waist|、thigh_length = 左右の |knee − hip| の平均、calf_length = 左右の |heel − knee| の平均、d_knee = d_hip + thigh_length、d_heel = d_knee + calf_length とする（axis への射影ではない）。行の距離 d(row) = axial_length × (0.15 + 0.75 × row_ratio)。s(row) = clamp((d(row) − d_hip) / (d_heel − d_hip), 0, 1)。thigh_length または calf_length が epsilon 以下なら ValueError。
6. 脚の半径: plugin の SkirtLegProfile と同じ 5 節点の区分線形。t_knee = thigh_length / (thigh_length + calf_length)（0<t_knee<1）。節点 s は hip 0、thigh t_knee × thighPosition、knee t_knee、calf t_knee + (1 − t_knee) × calfPosition、ankle 1。半径倍率は hip (1, 1)、thigh (thighRadiusX, thighRadiusZ)、knee (kneeRadiusX, kneeRadiusZ)、calf (calfRadiusX, calfRadiusZ)、ankle (ankleRadiusX, ankleRadiusZ)。SkirtLegProfile と同じく、s の差が 1e-9 以内の節点は優先順位 ankle、knee、thigh、calf、hip の順で残す方を決めて重複を除き（thighPosition=0 や calfPosition=1 でゼロ除算にしない）、残った節点を s 昇順に並べてから補間する。s が節点の外なら端の値。rx(s) = hip_half × ring_scale_x × 倍率X(s)、rz(s) = hip_half × ring_scale_z × 倍率Z(s)。
7. 必要半径 R_req(row) = hip_half + max(rx(s(row)), rz(s(row)))。脚の楕円（中心 ±hip_half × side、半径 rx、rz）が axis を中心とする半径 R の円に含まれる十分条件。
8. 行の半径 R(row) = R_req(row) × (1 + clearance) × (1 + flare × row_ratio)。
9. 位置: col の角度 angle = 2π col / cols、radial = front cos(angle) + side sin(angle)、position = center(row) + radial × R(row)。現行と同じ角度の取り方（col 0 が前）。

### 2.3 rebuild_grid_locators の変更

現行の幾何計算を 2.2 の関数呼び出しに置き換える。参照位置は現行の「_guide_position」、front は「_root_front」、profile は「_validated_leg_profile_value」で読み、ringScaleX/Z は root 属性から読む。clearance と flare は既定の定数のまま渡す。ValueError は RuntimeError と同じく displayWarning にして戻る。locator の生成、親子付け、行の表示曲線、選択、displayInfo は変えない。

## 3. 設定 UI の整理（settingsUI.py と guide.py）

現行の単一 formLayout を、mainLayout の下に並ぶ 5 つの QGroupBox（各自の QFormLayout）に分ける。既存 widget の objectName、型、既定値、guide.py の populate と connect は変えない（配置先だけ変える）。

| GroupBox の title | 行順 |
| --- | --- |
| Grid | Rows、Columns、Rebuild Grid Locators（SpanningRole）、Surface Spans V |
| Leg | Hip Radius Scale X（ringScaleX_doubleSpinBox）、Hip Radius Scale Z（ringScaleZ_doubleSpinBox）、Ring Height Scale（ringScaleY_doubleSpinBox）、Ring Positions、既存の Leg profile groupBox（SpanningRole、内容は不変） |
| Collision | Tightness、Falloff、Smoothness、Follow、Follow Range、Post Collision (2nd pass) |
| Panels | Seams、Column FK |
| Rig | Ctl Size、Add Joints、Wave (deterministic oscillator) |

ラベル文言の変更は Ring Scale X → Hip Radius Scale X、Ring Scale Z → Hip Radius Scale Z、Ring Scale Y → Ring Height Scale の 3 つだけ（値は hip 半間隔に掛ける倍率なので Scale を残す）。属性名は変えない。
settingsUI.py のヘルパー「_ring_scale_spin_box」「_unit_spin_box」「_setup_leg_profile」は現在「self.groupBox」を親に直接使っている。5 分割後は「self.groupBox」を外枠（mainLayout を持つ既存の QGroupBox、title は空にする）として残し、ヘルパーは親 QGroupBox を引数に取る形に変えて、各 widget の Qt 親を所属グループにする。legProfile_groupBox の親は Leg グループにする。retranslateUi の setText はそのまま（objectName 不変）。guide.py の populate と connect は widget の objectName が不変なので変更不要（参照が壊れないことを確認する）。

## 4. README

Grid の節に配置規則（必要半径、定数 clearance 0.15 と flare 0.3、配置はリガーの責任で構築時の検査はしない）、Leg の節にラベルと属性名の対応（Hip Radius X = ringScaleX）を追記する。

## 5. テスト（tests/ymt_skirt_01/test_cut_panels.py、既存 T1〜T21 は変更しない）

| # | 内容 | 期待 |
| --- | --- | --- |
| T22 | grid.grid_locator_positions を rows=5、cols=8、既定参照（waist (0,0,0)、hip (±1,−1.5,0)、knee (±0.9,−5,0)、heel (±0.8,−9,0)、front (0,0,1)、profile 全 1.0、位置 0.5、ring_scale 1.0、既定の定数）で呼ぶ | rows×cols 個、col 昇順 row 昇順。各 row の全 col について axis からの距離が R_req(row) × 1.15 × (1 + 0.3 row_ratio) と 1e-9 以内で一致。R_req(row) は hip_half + max(rx, rz) を同じ式で独立に計算した値（2.0 に hip_half と半径の値を入れた式で書き、関数の戻り値を写さない）。clearance=0、flare=0 なら全行が R_req と一致。 |
| T23 | thigh 1.0、knee 0.5、calf 0.4、ankle 0.25（X と Z とも）、位置 0.5 の profile で同じ呼び出し（rows=9、cols=8） | 節点の半径倍率が s について単調非増加なので、R_req(row) が row について単調非増加であること（clearance=0、flare=0 で呼ぶ）。rows=1 または cols=2 は ValueError。thighPosition=0 と calfPosition=1 でも例外なく計算できること。 |
| T24 | Fixture と同じ参照で、grid 位置を T22 の関数の結果に差し替えた guide で build（Fixture に positions を差し替える手段がなければ、Fixture と同じ手順で guide を組む補助関数をテスト側に足す） | build が成功し、T1 と同じ検査（区画数と ID）が通る。最上行の半径が 2.3 に 1e-6 以内で一致する（hip_half 1.0 + 半径 1.0 = 2.0 に 1.15 を掛けた値）。 |

UI の配置は Qt が要るので手動確認（README に手順）。
