# 列 FK 配線契約 レビュー第 1 ラウンドの裁定（2026-09-23）

対象: plans/column-fk-wiring.md（astra high 起草、Q1 HasNoEffect 採取・Q2 waistRef 追従を裁定後）。レビュアー: sonnet（6 件）、Muse Spark 1.3 high read-only（15 件）、Grok high（8 件）。採用基準は反例つき。

| 出所 | 指摘 | 裁定 | 反映 |
| --- | --- | --- | --- |
| sonnet 1 / Muse 1 | anchor の objectSpace に E のフレームを直接書くと bell_matrix が二重に掛かる | 採用 | 2.2: E フレーム × inverse(self.bell_matrix) |
| sonnet 2 / Muse 2 | addCtl の分解再合成で local が厳密 identity にならず、許容差 0 が失敗する | 一部採用 | addCtl 直後に _set_identity_transform で明示初期化してから許容差 0 で検査（零 TRS の合成は厳密 identity）。cell の 1e-6 は据え置き |
| sonnet 3 / Muse 12 | T19 で seam ありの Fixture では予約区画 0 が存在しない | 採用 | T19 は seam なし Fixture に限定、V は collider 面の V 域から取る |
| sonnet 4 | 存在しない mock の作法を要求 | 採用 | 文を削除 |
| sonnet 5 | 列同士の材料 U 間隔（plugin 条件 18）を component が事前検証しない | 採用 | 2.3 に事前検証を追加 |
| sonnet 6 / Muse 9 | addCtl の副作用（root.compCtl の疎索引、shape、set）の後始末 | 採用 | 2.3: ノードは差分削除で消える、compCtl の疎索引は許容 |
| Muse 3 | nodeState を try/finally で復帰、dgdirty | 採用 | 2.1 |
| Muse 4 | T19 の「角度増加」は巻き方向と両立しない | 採用 | 角度の要求を削除、T 方向成分のみ |
| Muse 5 | root の一様 scale と変位の単位 | 棄却 | ctl.matrix は親の scale を含まない E 単位。collider も E で解き root の DAG で一度だけ scale される（ADR-0010）ので ctl と面は同じ倍率で表示される |
| Muse 6 | tangentU の plug 名と読取手順 | 採用 | 2.1 |
| Muse 7 | 旧 guide に columnFk 属性がない | 採用 | 1 章: 設定ダイアログ / Guide Manager が既定 true を追加（leg profile の前例） |
| Muse 8 | UI の配置行が未定 | 採用 | wave_checkBox の直後 |
| Muse 10 | bytes 比較の手順と対象が未定義 | 採用 | 4.1 に cvPositions、knots、degree、form、CV 数の連結を明記 |
| Muse 11 | cvPosition の写像、HasNoEffect で FK が無効化される読み | 採用（写像を明記） / 棄却（plugin 契約 2.4 で HasNoEffect でも FK は乗る） | 4.2 |
| Muse 13 | T21 は mayapy で実行不能 | 採用 | Qt 部分は手動、保存再読込は自動 |
| Muse 14 | columnFk=false でも 5.1.0 を要求 | 棄却（理由を明記） | 0 章 |
| Muse 15 | plugin が rest を静的保持する読み | 採用（前提を引用） | 2.2 |
| Grok 1 / 2 | anchor の objectSpace の逆行列は構築時に読んだ W（evaluation_ref_matrices の waist）で、worldMatrix は使わない | 採用 | 2.2 |
| Grok 3 | refs group は非表示なので、その下の ctl は描画されない | 採用 | 2.2: group は root 直下、decomposeMatrix で W の translate と rotate を接続 |
| Grok 4 | anchor 第 0 行は waistRef 局所で E の T ではない | 採用 | T18 / T19 は保持した E フレームを使う |
| Grok 5 | addCtl 直後に許容差 0 を掛けると落ちる | 採用（明示初期化後に限ると明記済み） | 2.2 |
| Grok 6 | addCtl の命名規則と副作用（tag、compCtl、集合）、T20 の裸名検索 | 採用 | 2.2 / 4.1: 実名は戻り値、component が保持 |
| Grok 7 | mock の作法は存在しない | 採用（sonnet 4 と同じ、削除済み） | |
| Grok 8 | UI の行番号 | 採用 | 行 19 |

