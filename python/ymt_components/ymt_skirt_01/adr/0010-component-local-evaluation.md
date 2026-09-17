# ADR-0010：コンポーネント局所空間での評価

Status: Proposed  
Date: 2026-09-14  
Owner: ymtshiftercomponents maintainers  
Supersedes: 採択後に ADR-0005 と ADR-0008 の座標入力および親逆行列に関する決定を置換する  
Superseded by: none

## 決定

コンポーネントは、構築時の root に対して定義した評価空間 E で collider surface と参照行列を評価する。
保存済み guide は world matrix のまま保持し、構築時に取得した root 行列の逆行列で参照と grid を E へ変換する。

再構築 surface は local channel を identity、`inheritsTransform=True` とする。
CV と downstream の `local` データは E の値であり、表示時に root DAG が一度だけ配置を適用する。

major 4 の plugin 契約は object-space-only とする。
`yddSkirtBellCollider`、`yddSkirtCollideDeformer`、`yddSkirtWaveDeformer` は E の geometry と参照行列を受け取り、`localToWorldMatrix` による変換を行わない。
World/Object の評価切替は設けない。

7 個の参照出力を collider と post-collision deformer で共有する。
各参照は `matrix × offsetParentMatrix` と親の E 行列を合成する。

ring skin は influence 登録と bind pose を維持し、E の anchor 行列、live な inverse bind-pre 行列、identity の `geomMatrix`、E の入力 geometry を使う。
`skinPercent` と `MFnSkinCluster` が必要とする Maya の接続を維持する。

Wave の `World` 方向は、E から World への回転だけを持つ hidden input `evaluationToWorldRotation` で意味を維持する。
Bell Local 方向は従来どおり bell のローカル方向として扱う。

## 理由と不採用案

従来の graph は root 変換を collider、skin、cell の計算へ運び、親逆行列で相殺していた。
E の境界を設けることで、表示配置を DAG 境界に残したまま、評価経路の反復変換を除去できる。

`worldSpace[0]` を `local` に変更するだけでは、world 依存の参照行列が残る。
`transformGeometry` は評価 graph 内に root 依存を残す。
`inheritsTransform=False` は別の表示配置契約を必要とする。
これらは採用しない。

対応する root 変換は、回転、平行移動、正の一様スケールとする。
非一様スケール、反転、shear は構築時に拒否する。

## 影響

既存 guide の保存形式は維持するが、旧 rig をその場で更新しない。
新しい rig は major 4 の plugin と component で再構築する。

collider と rebuild は root 行列入力なしで評価できる。
skin と外部 cell constraint の dirty 経路は Maya 標準処理または custom step に依存するため、別途計測する。

Wave の E 出力は root を通じて表示し、World 方向の変更は `evaluationToWorldRotation` を通じて再評価する。

性能改善では、精度の完全一致を採用条件にしない。
実行時間と、操作時の制御挙動および E 空間の契約を満たすことを基準に実装を選ぶ。
rebuild、cell sampler、Wave と collision の近似計算を含む collider 側の方針は、[collider の ADR-0007](../../../../../../../colliders/2.1.0/colliders/docs/adr/0007-performance-first-evaluation.md) とその計画へ委譲する。
コンポーネント側では、その方針に従う単一の実装だけを採用し、旧実装との切替や互換 shim は設けない。

詳細な graph 作業と計測は[実装計画](../plans/local-evaluation-and-performance.md)に記録する。
実装の出力比較と計測結果は[検証記録](../../../../../../../colliders/2.1.0/colliders/docs/validation/component-local-evaluation.md)を参照する。

## 再検討条件

非対応の root 変換、world-space plugin 入力を要求する custom step、Wave の World 方向意味の維持不能が要件になった場合に再検討する。
skin または cell の評価が残ること自体は既知なので、操作時の制御挙動を保った最適化でもコストが支配的な場合に collider 側の ADR を再検討する。
