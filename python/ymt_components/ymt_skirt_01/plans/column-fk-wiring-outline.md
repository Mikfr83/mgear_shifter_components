# ymt_skirt_01 列根元 FK オフセット配線の骨子（契約起草の入力）

決定: 本コンポーネントの adr/0013-column-root-fk-offset.md と colliders の docs/adr/0010-column-fk-offset.md。
plugin 側の契約: colliders/docs/plans/column-fk-offset.md（Implemented、yddColliders 5.1.0、入力は columnOffsetMatrix（multi 行列）と columnMaterialU（doubleArray、要素の論理索引で対応））。
本書は起草者に渡す骨子で、構造と判断は固定。既存の配線契約 plans/cut-panels-wiring.md の用語（row、col、gap、E 空間、材料 U、区画）と様式に従う。

## 受け入れるもの

- guide パラメータ columnFk（bool、既定 true）。settingsUI にチェックボックス。false なら本書の構築を全て省き、collider の columnOffsetMatrix と columnMaterialU は未設定のまま。
- 列根元の rest フレーム（E 空間）。plugin 契約 Part 2.1 と同じ定義: 原点 o = C(U_col)（腰の未変形曲線を列の較正済み材料 U で評価した点）、A = ベル軸の単位方向（既存の self.axis、bellMatrix の Y）、T = normalize(C′ − (C′·A)A)（材料 U 増加向き）、R = normalize(r − (r·T)T)、r = (o − P) − ((o − P)·A)A、P は腰の参照位置（bellMatrix の平行移動）。C と C′ は材料 U の較正と同じ seam なしの outputPatches[0] を collider nodeState=1（HasNoEffect）で pointOnSurfaceInfo で (u=U_col, v=0) にサンプルして position と tangentU から取る（面の U は材料 U と線形、v=0 は腰行）。フレーム行列は行ベクトル規約で行 0 = T、行 1 = R、行 2 = A、行 3 = o。
- ノード: waistRef（bellMatrix を駆動する参照 transform）配下にグループ skirtColFk_grp（identity、ロック）、列ごとに anchor（skirtCol<col>_fk_anchor、objectSpace 行列 = rest フレーム）、その下に ctl skirtCol<col>_fk_ctl を addCtl で作る（ring controller と同じく anchor の評価済み worldMatrix を ctl のフレームに渡し、ctl.matrix が厳密に identity になるようにする）。keyable は tx ty tz rx ry rz、scale は非表示ロック。形状と大きさは ring ctl に準じ、色は color_fk。
- 接続: ctl.matrix（local）→ collider.columnOffsetMatrix[col]（論理索引 = col）。columnMaterialU = [material_u[0], …, material_u[cols−1]]（col 順）を setAttr。anchor と group は collider 出力に依存しない（循環禁止）。
- 構築位置: 材料 U の較正（2.3）の直後に rest フレームを計算し、seams と panelHems の書き込み（2.4〜2.6）の後、区画ごとの面と fit（3 章）の前に anchor と ctl を作って接続する。rest では全 ctl.matrix が identity なので collider 出力は接続前と bit 一致。
- 失敗時: 手順 4〜6 と同じ後始末（ノード削除して RuntimeError）。
- relatives: fk ctl は relatives / controlRelatives に登録しない（root は既存のまま）。addJoints に影響なし。ring skin、wave、post collision に影響なし。
- README に節を追加。adr/0013 を accepted へ。
- テスト（tests/ymt_skirt_01/test_cut_panels.py に T17 以降として追加、既存の Fixture を使う）: 
  T17 columnFk 既定 true で構築し、全 ctl.matrix が identity、columnMaterialU が較正値と一致、columnOffsetMatrix の要素数が cols、collider 出力が columnFk=false の構築と bit 一致。
  T18 seam 2 本の fixture で seam 隣の 2 列の ctl を local +X / −X に等量動かすと、その seam の両岸の裾 CV の間隔が増え、腰行の対応 CV も動くこと（plugin 契約の端値保持と腰行適用の確認）。
  T19 巻き方向 ±1 の両方で、ctl の local +X が較正済み材料 U 増加向き（列の平均角度の増加向き）へ列を動かすこと。
  T20 columnFk=false で ctl も接続も作られず、plugin の属性が未設定であること。
  T21 guide の columnFk が settingsUI と同期し、保存と再読込で保持されること。

## 対象外

- FK の自動化（脚角度からの駆動）、mirror、キー付けの補助。
- plugin 側の変更（5.1.0 の契約は固定）。
- post-collider の cell ctl の変更。

## 守る不変条件

- ADR-0010 の E 空間の境界（collider は E の値を受ける）。ADR-0011 の cell フレームと pin。ADR-0012 の区画配線。
- 較正済み材料 U（_calibrate_material_u）の値と seam の U をそのまま使う。
- 既存テスト T1〜T16 の合格。

## 採用しない代替案

- worldMatrix × rest 逆行列の multMatrix（ctl.matrix の直接接続で足り、root の変換の影響も受けない）。
- cell の npo の下に置く（collider 出力に依存し循環する）。
- 列 FK を skin joint にする（collider 入力であり、変形は collider 出力経由で届く）。
