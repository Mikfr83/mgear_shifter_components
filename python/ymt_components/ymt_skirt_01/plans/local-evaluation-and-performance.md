# 局所評価と性能改善の実装計画

[ADR-0010](../adr/0010-component-local-evaluation.md) の実装詳細と検証項目を記録する。
この文書は計画であり、採択済みの契約ではない。

## 現行の境界

build 時に root の初期 world matrix を取得し、保存済み guide の参照行列と grid 行列へその逆行列を乗じて E を作る。
7 個の参照出力は matrix × offsetParentMatrix と、合成済みの親出力から構築する。
collider と post-collision deformer には同じ出力を接続する。

再構築 surface は local channel を identity、inheritsTransform=True とする。
surface の .local geometry は E の値であり、DAG 上の world 配置だけが現在の root を継承する。
表示用 collider locator も root を継承する。

plugin major は 4 とする。
Wave と post collision の deformer は object-space geometry と E の行列を直接評価し、localToWorldMatrix 引数は使用しない。
evaluation space の互換切替は設けない。

## 参照行列と skin

参照行列は row-vector 規約で次のように合成する。

~~~text
L = matrix × offsetParentMatrix
waistE = Lwaist × LrefsGroup
hipE   = Lhip   × waistE
kneeE  = Lknee  × hipE
heelE  = Lheel  × kneeE
~~~

初期状態では、保存済み reference の world matrix に build root の逆行列を右から乗じた値と一致することを検証する。
編集後は、実際の参照 world matrix と現在の root inverse から求めた値と比較する。
実行時に world matrix と live root inverse を乗じて同じ値を作る経路は追加しない。

ring skin では、各 anchor の E 行列を A_i、ring control の有効な編集行列を C_i とする。

~~~text
skin.matrix[i]        = joint の offsetParentMatrix が読む C_i × A_i
skin.bindPreMatrix[i] = inverse(A_i)
skin.geomMatrix       = identity
~~~

hidden influence joint は inheritsTransform=False、local TRS と jointOrient を identity、segmentScaleCompensate=False とする。
bind 前に C_i × A_i を joint の offsetParentMatrix へ接続し、skin の matrix[i] はその joint の OPM を読む。
skin.matrix へ multMatrix を直接接続しない。

influence 登録、bind pose、skinPercent の値、skin の元 geometry 接続、MFnSkinCluster からの参照を一組として維持する。
Maya が作る Orig shape を含めた実際の接続を検証する。
Maya が生成した geometry 入力の worldSpace 接続を維持し、Orig shape の local を skin.input[0].inputGeometry へ再配線しない。
標準 skin の caching=True は使用する。

## cell と surface の追従

yddColliders 4.1.0 の yddSkirtSurfaceFit で surface を再構成し、1 個の uvPin で全 cell の位置計算用 frame を取得する。
yddSkirtSurfaceFit は rebuildSpansV（1〜256）で V を再分割し、リングアンカーは skin 前の outputSurface を読む。
uvPin は最終 surface の .local を deformedGeometry で受け、originalGeometry は接続せず、relativeSpaceMode=1、normalizedIsoParms=False、normalAxis=1、tangentAxis=0 とする。
各 cell の coordinate は col × rows + row の順に設定する。uvPin.outputMatrix は cell ごとの multMatrix で定数 offset と合成し、decomposeMatrix で位置を取り出す。
plusMinusAverage は周期的な隣接列の位置差(s = +1 なら p(c+) − p(c−)、s = −1 なら入力順を入れ替えた符号付きの差)を作り、aimMatrix は隣接行への弦とその位置差から姿勢を求め、npo.offsetParentMatrix へ出力する。
rest frame は guide の弦から求め、cell ごとの build 用 POSI は作成しない。U 校正と ring anchor の sampler は維持する。cell の root scale 補正ノードは使用しない。
cell の位置と姿勢の契約は [ADR-0011](../adr/0011-chain-aim-cell-frames.md) に従う。
Maya での構築検証と性能計測は未実施である。

ウェイト設定は既存の接続を維持する。
ウェイト設定用の CV 位置は `cmds.pointPosition(cv, local=True)` で E の座標を取得する。
`world=False` は local の指定にならないため使用しない。

cell sampler は、実行時間と操作時の制御挙動を基準に選ぶ。
現行の uvPin と、未実装の全 cell frame 用 C++ sampler の比較では、完全な frame 一致を採用条件にしない。
ring の移動、回転、profile 半径、rebuild span、非零 rest offset を含む操作で挙動を確認し、採用した経路を固定する。
候補を切り替える guide 設定、旧 node、互換 shim は残さない。

候補の設計と計測は、[collider の ADR-0007](../../../../../../../colliders/2.1.0/colliders/docs/adr/0007-performance-first-evaluation.md) と[性能計画](../../../../../../../colliders/2.1.0/colliders/docs/plans/performance-first-evaluation.md)で管理する。
コンポーネント側は E 空間、surface の `inheritsTransform=True`、influence 登録と skin API の接続契約を維持する。

未実装の候補は次のとおりである。

- 全 cell frame 用の C++ 一括 sampler
- U 校正用の OpenMaya 一括処理
- skin weight 用の配列一括設定

## cell frame と root scale

uvPin の初期剛体 frame を F0、現在の frame を F、guide の弦から作る rest frame を M0 とする。
cell ごとの multMatrix が位置用行列 P を求め、aimMatrix が隣接 cell の位置から姿勢を求める。root の変換は親階層で適用する。

~~~text
offset = M0 × inverse(F0)
P = offset × F
p = translation(P)
npo.offsetParentMatrix = aimMatrix.outputMatrix
npo.matrix = identity
npo.worldMatrix = aimMatrix.outputMatrix × E→world
~~~

uvPin の行 0〜2 は正規直交するため、法線と接線の長さの比を補正する K は使用しない。
構築時には F0 の有限性、正規直交性、正の行列式を検証する。
multMatrix.matrixIn[0] と offset の成分差は 1e-9 以内とする。
rest の aimMatrix.outputMatrix と M0、および npo.worldMatrix と M0 × E→world の成分差は、それぞれ 1e-6 × max(1, guide_size) 以内とする。
control 作成後には control の offsetParentMatrix を identity に設定し、matrix と offsetParentMatrix が identity（1e-6）であることを検証する。npo には aimMatrix.outputMatrix の接続を検証する。
これらの rest 検証は全 cell の aim 接続後、ring skin、wave、post-collision の接続前に行う。
cell frame と検証の契約は [ADR-0011](../adr/0011-chain-aim-cell-frames.md) に従う。

## Wave の方向契約

現在の root world matrix を pickMatrix に通し、translation、scale、shear を除いた回転を evaluationToWorldRotation へ接続する。
World 方向 dWorld は次の順で E へ変換する。

~~~text
dEval = dWorld × inverse(R)
dPerpEval = dEval - bellAxisEval × dot(dEval, bellAxisEval)
~~~

impulse は入力強度を保持し、idle direction は回転前に正規化してから変換する。
Bell Local は R を使わない。
bell axis、radial displacement、bell scale は E で計算し、root scale は DAG で一度だけ適用する。

## 検証データと判定

同じ fixture、同じ Maya 版、同じ入力系列を別プロセスで実行し、plugin hash、component revision、設定、評価モード、出力を記録する。
Maya 2022 から 2027 を対象にするが、未実行の版や Cached Playback の結果を検証済みとは記載しない。

| 分類 | 確認する入力 |
| --- | --- |
| E 参照 | 7 参照の TRS、OPM、親階層、root OPM、DAG 親 |
| root | 移動、回転、正の一様 scale 0.5 / 1 / 2 |
| 拒否 | 非一様 scale、反転、shear、退化 scale |
| deformer | hip / knee 単独・複合回転、左右非対称、有限値 |
| skin | ring 数、control 編集、anchor scale、live bind-pre |
| Wave | World / Bell Local、回転入力、zero signal、envelope |
| collision | Wave と post collision の有無、short / long profile |
| surface | rebuild span、UV seam、非零 rest offset |

最終比較は、実際の MFnNurbsSurface DAG path の kWorld CV を取得して行う。
E の hidden surface を world 出力として直接比較しない。
E の CV を基準にする比較では、capture した E 値へ現在 root を適用して world 値を作る。

root だけを変更する試験では E の参照と control を固定する。
collider と fit の E CV は固定され、表示結果だけが root に追従することを確認する。
World Wave は root 回転により R を通じて E の方向が変わり、Bell Local は同じ操作で signal が変わらないことを確認する。

既存の local 化を検証した記録では、位置と向きの許容差を使用する。
この許容差は過去の local 化の検証条件であり、新しい sampler、rebuild、近似計算の採用条件ではない。
新しい経路は、実行時間と制御挙動を計測し、E 空間および skin API の契約を壊さないことを確認する。

## 性能計測

root のみ、hip / knee、ring、Wave、build を分けて計測する。
warm-up 後に複数 batch を実行し、中央値と 95 パーセンタイルを記録する。
node 数の減少だけで高速化を主張しない。

root-only fixture では再計算された node を記録する。
collider と fit に root matrix 入力がないことを確認する。
skin、POSI、外部 constraint、custom step の評価回数は実測なしに root 非依存とは扱わない。

## 再検討条件

採用した sampler が操作時の制御挙動を維持できない場合、Wave の World 方向を維持できない場合、custom step が world 入力を再導入した場合に計画を見直す。
skin または cell の評価が残っていても、それが目標を妨げるほど支配的なコストになる場合に再検討する。
非一様 scale、反転、shear を本番要件にする場合は、root 変換契約自体を見直す。
