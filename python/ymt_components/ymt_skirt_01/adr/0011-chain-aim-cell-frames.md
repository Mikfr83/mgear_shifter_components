# ADR-0011: Chain aim による cell frame の位置と姿勢の分離

Status: accepted (2026-09-17; drafted from the orchestrator skeleton by Codex gpt-6-astra high,
contract review by sonnet, Muse, and Grok, implementation by Codex astra low, implementation review
by sonnet, Muse, and Grok; review records under docs/reference/skirt_design_review/adr11_*.md.
Maya acceptance tests below remain to be run by the user).

Partially supersedes ADR-0001: "Surface, drivers, controls, joints" の rest frame 規則
(Y = 外向き surface normal、Z = 投影した tangentV、X = cross(Y, Z))を R1 に置換する。
locator への rest 配置と offset の積順序は維持する。
Partially supersedes ADR-0008: V1 の VERSION = [4, 0, 0]、V2 の "before 4.0.0" の README 文言、
Consequences の integration check が 4.0.0 を期待する記述を M1/M2 に置換する。
命名・階層・joint の規則(N、G、C、J)は維持する。ただし N2 の node 列挙(_posi、_fbfm、_mm、_dm)は
uvPin への移行で既に存在しないため、N1 の現行 node 集合に置換する。
Partially supersedes ADR-0009: T4 の integration check が VERSION [4, 1, 0] を期待する規則を M1 に置換する。
Partially supersedes ADR-0010 の参照先 plans/local-evaluation-and-performance.md の
「cell frame と root scale」にある npo.matrix = offset / npo.offsetParentMatrix = Fcurrent の配線と
その検証を P/O/V に置換する。ADR-0010 本文の E 空間、root 変換、surface、参照、ring skin、
Wave の座標契約と plugin 要件は維持する。
ADR-0005 は置換しない(cell frame の規則は同 ADR に存在しない)。

## Context

cell の cube と npo の姿勢が隣接行に対してがたつき、次行の cell を向かない。
第一の原因は、surface の局所接線と grid 解像度の次行への弦が一致しないことである。
第二の原因は、uvPin の Z が normal と tangentU から決まる補完軸なのに対し、従来の rest frame は
tangentV を採用し、その差が cell ごとに異なる回転 offset として残ることである。
U/V 接線が斜交する変形後の surface では、この補完軸を tangentV と同一視できない。
位置は translation(offset × F) として先に確定し、その位置群から Z と X を決めて npo の姿勢を構成する。
非零 rest offset による位置への uvPin 回転の寄与は維持する。
この変更は位置が作る折れ線そのものを平滑化しない。

## Decision

row は腰から裾、col は周方向、内部 cell は (row, col) とし、scene 名は ADR-0008 に従う。
以下の点、方向、frame は E 空間(ADR-0010)で表す。
Maya の row-vector 規約を用い、行列の row 0/1/2 に X/Y/Z、row 3 に translation を置く。
記法: 行列積は × (左から右への合成)、外積は cross(a, b)、内積は a·b、スカラー倍は * で表す。
全行列は _matrix_from_axes / _matrix_attr と同じ 16 成分順(row 0 = X、row 1 = Y、row 2 = Z、row 3 = translation)
で扱い、multMatrix は matrixSum = matrixIn[0] × matrixIn[1] の row-vector 合成(matrixIn[0] が local 側)とする。
ベクトルと回転部の積 v × R は 1×3 row ベクトルと 3×3 回転行列の積である。
aimMatrix は純粋な行列 node であり world 空間の概念を持たない。inputMatrix、primaryTargetMatrix、
secondaryTargetVector を E の値で与えれば outputMatrix も E の値である。
c+ = (col + 1) mod cols、c− = (col − 1 + cols) mod cols とする。
cell の走査順は col-major(col 外側、row 内側の昇順)とする。

### Position layer (P)

- P1. _create_surface_drivers_and_controls は共有 uvPin と既存の E 入力を維持し、cell の frame を
  F(row, col) = uvPin.outputMatrix[col × rows + row] とする。
  _surface_u_parameters と _surface_v_parameters の校正と割当は変更しない。
- P2. _create_cell_driver は cell 作成時点の F を F0、R1 の rest frame を M0 として、
  定数 offset = M0 × inverse(F0) を計算する。
  cell ごとの multMatrix の matrixIn[0] に offset を値として設定し、matrixIn[1] に F を接続し、
  matrixSum を P = offset × F とする。
- P3. cell の位置は p = translation(P) とし、P の回転部を最終姿勢に使わない。
  locator 位置を L、F0/F の translation を f0/f、回転部を R_F0/R_F とすれば
  p = (L − f0) × inverse(R_F0) × R_F + f であり、M0 の回転部の変更はこの位置式を変えない。
  uvPin 回転の位置への寄与は |L − f0| に比例して残る(既存挙動、変更しない)。
- P4. _create_surface_drivers_and_controls は 3 段で cell を作る。
  第一段: 全 cell について multMatrix(P)と decomposeMatrix(inputMatrix = P、outputTranslate = p)を作る。
  第二段: D3 の p ベース検証を通した後、全 cell について O1〜O4 の plusMinusAverage と aimMatrix を作り、
  隣接参照(O2、O3)を connectAttr で結ぶ(値の setAttr ではない)。
  第三段: cell ごとに npo を作り、O7 の接続を済ませてから、npo の world matrix を読んで addCtl で ctl を作る。
  _create_cell_driver は第一段の cell 単位処理(F0 取得、offset、P、p)を担当し、第二段は別の helper
  (_create_cell_aim)が担当する。第一段の完了前に隣接 cell の P を参照しない。
- P5. F0 の取得と V の検証は現行の呼び出し順(ring skin、wave、post-collide の接続前)で行う。
  rest pose で post-collide が CV を動かす guide では、それらの接続後に cell が locator から
  ずれることがあるが、これは既存挙動であり本 ADR は変更しない。

### Orientation layer (O)

- O1. _create_cell_aim は cell ごとに aimMatrix を 1 個作り、inputMatrix に自身の P を接続する。
  primaryMode = Aim、primaryTargetVector = (0, 0, 0) とする。
  Aim モードの primaryTargetVector は primaryTargetMatrix 空間の点であり、(0, 0, 0) は target の原点
  (= translation(P_target))を指す。方向ベクトルではないので、ゼロベクトルの拒否規則を適用しない。
- O2. row < rows − 1 では primaryInputAxis = (0, 0, 1)、primaryTargetMatrix = P(row + 1, col)。
  hem(row = rows − 1)では primaryInputAxis = (0, 0, −1)、primaryTargetMatrix = P(row − 1, col)。
- O3. cell ごとに plusMinusAverage を 1 個作り、operation = 2(減算)とする。
  s = +1 なら input3D[0] = p(row, c+)、input3D[1] = p(row, c−)、
  s = −1 なら input3D[0] = p(row, c−)、input3D[1] = p(row, c+) とし、
  output3D = T_s = s * (p(row, c+) − p(row, c−)) を得る。
  周期は列指数の mod cols であり、U 値の seam に対する分岐は設けない。T_s は E のユークリッド差である。
- O4. secondaryMode = Align、secondaryInputAxis = (1, 0, 0)(常に正)、secondaryTargetVector に T_s を接続する。
  T_s は E 空間のベクトルである。secondaryTargetMatrix、preSpaceMatrix、postSpaceMatrix は接続せず
  既定値(identity)のままにし、identity は「T_s を E のまま解釈する」ことを意味する。
  enable と envelope も既定値のままにする(enable = True、envelope = 1.0)。
- O5. primaryMode / secondaryMode は enum の数値を ADR に固定しない。
  実装は cmds.attributeQuery(listEnum=True) で各 enum の定義文字列を読み、label "Aim"(primary)と
  "Align"(secondary)の index を求めて setAttr し、cmds.getAttr(asString=True) が "Aim" / "Align" を
  返すことを検証する。label が見つからない、または読み戻しが一致しない場合は RuntimeError とする。
  enable = True、envelope = 1.0 も読み戻して検証する。
- O6. aimMatrix は primary(Z の aim)を厳密に解き、secondary は primary 軸に直交する平面へ
  投影した後に合わせる。結果の frame は、通常行で Z = normalize(p(row + 1, col) − p(row, col))、
  hem で Z = normalize(p(row, col) − p(row − 1, col))、
  X = normalize(T_s − Z * (T_s·Z))、Y = cross(Z, X) とし、X = cross(Y, Z) の右手系を保つ。
  outputMatrix の row 0/1/2 は単位長の X/Y/Z、row 3 は p である。
- O7. aimMatrix.outputMatrix を npo.offsetParentMatrix に接続し、npo.matrix = identity とする。
  最終姿勢に旧 offset を後掛けしない。
- O8. aimMatrix、plusMinusAverage、decomposeMatrix は上流の P と p だけを参照し、
  npo、ctl、joint を入力として読まない。
  _cell_ctl_length と cube 形状は変更せず、FK ctl は npo の子に保ち、
  作成時の matrix と offsetParentMatrix を identity とする。

### Rest frame (R)

- R1. 新設 _rest_chain_cell_matrix は E の grid_positions のみを姿勢の幾何入力とし、S2 の s を適用する。
  locator を L(row, col) とし、通常行は Z0 = normalize(L(row + 1, col) − L(row, col))、
  hem は Z0 = normalize(L(row, col) − L(row − 1, col))、
  T0 = s * normalize(L(row, c+) − L(row, c−))、X0 = normalize(T0 − Z0 * (T0·Z0))、Y0 = cross(Z0, X0) とし、
  _matrix_from_axes で M0 = [X0; Y0; Z0; L] を構成する。
  弦と T の normalize の閾値は eps_len(D1)、投影 T0 − Z0 * (T0·Z0) の normalize の閾値は eps_dir(D2)とする。
- R2. 従来の _rest_cell_matrix と、cell ごとの build 用 pointOnSurfaceInfo(_restSampler)を撤去する。
  _surface_u_parameters と ring anchor の sampler は撤去対象に含めない。
- R3. rest では P0 = M0 × inverse(F0) × F0 = M0 により p が L に一致し、aim の出力も M0 に一致する。
  これを V2 で検証する。

### Winding sign (S)

- S1. 新設 _cell_winding_sign は _fit_cone 後の self.axis = a と reference_positions["waist"] = W を用いる。
  各 rest cell で radial = (L − W) − a * ((L − W)·a)、T_hat = normalize(L(row, c+) − L(row, c−))、
  Y0_candidate = cross(Z0, normalize(T_hat − Z0 * (T_hat·Z0)))、q = Y0_candidate · radial を求める。
  normalize の閾値は R1 と同じ(弦と T_hat は eps_len、投影は eps_dir)とし、D1/D2 の L ベース検証を
  S より先に行う(V5)ので、ここで退化は起きない。
- S2. |radial| < eps_len(D1)、または |q| ≤ 1e-6 × |radial| の cell があれば、cell 名を含む RuntimeError で停止する。
  走査順の最初の cell(0, 0)の sign(q) を基準符号とし、以降の cell で基準と異なる sign(q) を最初に
  検出した時点で、基準 cell 名と符号、不一致 cell 名と符号を含む RuntimeError で停止する。
  全 cell が一致するとき、基準符号を component 全体の s ∈ {−1, +1} とする。
  cell ごとに符号を反転して救済しない。多数決も行わない。
- S3. U 値の大小や col の番号順だけから s を決定しない。
  _rest_chain_cell_matrix と _create_cell_driver は同じ s を使う。
  「Y は外向き」は rest winding の規約であり、動作 pose で Y·radial > 0 を保証する規則ではない。
  実行時に符号を再選択しない。

### Degenerate handling (D)

- D1. 新設 _validate_cell_frame_geometry は eps_len = 1e-4 × guide_size(E の値)を用いる。
  弦は列ごとの隣接行ペア (row, row + 1) 単位で検証し、弦長が eps_len 未満なら両端の cell 名を含む
  RuntimeError で停止する。rows = 2 では 1 本の弦を 2 つの cell が共有する。
- D2. |T| < eps_len なら RuntimeError で停止する。
  T_hat = normalize(T)、Q = T_hat − Z * (T_hat·Z) として |Q| < eps_dir = 1e-3 なら RuntimeError で停止する。
  eps_dir は無次元の方向閾値であり、未正規化の T の長さに適用しない。
- D3. _validate_cell_frame_geometry は guide locator の rest 位置群(L)と、
  cell 作成時点の P の位置群(p)の両方に適用する。hem の Z と列の周期参照は O2/O3/O6 に従う。
- D4. collision / wave による実行時退化への fallback node は作らない。
  aimMatrix の退化時の代替出力は公開仕様で保証されず、実行時退化は本契約の保証範囲外とする。
  直前フレーム保持は評価順序に依存するため採用しない。
- D5. 校正 U の重複検出は本 ADR の範囲外とする。_surface_u_parameters の挙動は変更しない。
- D6. 第一段で各 cell の |L − f0| を求め、0.1 × guide_size を超える cell があれば、cell 名と距離を列挙する
  cmds.warning を 1 回出す。build は停止しない。P3 のとおり、この距離に比例して uvPin 回転が p に残る。

### Build validation (V)

- V1. F0 の有限性と右手系正規直交チェック(row 0〜2 の長さと 1 の差、および異なる軸の内積の
  絶対値が 1e-6 以下、行列式が正)は維持する。
- V2. _require_cell_matrix により aimMatrix.outputMatrix = M0 と
  npo.worldMatrix[0] = M0 × E→world を検証する。
  いずれも 16 成分ごとの差の絶対値を 1e-6 × max(1, guide_size) 以下とする。
  検証は全 cell の O2/O3 の接続後、ring skin / wave / post-collide の接続前(第三段)に行う。
  それらの接続後には再検証しない(P5)。
- V3. ctl の matrix / offsetParentMatrix が identity であることを、既存の許容差 1e-6 で検証する。
  旧 uvPin.outputMatrix → npo.offsetParentMatrix の直接接続チェックは、
  aimMatrix.outputMatrix → npo.offsetParentMatrix の接続チェックに置換する。
- V4. npo.matrix = offset の一致検証を廃止する。world rest の期待値(M0 × E→world)自体は変えない。
- V5. D1〜D3 と S2 を build 時に検証する。順序は、L ベースの D1、D2、次に S2、次に第一段、
  次に p ベースの D1、D2、次に第二段(aimMatrix / plusMinusAverage の作成)とする。
  退化 cell を検出したとき aimMatrix を作らずに停止する。
  _validated_grid_matrices、_convert_guide_to_evaluation_space、_fit_cone の既存検証は維持する。
- V6. O5 の enum 読み戻しと、multMatrix.matrixIn[0] の値が offset に一致すること(許容 1e-9)を検証する。

### Naming (N)

- N1. cell stem "skirt_<col>_<row>" に "_pos_mm"(multMatrix)、"_pos_dm"(decomposeMatrix)、
  "_tan_pma"(plusMinusAverage)、"_aim"(aimMatrix)を追加する。
  node 名は既存の _npo / _ctl と同じく self.getName(_cell_stem(cell) + suffix) で生成する。
  uvPin の index は従来どおり col × rows + row である。
  ADR-0008 N2 の列挙(_posi、_fbfm、_mm、_dm)は stem 規則の例示であり、それらの node は
  uvPin への移行で既に存在しない。
- N2. 新設 helper の error message の cell 名も _cell_stem で生成し、ADR-0008 N5/N7 を維持する。

### Version and documents (M)

- M1. component / guide の VERSION は __init__.py と guide.py とも [0, 1, 0] に据え置く(公開前。ユーザー決定)。
  公開前は VERSION を上げない。colliders repository の integration check
  (tests/integration/check_wave_component.py)が期待する VERSION も [0, 1, 0] とする(orchestrator が編集する)。
- M2. README の "Surface fit and cell tracking" を P/O/R/V の新配線に書き換える。
  "before 4.0.0" と "4.0.0 lack the leg profile parameters" の文言は、版番号を使わず
  「column-major grid(ADR-0008)より前の guide は fail closed」「leg profile parameter の無い guide は
  settings dialog が既定値を追加する」に改める。yddColliders の plugin 要件は維持する。
- M3. plans/local-evaluation-and-performance.md の「cell frame と root scale」にある
  npo.matrix = offset / npo.offsetParentMatrix = Fcurrent の式ブロックを削除し、P2/O7 の式
  (P = offset × F、npo.offsetParentMatrix = aimMatrix.outputMatrix、npo.matrix = identity)に置き換える。
  「cell と surface の追従」の uvPin 直結と build POSI の記述も同様に改め、両節に本 ADR を参照する 1 行を追記する。
- M4. _cell_ctl_length のコメント(Z = tangentV)は弦契約に合わせて改める。

### Scope of replacement (X)

- X1. _rest_cell_matrix の surface 微分による rest 姿勢と、_create_cell_driver の offset 配置を
  P/O/R/V に置換する。
- X2. _create_surface_drivers_and_controls の命名、group、joint 登録は ADR-0008 を維持し、
  joint は J1〜J5 のとおり ctl の world matrix に追従する。J5 で維持するのは駆動経路であり、
  joint の rest 姿勢は R1 の M0 に従う新しい ctl world になる。旧数値の rest 姿勢は保証しない。
  _connect_anchor_surface_follow、_skin_rebuilt_surface、_create_collider_node、_create_wave_deformer、
  _create_post_collision_deformer の配線と ADR-0002/0005 の ring anchor frame は変更しない。
- X3. _convert_guide_to_evaluation_space と evaluation_to_world_plug の E 境界は ADR-0010 を維持する。

## Considered options

- B(法線平滑化): 接線と次行への弦の不一致が残るため不採用。
- 隣接列の中点への Aim: 中点から自身を引いた方向は周方向ではなく内向きになるため不採用。
- Z の中央差分: 次行への厳密な aim を失うため不採用。
- joint 層での再 aim: ctl の向きを直せず、animator の回転を上書きするため不採用。
- 法線 Align の副軸: 法線微分由来の roll が残るため不採用。Maya での対照実験には使えるが契約に含めない。
- 実行時 fallback(直前フレーム保持など): 状態依存を作るため不採用。
- C(C++ 一括 sampler): 標準 node で要件を満たせるため今回は不採用。再検討条件を参照。

## Consequences

- 既存 rig は再構築し、変更後の joint rest orientation に合わせて re-bind する。
  control の rest orientation が変わるため、既存の回転 animation と、姿勢に依存する custom step の
  互換性は保証しない。
- cell ごとの実行時 node は multMatrix、decomposeMatrix、plusMinusAverage、aimMatrix の各 1 個、
  計 4 × rows × cols 個(既定 40 cell で 160 個)。共有 uvPin は 1 個のまま、build 用 _restSampler はなくなる。
  node 数から速度を推定せず、操作レイテンシと再生時間を旧配線と比較する。
- 位置式、UV 校正、cube 形状と rest 長、FK 編集層、ADR-0008 の命名と階層と joint、ADR-0010 の E 境界、
  ring と各 deformer の配線は維持する。
  cube の長さを動的に変えないため、変形時に先端が次行位置へ届くことは保証しない。
- Z は隣接 cell の p への厳密な aim であり、生の surface 点への aim ではない。p は P3 のとおり
  |L − f0| に比例して uvPin 回転を継承するため、locator が surface から離れた cell では位置由来の
  揺れが残り、がたつきは完全には消えない(D6 の warning で可視化する)。
- 旧配線は cell ごとに評価が独立していたが、新配線は各 cell が row ± 1 の P と col ± 1 の p を読むため、
  rows × cols の連結した依存グラフになる。循環はない(O8)。Parallel Evaluation のクラスタリング挙動は
  acceptance の DG / Parallel / Cached Playback 比較で確認する。

## Revisit triggers

- 実運用で collision / wave による退化(D4)が観測された場合、案 C で frame 算法と退化処理を再検討する。
- 周方向の弦を使っても roll 品質が不足し、parallel transport が必要になった場合、初期副軸と列間 roll を
  含めて再検討する。
- 既定構成または本番最大構成で cell の評価コストが操作レイテンシや再生時間を支配する場合、
  案 C と性能計画を再検討する。
- 弦由来の winding(S1/S2)が surface normal ベースの外向きと系統的に食い違う grid 形状が観測された場合、
  normal を補助入力に使う winding 判定を再検討する。
- D6 の warning が実運用の guide で常態化する場合、locator を surface へ投影する rest 配置を再検討する。

## Maya acceptance tests

実装後に orchestrator / user が実施し、未実施の試験を採用済みの根拠としない。

- 中立、深いしゃがみ、片脚上げ、脚交差、U seam、非零 rest offset、rows = 2 / cols = 3。
  O6 の弦方向に対する acos(Z·弦方向) ≤ 1e-4 rad、E frame の直交誤差 ≤ 1e-6、行列式 > 0。
- FK ctl 1 個の操作が他 cell に逆流しないこと。root の回転と正の一様 scale 0.5 / 1 / 2。
  build 時の root が identity でない(回転 90 度、scale 2)状態でも V2 が通り、rest で ctl が locator に乗ること。
- DG / Parallel / Cached Playback の結果が一致すること。一致の要求は、全フレームで弦長 ≥ eps_len かつ
  |Q| ≥ eps_dir を満たす入力系列に限る。退化を含む系列の一致は採用条件としない。
- postCollision を有効にした rest pose で、全 deformer 接続後の弦長と |Q| を計測し、D1/D2 の閾値を
  下回る cell がないこと(P5 の既存挙動の確認)。
- 各 cell の |L − f0| と、脚の動作中の p の揺れ(隣接 cell 間の角度の時間差分)を記録し、D6 の
  warning 閾値の妥当性を判断すること。
- 折返しに近い入力(|Q| が 2e-3 程度)で aimMatrix の出力が O6 の式と一致し、反転しないこと。
- 既定 40 cell と本番最大構成で、操作レイテンシと再生時間を旧配線と比較すること。
