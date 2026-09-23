# 切断（seam）対応の配線し直し: 決定事項

Status: Decided and implemented (2026-09-22。C11 を含む。A3/A5 を round 1 裁定で補正。実装は cut-panels-wiring.md 参照)。
Plugin 側の契約: colliders/docs/plans/skirt-cut-panels.md（yddColliders 5.0.0、outputPatches）。

## A. 切断の指定（guide / settings）

| # | 決定 |
| --- | --- |
| A1 | seam は guide の文字列パラメータで指定する。ringPositions と同形式で「列間の位置, 開始行」を列挙する。 |
| A2 | seam の周方向位置は列と列の間に限定する。materialU は隣接 2 列の平均角から算出する。列が seam 上に乗る構成は作らない。 |
| A3 | seam の開始高さは grid 行に限定し、行番号 r（最初に切れる行）で指定する。plugin の物理段は脚参照で決まるため、r-1 行の t は通常 plugin の挿入行になる（起草時の「挿入行は発生しない」は誤り。fit の保護位置は plugin の出力行に対して成立するので支障なし）。 |
| A4 | panelHems は最下行の guide locator の高さから自動生成する。最下行だけ列ごとの高さを保持する。 |
| A5 | followRange を guide パラメータに出す（既定 0.1875）。referenceMaterialHeight は公開せず、surface_length（plugin の h_val と同じ、bellScale1 = 1）を自動設定する。round 1 裁定で「最下行の平均」から改めた（平均では短い列の wave の v が plugin の t とずれる）。 |

## B. 区画と grid の対応

| # | 決定 |
| --- | --- |
| B6 | 各列は一意に 1 区画に属する。隣接規則は「同じ区画内かつ seam 開始行より下では切る」。seam 下側の岸の cell の chain aim secondary 軸は片側隣接だけで作る。 |
| B7 | 行表示カーブは seam 開始行より下で区画ごとの open カーブに分割する。 |
| B8 | joint と control の数と命名（rows × cols、skirt_<col>_<row>）は不変。 |
| B9 | ring anchor の 8 方向 POSI は角度ごとに所属区画の面へ振り分ける。 |

## C. ノード配線

| # | 決定 |
| --- | --- |
| C10 | outputPatches[i].surface ごとに fit ノードと nurbsSurface shape を作る。uvPin は区画ごとに 1 個。索引は区画内列索引 × rows + row。 |
| C11 | deformer 連鎖（ringSkin → wave → postCollide）は区画ごとに独立のノードにする。host の anim パラメータから各 deformer へ接続する。 |
| C12 | 各 fit の protectedVParameters に outputPatches[i].vBreaks を接続する（構築時の値写しはしない）。 |
| C13 | wave は常に heightNormalization = ReferenceHeight、referenceHeight に outputReferenceHeight を接続する。seam なしでも同じ配線。 |
| C14 | component は常に outputPatches を読む。outputSurface は使わない。plugin 側に「seam なしでも区画 1 個の outputPatches を出す」変更を入れる。 |
| C15 | 列 U の角度校正は所属区画の面上だけで探索する。 |
| C16 | 互換は考慮しない。seam パラメータのない既存 guide は読み込めなくてよい。 |

## D. 検証

| # | 決定 |
| --- | --- |
| D17 | 既存のテスト群は維持する。component の受け入れは対象グラフに絞った mayapy テストを追加して行う。削除したのは質の悪い統合チェックだけで、全削除ではない。 |
| D18 | check_wave_component.py に依存する未追跡 3 本（check_local_evaluation.py、benchmark_skirt_component.py、benchmark_skirt_playback.py）は放置する。 |

## C11 の検討材料

アーティストが触る値は host の anim パラメータ（tightness、postFalloff、wave 系）で、
そこから deformer 属性へ connectAttr している。deformer が N 個でも host は 1 個なので、
アーティストから見える差はない。差が出るのは次の点。

- (a) 区画ごとに独立: Evaluation Manager で区画ごとに別タスクになり並列化できる。区画の再構築が局所で済む。ノード数は区画数 × 3。
- (b) 1 ノードに複数 geometry: ノード数が少ない。yddSkirtWaveDeformer と yddSkirtCollideDeformer は multiIndex で weights を引いており、ノード単位の状態は持たないので技術的には可。同一ノードの出力は 1 タスクにまとまり、区画間で並列化されない。
