# ymt_skirt_01 切断（seam）配線契約

Status: Implemented (2026-09-22。契約は round 1 と round 2 のレビュー反映済み v3。実装は 3 wave で完了し、9 章のテスト T1〜T15 が Maya 2026 で通過。実装中の補正: 5.4 の host、9 章の後始末の判定、T3 の操作、T11 の巻き方向)。決定事項は cut-panels-wiring-decisions.md、plugin 側の契約は
colliders/docs/plans/skirt-cut-panels.md（yddColliders 5.x）。裁定は colliders/docs/plans/skirt-cut-reviews/component-adjudication-round1.md と component-adjudication-round2.md。
本書は両方に従い、矛盾があれば停止して報告する。

用語: row は腰から裾（0 .. rows-1）、col は周方向（0 .. cols-1）。gap g は col g と col (g+1) mod cols の間。
E 空間、row-vector 規約、cell の走査順は ADR-0010 / ADR-0011 のとおり。
「材料 U」は plugin 契約 2.3 の s、「区画」は outputPatches の要素、panelId はその論理索引。
t は plugin の正規化高さ（腰 0、面の末端 1）。

## 0. 範囲、所有権、前提

| 所有 | 変更対象 |
| --- | --- |
| plugin（colliders リポジトリ、先行作業） | sources/skirtBellCollider.cpp（8 章 P）、docs/plans/skirt-cut-panels.md の該当行、tests/test_skirt_panels.py、tests/test_registration.py |
| component（本リポジトリ） | python/ymt_components/ymt_skirt_01/__init__.py、guide.py、settingsUI.py、README.md、adr/0012-*.md、tests/ymt_skirt_01/ |

互換は考慮しない（C16）。seam パラメータのない guide、4.x plugin、旧 rig の読み替えや shim は作らない。
VERSION は ADR-0011 M1 に従い component と guide とも [0, 1, 0] に据え置く。
component は版番号を検査しない（所有者指示）。_ensure_ydd_colliders_plugin は
outputPatches、seams、panelHems、followRange、referenceMaterialHeight、outputReferenceHeight の存在を検査する。
8 章 P が入る前の plugin では 2.3 が成立しないので、component の実装は P の完了後に始める。

## 1. guide パラメータ（A1、A3、A5）

| 名前 | 型 | 既定 | 意味 |
| --- | --- | --- | --- |
| seams | string | "" | 「g:r」をカンマ区切りで列挙。g は gap、r は最初に切れる row。空文字は seam なし。 |
| followRange | double | 0.1875 | plugin の followRange にそのまま渡す。有限かつ 0 以上。 |

seams の解析（_parse_seams(raw, rows, cols)、純関数、guide と rig で共用）:

1. 空白を除いた空文字は空リスト。
2. トークンはカンマ区切り。各トークンは「整数:整数」。それ以外は RuntimeError（ringPositions と同じく、生の文字列、トークン番号、理由を含む）。
3. 0 <= g <= cols-1、0 <= r <= rows-1。
4. g の重複は拒否。隣接する gap（g と (g+1) mod cols の両方が指定される）は「区画の列が 1 本になる」として拒否。
   cols = 3 で 2 本以上、cols = 4 で 3 本以上は必ず隣接するので同じ理由で拒否される。トークン数は 32 以下。
5. 返り値はトークン順の [(g, r)] と生トークン列。トークン順の索引 i が plugin の seams[i]（論理索引 i、密）、panelId = i+1。
   角度や g で並べ替えない。

settingsUI には seams の lineEdit と followRange の doubleSpinBox（最小 0、小数 4 桁）を ringPositions の直後に置き、
guide.py の同期は ringPositions と同じ形で行う。guide の描画は self.values["seams"] を読む（addParameters が既定値を登録済み）。

## 2. 構築手順（addObjects）

現行の順序を次に置き換える。太字は新規または変更。

1. plugin 確認（0 章）、rows/cols、参照と grid の収集、E 空間変換、_fit_cone（2.1）。
2. **seams と followRange の検証**（1 章、2.2）。ここまでの失敗はノードを一つも作らない。
3. refs、collider ノード作成、参照接続、_configure_collider（**followRange、referenceMaterialHeight、bellScale1 = 1.0 を含む**）。
4. **材料 U の校正**（2.3）。seam なしの状態で outputPatches[0] を採る。
5. **seams の書き込みと検証**（2.4）。
6. **列の区画所属と panelHems**（2.5）、**書き込み後の検証**（2.6）。
7. **区画ごとの面と fit**（3 章）。
8. ring controller（4 章）。
9. **区画ごとの U/V パラメータ**（5.1）。
10. cell（5 章）。
11. **区画ごとの ring skin、wave、post collision**（6 章）。
12. host は mGear の getHost が決める（ui_host 設定、なければ global ctl）。addObjects の uihost 代入は mGear が上書きするので効果がない（従来どおり）。

手順 2 の完了時に cmds.ls(long=True) の集合を記録し、手順 4〜6 で失敗したら、それ以降に作られた全ノード
（一時 shape、校正用 POSI、collider transform、refs group、参照の multMatrix を含む）を削除してから RuntimeError にする。
手順 7 以降の失敗は現行どおり（mGear が部分構築を残す）。

### 2.1 _fit_cone の変更（A4）

_fit_grid_profile で hem_column_projections[col] = dot(grid_positions[(rows-1, col)] - waist, axis) を計算する。
_seat_bell_origin_on_top_row が top_projection を引くとき、row_axial_projections と同時に hem_column_projections からも引く。
_fit_chain_height の hem_projection は max(hem_column_projections) にする。skirt_type、raw_height、height、surface_length の式は変えない。
_validated_ring_stations の hem_projection も max(hem_column_projections) にする（ring は面の末端まで置ける）。
row_axial_projections[-1] は従来どおり centroid で、行の V 写像（_surface_fraction）にだけ使う。

### 2.2 seam の開始高さ

plugin は startHeight h の seam で t > h の行だけを切り、t = h の行は共有する（plugin 契約 2.5）。h = 0 は腰から切る。
seam (g, r) の startHeight h は r = 0 なら 0、それ以外は h = max(t_(r-1), 1e-6)、t_(r-1) = _surface_fraction(row_axial_projections[r-1])。
下限 1e-6 は、腰に座った上行（t_0 = 0）で r = 1 を指定したとき plugin が h = 0 として腰行まで切るのを防ぐ
（buildRow は h = 0 で全行を切る）。実測（5.0.0）: startHeight 1e-6 の seam は受理され、t = 1e-6 に挿入行と vBreak ができる。
r >= 1 では t_r > h + 1e-9 を要求し、満たさなければ「開始行が前の行と同じ高さ」として拒否する。
h >= 1 - 1e-9 は「開始行が面の末端」として拒否する。
したがって component が書く startHeight は常に 1 未満で、plugin 条件 8 の未切断端の一致は到達しない。
同じ r の seam は同じ値を書くので plugin の高さクラスタで 1 行に集約される。
plugin の物理段は脚参照で決まり grid 行とは一致しないので、t_(r-1) は通常 plugin の挿入行になる。
fit の保護位置（vBreaks）は plugin の出力行に対して成立する。

gap g が row ρ で「有効」とは、g を持つ seam があり ρ >= r であること。

### 2.3 材料 U の校正（C15 の前段）

1. collider の seams が空の状態で outputPatches[0].surface（8 章 P の予約区画、u = s）を一時 nurbsSurface shape に接続し、
   pointOnSurfaceInfo を 1 個接続する。
2. u_k = k / N（k = 0 .. N-1、N = max(256, cols * 64)）で V = 0.5 の点を採り、_surface_angle で theta(u_k) を得る。
3. 目標角 phi に対する材料 U は次で求める。最近傍 k* = argmin_k |wrap(theta(u_k) - phi)|。
   その後、unwrap した連続座標の区間 [ (k*-1)/N, (k*+1)/N ]（k* = 0 なら [-1/N, 1/N]、k* = N-1 なら [(N-2)/N, 1]）で
   f(u) = wrap(theta(u mod 1) - phi) の符号変化を二分法で 40 回反復し、区間中点を mod 1 して材料 U とする（1 は 0 に写す）。
   区間は長さ 2/N の短い弧だけを対象にし、0/1 の反対側を探索しない。二分法は POSI の parameterU に u mod 1 を設定して評価する。
   符号変化がない場合は u_k* を使う。
4. col c の材料 U は phi = _column_mean_angle(c)。
5. gap g の材料 U は phi_g = atan2(sin(a_g) + sin(a_(g+1)), cos(a_g) + cos(a_(g+1)))、a はそれぞれの _column_mean_angle。
   sin 和と cos 和の絶対値が共に 1e-9 未満なら「gap の角度が退化」として拒否する。
6. s_g は [0, 1) に入れる（1 に等しければ 0）。異なる gap の s_g の周期差が 1e-9 以下なら拒否する。
   col と gap の材料 U の周期差が 1e-6 以下なら「seam が列に重なる」として拒否する。
7. 一時 shape、transform、POSI を削除する。

実測（2026-09-22、yddColliders 5.0.0、Maya 2026）: seams[0] = (materialU 0, startHeight 1) の単一区画 [0,1] の surface は、
u ノットが 0, 0, 0, 1/16, ..., 1, 1, 1 の clamped 一様で、(u, v) の評価点が周期 outputSurface の (u, v) と 3e-15 以内で一致した。
8 章 P はこの制限をそのまま予約区画 0 に使う。

### 2.4 seams の書き込みと検証

- seams[i]（i はトークン順、0..n-1）: enabled = true、materialU = s_(g_i)、startHeight = 2.2 の値。
- referenceMaterialHeight = surface_length。bellScale1 = 1.0 を _configure_evaluation_scale で設定し続ける
  （plugin の h_val は surface_length と同じ式。bell-local y の裾 = surface_length）。
- followRange = guide の値。

書き込み後、2.6 の方法で強制評価し、エラーがなく、`cmds.getAttr(node + ".outputPatches", multiIndices=True)` が
期待集合（seam なしなら [0]、あれば [1 .. n]）と一致することを要求する。
各要素の materialUStart、materialUEnd、vBreaks を読み、区画表 panels[id] = (a, b, vBreaks) を作る。
vBreaks は全区画で同一であることを検査する。
内部開始（0 < h < 1）の各 seam について vBreaks に h と 1e-9 以内の値があることを要求し、その値が h より小さければ
（plugin の高さクラスタが物理段の代表値へ繰り下げた場合）、h = その値 + 1.5e-9 で一度だけ書き直して再評価する。
beta = max(vBreaks)（空なら 0）。plugin は内部開始 seam があればその最大値を beta にし、なければ物理段の
最下から 2 番目を beta として vBreaks に入れるので、max(vBreaks) は plugin の beta と一致する。
rebuildSpansV >= len(vBreaks) + 1 を要求し、満たさなければ必要な値を含む RuntimeError にする（自動増加しない）。

### 2.5 列の区画所属と panelHems（A4、B8）

col c の unwrap 値 s'_c は、区画 (a, b) に対し a < s_c + m < b となる整数 m を探して定める。
どの区画にも入らない、または境界から 1e-6 以内なら拒否する（2.3 項目 6 で先に弾かれる）。
全区画で区画内の col の並びは s'_c 昇順とし、その順位を k_c（区画内列索引）とする。seam なしも同じ（col 順ではない）。
全 col が一度ずつ割り当てられることを検証する。

区画 id の裾サンプル:

- H_c = hem_column_projections[c] / surface_length。hem_column_projections[c] <= 0 は列名つきで拒否。H_c > 1 は 1 にする。
- H_c <= beta + 1e-9 の col は「裾が保護行より上」として列名と beta を含めて拒否する（plugin は厳密な H > beta）。
- uPanel_c = (s'_c - a) / (b - a)。
- サンプル列は [(0, H_first), (uPanel_c, H_c) for c in 区画内順, (1, H_last)]。
  seam あり: H_first = 先頭 col の H、H_last = 末尾 col の H（端の列の値をそのまま使う）。
  seam なし（周回）: 末尾 col (u_k, H_k) と先頭 col (u_1 + 1, H_1) の間を u = 1 で線形補間し、
  lambda = (1 - u_k) / (u_1 + 1 - u_k)、H_wrap = (1 - lambda) H_k + lambda H_1、H_first = H_last = H_wrap。
- 区画内の uPanel_c が 0 と 1e-12 以内なら先頭サンプルを厳密な (0, H_c) にしてその列自身のサンプルは出さず、1 と 1e-12 以内なら
  末尾サンプルを厳密な (1, H_c) にして同様にする。seam ありの区画では 2.3 項目 6 が先に列と seam の重なりを拒否するので、
  この置換に到達するのは seam なしの区画 0 で列が s = 0 に乗る場合だけである。
- 全区画の全 H が厳密に 1.0 なら panelHems を書かない。そうでなければ全区画に panelHems[id] を書く（疎にしない）。

### 2.6 強制評価と失敗検出

plugin は失敗を MGlobal::displayError で報告し kInvalidParameter を返すが、Python の getAttr は例外にならず、
配列要素は前回の成功値のまま clean になりうる。component は次で失敗を検出する。

1. om.MCommandMessage.addCommandOutputCallback で kError のメッセージを捕捉する（構築中だけ登録し、finally で外す）。
2. cmds.dgdirty(collider) の後、期待する各要素について MPlug(outputPatches[id].surface).asMObject() を呼ぶ。
3. 捕捉したメッセージのうち「<collider ノード名>: 」で始まるものがあれば、その全文を含む RuntimeError。
   asMObject が例外を投げる、または null を返す場合も RuntimeError（初回評価の失敗には前回値がない）。
4. panelHems を書いたときは outputPatches[id].hemHeightSamples を読み戻し、書いた配列と厳密一致することを要求する。

## 3. 区画ごとの面と fit（C10、C12）

区画 id ごとに次を作る。名前の接尾辞は常に「_p<id>」（seam なしでも _p0）。

| ノード | 名前 | 接続 |
| --- | --- | --- |
| transform | colliderSurface_p<id> | 現行の colliderSurface と同じ identity、inheritsTransform、非表示 |
| nurbsSurface | colliderSurface_p<id>Shape | fit.outputSurface -> create |
| yddSkirtSurfaceFit | colliderSurface_p<id>_fit | collider.outputPatches[id].surface -> inputSurface、collider.outputPatches[id].vBreaks -> protectedVParameters、spansV = rebuildSpansV |

置換表（現行関数 -> 変更）:

| 関数 | 変更 |
| --- | --- |
| _create_rebuilt_surface | 区画ごとに上表を作る。outputSurface への接続は残さない。返り値は dict[id, (transform, shape)]。 |
| _surface_u_parameters | 区画ごと。所属区画の fit 出力（shape.local）上で探索し、目標角は _column_mean_angle(col)。返り値 dict[col, u]。 |
| _surface_v_parameters | 変更なし（fit の V 域は全区画 [0,1]、行ごとに共通）。 |
| _ring_u_parameters, _connect_anchor_surface_follow | 4 章。 |
| _connect_anchor_scale | 入力の 8 点は 4 章で選んだ POSI。式は変更なし。 |
| _create_surface_drivers_and_controls | 区画ごとの uvPin を先に作り、cell の作成順は col-major（global col 外側、row 内側）のまま。5 章。 |
| _create_cell_driver | pin = 所属区画の uvPin、索引 k_col * rows + row。 |
| _validate_sampled_cell_positions | 失敗時に全区画の uvPin と位置ノードを削除。 |
| _cell_tangent, _projected_tangent, _rest_chain_cell_matrix, _validate_cell_frame_geometry, _cell_winding_sign, _create_cell_aim | 5.2 の隣接規則。 |
| _configure_cell_aim_modes | 5.3。 |
| _skin_rebuilt_surface, _ring_weights_for_cv, _validate_live_ring_weights | 6 章。 |
| _create_wave_deformer, _create_post_collision_deformer, _assert_surface_deformer_order | 6 章。 |
| addAttributes | host の post_falloff と wave 系を全区画の deformer に接続。 |
| _ensure_ydd_colliders_plugin | 0 章の版と属性の検査。 |

self.collider_surface_shape は dict[id, shape]、self.panel_ids は id の昇順リスト、self.panel_columns は dict[id, [col in s' 順]]。
outputSurface を読む経路は残さない。

## 4. ring anchor（B9）

_ring_u_parameters は全区画の fit 出力を対象にする。区画ごとに 256 点（u = k/256）を V = v_value で採り、
(id, u, angle) の表を作る。8 方向の各目標角に対して |wrap(angle - target)| 最小の (id, u) を選ぶ。
_connect_anchor_surface_follow の 8 個の POSI は選ばれた区画の fit 出力に接続する。

## 5. cell（B6、C10、C15）

### 5.1 パラメータ

- uvPin は区画ごとに 1 個、名前 skirtCells_p<id>_uvPin、deformedGeometry は colliderSurface_p<id>Shape.local。
  relativeSpaceMode、normalizedIsoParms = False、normalAxis、tangentAxis は現行と同じ。
- cell (row, col) の座標索引と outputMatrix 索引は k_col * rows + row（k_col は所属区画内の順位）。
- coordinateU は _surface_u_parameters の値、coordinateV は _surface_v_parameters の値。
  非対称裾でも行 V は col ごとに変えない。列の裾差は面（plugin の裾写像）と rest offset が吸収する。

### 5.2 隣接規則（B6）

cell (row, col) の隣接:

- next = (col + 1) mod cols。gap col が row で有効（2.2）なら next は無い。
- prev = (col - 1 + cols) mod cols。gap (col - 1 + cols) mod cols が row で有効なら prev は無い。
- 接線 T = p[next] - p[prev]。片方が無ければ T = p[next] - p[col] または p[col] - p[prev]。
  両方無い構成は 1 章の隣接 gap 拒否で到達しない（到達したら RuntimeError）。
- 巻き方向 s（_cell_winding_sign）は同じ規則の T で判定する。片側差分でも周方向の向きは同じなので符号は変わらない。

この規則を _cell_tangent、_projected_tangent、_rest_chain_cell_matrix、_validate_cell_frame_geometry、_cell_winding_sign、
_create_cell_aim の全てで使う（rest の M0 と live の aim が同じ接線定義を持つこと）。
_create_cell_aim の plusMinusAverage は片側のときも 2 入力の減算のままとし、ADR-0011 O3 と同じく
s = +1 なら input3D[0] = 減算の左辺、input3D[1] = 右辺、s = -1 なら入れ替えて output3D = s * T とする。
seam の開始行より上の行では seam をまたぐ隣接を残す（面は上側で共有）。異なる区画の cell の位置ノードを接続してよい。

### 5.3 aim の enum 検証の修正

_configure_cell_aim_modes は setAttr 後の確認を `cmds.getAttr(attr) == value`（整数）で行う。
asString はロケールで訳語を返すため使わない。

### 5.4 順序と索引の不変

fk_ctls、col group、jnt_pos、jointRelatives（stem_loc -> col * rows + row）は現行の col-major のまま。
uvPin の索引（5.1）と joint の索引は別物で、後者は区画に依存しない。host は mGear の getHost の結果（ui_host 設定か global ctl）で、component は変更しない。

## 6. deformer（C11、C13）

区画 id ごとに、次の順で作る。

1. ring skin: ringSkin_p<id>_skc。influences、bindPreMatrix、geomMatrix、caching は現行と同じ。weights は CV の軸投影から
   （_ring_weights_for_cv を区画の shape の CV に対して呼ぶ）。_validate_live_ring_weights は全区画の CV の最大値で 1 回だけ行う。
2. wave（wave が真のとき）: wave_p<id>_def。bellMatrix、evaluationToWorldRotation は現行と同じ。
   heightNormalization = 1、collider.outputReferenceHeight -> referenceHeight。
3. post collision（postCollision が真のとき）: 区画ごとに rest 複製 postCollide_p<id>_rest（colliderSurface_p<id> の duplicate、
   intermediateObject、非表示）を作り、その shape.local を postCollide_p<id>_def.restGeometry に接続する。他の属性は現行と同じ。
4. _assert_surface_deformer_order を区画ごとに行う。

self.wave_deformer と self.post_collide_deformer は dict[id, name]、self.post_collide_rest は dict[id, transform]。

## 7. guide の表示カーブ（B7）

_add_row_display_curves と _create_row_display_curves は _parse_seams(self.values["seams"], rows, cols) で seam を得て、
row ρ の閉ループを row ρ で有効な gap（ρ >= r）の位置で切る。
有効な gap がなければ現行どおり閉曲線 skirtRow<ρ>Crv。あれば、有効な gap のうち最小の g の直後の col から始めて col 順に断片を作り、
skirtRow<ρ>_<k>Crv（k = 0 から断片順）とする。2 点の断片も作る。1 点の断片は 1 章の隣接 gap 拒否で生じない。
postDraw の削除は「skirtRow で始まり Crv で終わる」の現行規則で新名も拾う。seams の解析エラーは描画でも RuntimeError。

## 8. plugin 側の変更 P（C14、先行作業）

sources/skirtBellCollider.cpp:SkirtBellCollider::compute は panelMode = false でも outputPatches に要素 0 を書く。

- surface: 周期 outputSurface と同じ行データを材料 [0, 1] に制限した U 3 次 kOpen、V 1 次 kOpen の面。
  パラメータ域は両方 [0, 1]。u と材料 U は一致する（u = s）。2.3 の実測と同じ構成。
- materialUStart = 0、materialUEnd = 1、vBreaks は契約 2.3 の規則（内部の beta があれば格納）、hem 配列は空。
- outputSurface は従来どおり同時に書き、描画は変えない（seam なしは周期面）。
- 失敗時の扱い、clean 処理は既存の panelMode = true と同じ。要素 0 の子 plug も setClean する。
- 版番号は 5.0.0 のまま変えない（所有者指示）。

契約 skirt-cut-panels.md の「panelMode=false の outputPatches は空」を上記に改める。改訂対象は 2.2 の要素表、2.4 の空配列判定、
2.9 の seam なし出力、5.2 項目 1（test_seamless_new_path_regression の空配列期待）、Q1 の行。
テスト: tests/test_skirt_panels.py に seam なしで要素 0 が存在し、同じ (u, v) の評価点が outputSurface と 1e-9 で一致し、
vBreaks が同じ形状で startHeight 0 の seam 1 本（内部開始なし、beta は物理段）を置いた場合と 1e-9 で一致することを追加する。
既存の「空配列」を期待する検査は改める。

## 9. テスト（D17）

component リポジトリに tests/ymt_skirt_01/test_cut_panels.py を置き、mayapy で実行する。
入力は環境変数 YDD_PLUGIN（mll のパス）、MGEAR_RELEASE、既定は本リポジトリと mgear develop のパス。
fixture は guide をコードで組む（テンプレートファイルは使わない）。rows = 5、cols = 8、必要なら列を回転する。
「ノードを残さない」は addObjects が作るノード（collider、refs、参照の multMatrix、校正用ノード、区画面、ring、cell、deformer の名前パターン）が残らないことで検査する。mGear の rig と component root は addObjects の前に作られるので対象外。

| # | 内容 | 期待 |
| --- | --- | --- |
| T1 | seam なし | 区画 [0]、cell の npo が locator 位置に 1e-6 * max(1, guide_size)（ADR-0011 V2）で乗る、deformer 順序、ring anchor が有限、outputSurface への接続がない、host が skirt_0_0、joint 索引が col*rows+row |
| T2 | seams "1:2,5:2" | 区画 [1, 2]、各 col の所属が 2.5 のとおり、row >= 2 の cell の接線入力が同区画の cell だけ、row < 2 は seam をまたぐ、uvPin が所属区画のもの、vBreaks に t_1 と 1e-9 以内の値を含む |
| T3 | T2 で follow = 0、smoothness = 0、全区画の ringSkin と postCollide の envelope = 0 にして左膝を X 軸に 35 度曲げる | 左区画の row >= 2 の cell が動き、右区画の row >= 2 の cell の outputMatrix が回転前後で厳密一致。腰や膝の Z 回転は seam より上の共有行を動かし、一方向伝達で両岸へ正当に伝わるので使わない（実測: 膝 Z 回転で右区画に 2.4e-3、膝 X 回転で 0）。envelope = 1 では 10 章の ring 経路で変わりうるので比較しない |
| T4 | 最下行の 3 列を上げ、列を 20 度回転した非対称裾、seam なし | panelHems[0] が s' 順で狭義単調、端点 0 と 1、H(0) = H(1) = 2.5 の補間値、H の最大が 1、構築成功、最下行 cell が locator に乗る |
| T5 | 不正な seams（書式、範囲外、重複 g、隣接 gap） | 構築前に RuntimeError、ノードを残さない |
| T6 | guide 描画 | T2 の seams で row >= 2 の表示カーブが 2 本の open、row 0〜1 は閉 |
| T7 | aim の enum | 5.3 の検証が整数比較で通る |
| T8 | 腰に座った上行（t_0 = 0）で "1:1,5:3" | 区画 [1, 2]、row 0 は両 gap をまたぐ（h = 1e-6）、row 1〜2 は gap 5 をまたぐ、row >= 3 は両方切れる、各 patch の V ノットに 1e-6 と t_2 が物理段と別に存在する（挿入行） |
| T9 | seam "1:0" で一度構築して beta を読み（beta >= 0.1 の fixture）、最下行の 1 列を H = beta - 0.05 に下げて再構築 | 列名と beta を含む RuntimeError、ノードを残さない |
| T10 | 腰に座った上行で 4 種の開始行 "0:1,2:2,4:3,6:4"（h = 1e-6, t_1, t_2, t_3）と rebuildSpansV = 4 | vBreaks 4 本、必要 spansV 5 を含む RuntimeError（fit 作成前）。spansV = 5 で成功 |
| T11 | 既定の列順（巻き方向 -1）と鏡像（+1）の両方で "1:2" | 片側 aim の出力が rest と 1e-6 * max(1, guide_size) で一致し構築成功。巻き方向は既定 fixture で -1、鏡像で +1 |
| T12 | 校正: col 2 を col 1 と同じ角度で半径だけ変えて置き seams "1:2"（gap 1 の角度 = col 1 の角度） | 2.3 項目 6 の拒否（seam が列に重なる）。別 fixture: 3 列を角度 0、180、90 度に置き seams "0:1" | 退化角の拒否。材料 U の 1e-6 は約 3.6e-4 度なので、度単位の小さな差では拒否されない |
| T13 | 非対称裾 + seam "1:2,5:2" | 各区画の hemHeightSamples が書いた値と厳密一致、両区画の vBreaks 一致 |
| T14 | wave あり、T4 の裾 | wave_p0_def.referenceHeight が surface_length、heightNormalization = 1 |
| T15 | postCollision あり、T2 | 区画ごとに rest 複製が別ノードで、restGeometry が自区画の複製に接続 |
| T16 | 8 章 P | plugin 側 tests/test_skirt_panels.py で検査 |

## 10. 既知の近似と未決

- 中間行の V は列共通（5.1）。非対称裾の短い列では中間行の面上高さが locator と一致しないが、rest offset で位置は一致する。
- ring anchor は seam をまたいで 8 点を採るので、seam 下側の ring 中心は両岸の平均になる。片岸の接触で anchor が動き、
  ring skin がその station の全区画の CV を動かすため、切断をまたぐ間接経路が残る（G1 の直接依存除去の外）。
  受け入れるか、区画ごとの anchor と skin に分けるかは未決。本書は受け入れる前提で書き、T3 は ring 経路を envelope で切って検査する。
- ymt_skirt_01 の README と ADR-0012 は実装後に本書から起こす。
