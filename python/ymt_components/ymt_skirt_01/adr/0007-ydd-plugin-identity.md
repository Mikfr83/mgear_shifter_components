# ADR-0007: yddColliders の利用

Status: Proposed
Date: 2026-09-10
Owner: ymtshiftercomponents maintainers
Supersedes: ADR-0001 から ADR-0006 のプラグイン名とノード型名、Component と Guide のバージョン
Superseded by: none

## 判断

fork 元との同時利用を可能にするため、プラグインを `yddColliders`、ノード型を `yddSkirtBellCollider`、`yddSkirtCollideDeformer`、`yddSkirtWaveDeformer` に変更する。
Component と Guide の `VERSION` は `[3, 0, 0]` とする。
識別子の正本は colliders 側の [ADR-0003](../../../../../../../colliders/2.1.0/colliders/docs/adr/0003-ydd-plugin-identity.md) とする。

旧 `colliders` がロードされていても、構築時には `yddColliders` を別にロードして登録ノードを確認する。
旧名で作成する代替経路は残さない。
作成するカスタムノードの型名と型名に由来するインスタンス名、エラーメッセージ、履歴検証を揃える。

ガイドのパラメータ、ホスト属性、リング、衝突、Wave の計算と変形順は維持する。
旧ノードの型名と ID は継承しないため、旧リグは再構築または別途移行を必要とする。
旧バイナリを通常のプラグイン検索パス外に保存してから、Maya 2022 から2027の配置先を `yddColliders.mll` に切り替える。

## 選択肢と影響

旧名も扱う分岐を残す案は、ロード順で利用する fork が変わるため採用しない。
プラグインの識別子を一つに固定し、ノード、属性、変形順の既存検証を新名に更新する。
Accepted の ADR-0005 は変更せず、この ADR が識別子とバージョンの記述を置き換える。

## 検収と再検討

fork 元を同時ロードした状態を含め、実際の mGear リグを構築して新ノードの利用と形状出力を確認する。
登録済みのグローバル ID を取得する場合や、旧リグを一括移行する必要が生じた場合は、colliders 側の正本と合わせて契約を見直す。

2026-09-10に配置済みバイナリで3構成の実リグ構築、fork 元のみのロード状態からの自動ロード、形状の一致を確認した。
結果は colliders 側の [検収記録](../../../../../../../colliders/2.1.0/colliders/docs/validation/ydd-identity.md) に記載した。
