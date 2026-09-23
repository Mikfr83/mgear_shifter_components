# ymt_skirt_01 列根元 FK オフセット配線契約

Status: Implemented（2026-09-23。実装 gpt-6-luna medium（契約 0 章の起草者の行で 1 回停止、再投入で完走）。オーケストレータの修正: columnMaterialU の setAttr の doubleArray 引数（要素数の前置を削除）、T17 のメタデータ plug、T18 の区画端の周期比較、T21 の node wrapper。Maya 2026 で T1〜T15、T17〜T21 の 20 件合格、T16 は plugin 側で検証。設定ダイアログの操作（T21 の手動部分）は未確認）
固定入力は [骨子](column-fk-wiring-outline.md) と [ADR-0013](../adr/0013-column-root-fk-offset.md)、plugin 側 ADR-0010 および docs/plans/column-fk-offset.md の Part 1、2.1、2.3、4 とする。
以下の「既存契約」は [cut-panels-wiring.md](cut-panels-wiring.md) を指す。
本書は既存契約への独立した追補であり、章内の十進番号とテスト番号の様式を引き継ぐ。
row、col、gap、E 空間、材料 U、区画の意味は既存契約のままとし、「既存 2.3」などの参照は既存契約の節を指す。

## 0. 範囲と所有権

| 所有 | 実装時の対象 |
| --- | --- |
| component（本リポジトリ） | 「__init__.py」「guide.py」「settingsUI.py」「README.md」、ADR-0013、tests/ymt_skirt_01/test_cut_panels.py |
| plugin（colliders リポジトリ） | yddColliders 5.1.0 の確定済み入力契約を利用する。変更対象なし。 |

「_ensure_ydd_colliders_plugin」の「yddSkirtBellCollider」の検査対象に「columnOffsetMatrix」と「columnMaterialU」を加える。
既存の属性存在検査を使い、版番号の文字列検査は追加せず、「columnFk=false」でも同じ plugin 要件を課す（component は platforms に同梱する 1 つの plugin だけを対象にし、旧 plugin との組合せを支持しないため）。
「_configure_collider」の既存設定は維持し、列入力の書き込みは 2 章の有効時の手順に置く。
脚角度からの自動駆動、mirror、キー付け補助、post-collider の cell ctl 変更は対象外とする。
実装では README に列根元 FK の操作、既定値、無効時の挙動を追記し、骨子に従って ADR-0013 を accepted へ更新する。

## 1. guide パラメータ

| 名前 | 型 | 既定 | 意味 |
| --- | --- | --- | --- |
| columnFk | bool | true | 列ごとの根元 FK ctl を作り、collider の事前変位へ接続する。false なら列 FK のサンプリング、group、anchor、ctl、列入力の設定をすべて省く。 |

「Guide.addParameters」で「pColumnFk」として「addParam」に登録し、保存対象の guide 属性「columnFk」を正とする。
「settingsUI.setupUi」に「columnFk_checkBox」を設け、表示文言を「Column FK」とし、既存の設定用 form の「formLayout」の未使用の行 19 の FieldRole に置き、行 0〜18 は変更しない。guide.py の populateCheck、stateChanged、updateCheck の追加も「wave_checkBox」の各記述の直後に置く。
「guide.py」の設定表示では「populateCheck」、変更時は「stateChanged」と「updateCheck」の接続を、既存の「addJoints_checkBox」と同じ作法で用いる。
「ringPositions」「followRange」と同じく、ダイアログを開いたときに root 属性から読み、操作時に root 属性へ書く。UI 独自の保存値は持たない。
構築では「_validated_bool_setting」で読み、不正値は既存の必須設定と同じ RuntimeError にする。columnFk 導入前に保存された guide には属性がないので、leg profile の前例と同じく、設定ダイアログを開いたとき（および Guide Manager の update）に guide.py が既定 true で属性を追加する。構築時に属性がない場合は既存の必須設定と同じ RuntimeError とし、構築側で黙って補わない。

## 2. 構築手順

既存 2 章の手順番号 1〜12 は変更せず、次の位置へ挿入する。

| 既存の位置 | 追加する処理 |
| --- | --- |
| 手順 1 | 0 章の属性存在検査を行う。 |
| 手順 2 の完了前 | 「columnFk」を検証し、既存どおり「nodes_before」を記録する。 |
| 手順 4（既存 2.3）の直後を 4a とする | 有効時のみ、seam なしの面から全列の rest フレームを計算し、数値として保持する。 |
| 手順 6（既存 2.4〜2.6 の完了後）の直後を 6a とする | 有効時のみ group、anchor、ctl を作り、単位行列検査、列入力の設定と接続、強制評価を行う。 |
| 手順 7 以降 | 既存 3 章の面と fit、ring、cell、deformer の順序を維持する。 |

### 2.1 rest フレームの採取（手順 4a）

「_calibrate_material_u」が得た「material_u[col]」を「U_col」とし、列番号順のまま使う。
同関数の一時ノードは終了時に削除されるため、直後に同じ接続の一時 transform、nurbsSurface shape、pointOnSurfaceInfo を作る。
「collider.outputPatches[0].surface」を shape の「create」へ、shape の「local」を sampler の「inputSurface」へ接続する。
採取の間だけ collider の「nodeState」を 1（HasNoEffect）にし、採取後に元の値へ戻す（Q1 裁定）。変更前の値は整数で保存し、設定と復帰は try と finally で行い、例外時も必ず復帰する。設定直後と復帰直後に「_force_patch_evaluation([0])」で再評価し、古い出力を採取しない。HasNoEffect の出力は solver 前の基準行そのものなので、腰行は plugin 契約 2.1 の C（segments[0].bottom）と一致し、構築姿勢での脚との接触や smoothing の影響を受けない。
この時点では seams、panelHems、列 FK 入力が未設定であり、面の U は材料 U と線形に対応する。
sampler の「turnOnPercentage」は false とし、「_surface_point」で「parameterU=U_col」「parameterV=0」を設定して「position」を読む。
続けて、parameter を変えずに同じ sampler の plug「<sampler>.tangentU」を「_plug_vector」で読む（position の読取と同じ parameterU、parameterV の設定の直後）。「turnOnPercentage」は false のまま、値は正規化せずに 2.1 の正規化へ渡す。「normalizedTangentU」や「tangentV」へ置き換えない。
「position」は「o=C(U_col)」、「tangentU」は「C′」とする。shape の「local」なので両者は E の値であり、world 行列を掛けない。
腰の未変形曲線との同一性は上記の HasNoEffect 採取で担保する（5.2 Q1 は裁定済み）。

フレームは骨子の式をそのまま用いる。

1. 「A=self.axis」（既存の単位方向、bellMatrix の Y）、「P=self.bell_matrix」の平行移動成分とする。
2. 「t=C′−(C′·A)A」、「T=t/|t|」とする。T は材料 U の増加向きであり、「cell_winding_sign」を掛けない。
3. 「r=(o−P)−((o−P)·A)A」、「q=r−(r·T)T」、「R=q/|q|」とする。楕円でも生の半径 r を R の代用にしない。
4. 「_matrix_from_axes(T,R,A,o)」で行 0=T、行 1=R、行 2=A、行 3=o、最終列=(0,0,0,1) の行列を作る。

正規化は既存「_normalize」を使い、E の長さを持つ t と q に「eps_len=1.0e-4 * guide_size」を適用する。
各長さが eps_len 未満なら列名と退化した量を含む RuntimeError とし、非有限の採取値や行列も既存の有限性検査で拒否する。
A は既存「_fit_bell_frame」の検証済み単位軸を用い、代替軸、符号反転、前フレーム保持は加えない。
一時 POSI と shape を含む transform は成功時も失敗時も削除し、以後は保持した数値だけを参照する。

### 2.2 group、anchor、ctl（手順 6a）

refs group（「colliderRefs」）は visibility が false で、その下の ctl は描画も操作もできない。そこで「skirtColFk_grp」は「ringCtls」と同じく「root」の直下に「self.getName」で作り、「decomposeMatrix」で「self.evaluation_ref_matrices["waist"]」（waistRef の matrix × offsetParentMatrix の E 行列 W、collider の bellMatrix と同じ plug）を translate と rotate に接続して腰に剛体追従させる（Q2 裁定、scale は接続しない）。駆動されるので「_lock_identity_group」は使わず、駆動チャンネル以外（scale、shear、visibility）だけをロックする。group の局所行列は W の回転と平行移動に等しく、anchor の rest フレームは常に現在の bellMatrix に対する rest フレームであり、plugin が各評価で bellMatrix から作り直すフレーム（plugin 契約 2.2: 評価をまたいで保持しない）と剛体運動の範囲で一致する。anchor と ctl は collider 出力に依存しない（W は入力側の multMatrix）。
各 col の anchor は group の直下に「self.getName(skirtCol<col>_fk_anchor)」として作り、「xform」の objectSpace 行列に「2.1 の E のフレーム × inverse(W)」を設定する。W は構築時に「_matrix_attr(self.evaluation_ref_matrices["waist"])」で読んだ E 行列（構築時は self.bell_matrix に等しい）であり、行ベクトル規約の「om2.MMatrix」で右から逆行列を掛ける。root や waistRef の「worldMatrix」、xform の worldSpace は使わない（root が非単位に置かれた構築で E とずれる）。E のフレームをそのまま objectSpace に書くと W が二重に掛かる。2.1 で保持した E のフレーム数値（T、R、o）は破棄せず、テストの期待値に使う。
anchor の offsetParentMatrix は identity のままとし、collider 出力、fit、pin、cell からの接続を作らない。
「_create_ring_controller」と同じく、anchor の評価済み「worldMatrix[0]」を「_matrix_attr」で読み、「datatypes.Matrix」にして addCtl へ渡す。この world 引数は初期配置にすぎず、ctl の rest は後述の明示初期化で決まる。
「_connect_anchor_surface_follow」の動的な追従配線は列 anchor へ転用しない。

「addCtl」の引数は、親が anchor の PyNode、名前が「skirtCol<col>_fk」（addCtl が既定の命名規則で接頭辞と拡張子 ctl を付けるので、実ノード名は addCtl の戻り値で決まる。本書の「skirtCol<col>_fk_ctl」はその戻り値を指す）、行列が上記 world フレーム、色が「self.color_fk」、形状が「circle」とする。「lp」は既定の true のまま（anchor は finalize でロックされてよい）。addCtl は controller tag、root の compCtl と rigCtlTags への message 接続、controllers 集合への登録を作るが、いずれもノードまたは接続なので後始末の差分削除で消える。component は group、anchor、ctl の実名を「self.column_fk_group」「self.column_fk_anchors[col]」「self.column_fk_ctls[col]」に保持し、テストはこれらを読む。
大きさは ring ctl の腰 station に準じ、「radius=_station_radius(0.0, self.row_axial_projections, self.row_mean_radii) * 1.1」、「w=radius * 2.0」とし、「tp=self.parentCtlTag」「wip=self.WIP」を渡す。
addCtl は行列の分解と再親付けを経るため local が近似 identity になる。そこで addCtl の直後に「_set_identity_transform」で ctl の translate、rotate、scale、shear、pivot を明示的にゼロと 1 に書き、ctl の offsetParentMatrix に identity を設定する。この初期化後の「matrix」は Maya が零の TRS から合成する厳密な identity であり、ctl の world は anchor の world と丸めの範囲で一致する。
初期化後に「attribute.setKeyableAttributes」へ tx、ty、tz、rx、ry、rz のみを渡し、sx、sy、sz は値 1、非 keyable、channelBox 非表示、ロックとする。
これは新規 ctl の初期化であり、評価された近似単位行列を plugin 側で丸める処理ではない。
初期化後に「_require_cell_matrix」に expected=identity、tolerance=0.0 を渡し、ctl の「matrix」と「offsetParentMatrix」を検査する（明示初期化後なので厳密一致が成立する。addCtl 直後の未初期化の値には許容差 0 を適用しない）。既存 cell の許容差 1.0e-6 は変更しない。

### 2.3 入力の設定、接続、後始末

書き込みの前に、較正済み material_u を昇順に並べ、隣接する列（最後と最初は周期差）の間隔が 1.0e-9 より大きいことを component 側で検証し、違反時は両列の番号と間隔を含む RuntimeError にする（plugin の条件 18 と同じ判定を先に行う。columnFk=false ではこの検証を行わない）。
全 ctl の検査後、「columnMaterialU」へ「[material_u[0], …, material_u[cols−1]]」を要素数 cols とともに「setAttr」の doubleArray として一度に設定する。
これは multi ではないため、「columnMaterialU[col]」という plug への個別接続は作らない。
各 ctl の「matrix」を「collider.columnOffsetMatrix[col]」へ直接接続する。論理索引は col と一致させ、U 順や panelId 順へ並べ替えない。
worldMatrix と rest 逆行列を結ぶ multMatrix は作らず、local の差分だけを plugin に渡す。
接続後は「_force_patch_evaluation(self.panel_ids)」で既存 2.6 と同じエラー検出を行う。
rest の入力は全列で厳密な identity なので、plugin 契約 Part 4 に従い接続前後の collider 出力は bit 一致する。実比較は T17 で行う。

手順 4a と 6a を、既存の手順 4〜6 を囲む try の保護範囲に含める。
失敗時は「nodes_before」と現在のノード集合の差を、既存どおり DAG の深い順に削除して RuntimeError を再送出する。
削除対象には一時 sampler、shape、列 FK group、anchor、ctl と addCtl が作ったノード、collider、refs、参照の multMatrix を含める。
既存ノードと mGear が addObjects より前に作った root は残し、手順 7 以降の失敗時の扱いは変えない。addCtl が作る shape、controller tag、set への登録は cmds.ls に現れるノードなので同じ差分削除で消える。root の「compCtl」multi に addCtl が追加した要素は ctl 削除で未接続の疎な索引として残るが、これは許容し、ロールバックは新規ノードの削除に限る。

## 3. 不変条件と非影響

| 境界 | 維持する内容 |
| --- | --- |
| 材料と区画 | 「_calibrate_material_u」の値、seam の U、区画所属、panelHems、panelId を変更しない。FK 後の位置から U を再較正しない。 |
| 面と fit | 既存の outputPatches と fit の接続を維持する。非単位入力でも区画数、次数、form、CV 数、ノット、裾対応、vBreaks は不変で、点位置が変わる。 |
| pin と cell | ADR-0011、ADR-0012 の E 入力、区画内 pin 索引、位置 offset、chain aim、cell ctl の階層と keyable を維持する。 |
| ring skin、wave、post collision | 既存の接続と順序を維持する。FK の点位置変化は collider 出力経由で届くため、下流の評価結果が常に不変という意味ではない。 |
| joints と relatives | 列 FK ctl を「fk_ctls」「fk_ctls_by_cell」「jnt_pos」へ混ぜず、skin influence にも追加しない。「addJoints」、col-major の joint 索引、setRelation の root と既存登録を維持し、列 FK の relatives、controlRelatives 登録を追加しない。 |
| E 空間 | anchor は waistRef に対する rest フレーム（構築時の E の値を waistRef の局所で表したもの）、plugin 入力はそのフレームの local 差分とする。root と waistRef の配置は DAG で適用し、差分入力へ持ち込まない。 |

plugin は列の変位を材料 U で補間し、切断済みの seam を越えず、岸では自区画側の端列の変位を保持する。
途中開始 seam の未切断行は共有のままであり、腰行も FK の適用対象となる。腰固定や列別 collider 重みは追加しない。
既存 T1〜T16 の要件を維持する。T16 は component テストでは skip される plugin 側の検査であり、skip を合格と数えない。

## 4. テスト T17〜T21（既存 9 章への追加）

実装時に tests/ymt_skirt_01/test_cut_panels.py の「CutPanelTests」へ追加し、既存の「Fixture」「_matrix」「_array」「_surface」「assert_connection」を使う。
Fixture は生成のたびに scene を初期化するため、別構築との比較値は Maya のハンドルではなく Python の数値列または bytes にして先に保存する。
bool の変更は Fixture の「guide.root.columnFk」へ build 前に書く。新たな Fixture 引数を前提にしない。
位置とフレームの近似比較は既存の「eps=1.0e-6 * max(1.0, component.guide_size)」、材料対応は 1.0e-9 を用い、厳密一致を指定した対象へは適用しない。

| # | 内容 | 期待 |
| --- | --- | --- |
| T17 | 既定 true と false の同じ Fixture を別々に構築 | 全列 identity、較正値と入力の一致、cols 個の直接接続、全区画の collider 出力の bit 一致。 |
| T18 | seam 2 本の両岸に接する列を local X に等量、逆向きへ動かす | 裾の岸間隔が増え、対応する腰 CV も動く。端値保持の変位と一致する。 |
| T19 | seam なしの reverse=false / true | 巻き方向 −1 / +1 の両方で local +X が材料 U 増加向き（保持した E フレームの T、面の tangentU の向き）になる。 |
| T20 | columnFk=false | 列 FK ノードと接続がなく、列入力が未設定のまま。 |
| T21 | guide の設定画面、保存、再読込 | bool が UI と双方向に同期し、true / false がそれぞれ保持される。 |

### 4.1 T17 と T20

T17 は「Fixture()」と「Fixture("1:2,5:2")」を各々 true / false で比較し、true 側では guide 属性を上書きせず既定 true も確認する。
各 ctl の「matrix」と「offsetParentMatrix」は「_matrix」で読み、16 成分すべてを identity と数値の厳密一致で比較する。
「columnOffsetMatrix」の multiIndices は「[0, …, cols−1]」、各要素の接続元は対応 ctl の「matrix」であり、要素の読み戻しも identity と厳密一致することを要求する。
「_array(collider.columnMaterialU)」は col 順の「component.material_u」と厳密一致させ、長さ cols を確認する。
比較する出力は全「outputPatches[id].surface」、各区画の「materialUStart」「materialUEnd」「vBreaks」「hemUSamples」「hemHeightSamples」、および「outputReferenceHeight」とする。
比較対象は「self.panel_ids」の各区画とし、「_surface」が返す MFnNurbsSurface の「cvPositions()」を格納順（Maya の U 優先の平坦順）に x、y、z、w の順で、続けて「knotsInU()」「knotsInV()」を struct の倍精度で連結した bytes と、「degreeInU」「degreeInV」「formInU」「formInV」「numCVsInU」「numCVsInV」の整数列を比較する。符号付きゼロも区別し、通常の float の等価比較や eps で代用しない。
panelId、次数、form、CV 数、配列長も一致させる。seam ありで禁止される「outputSurface」は要求しない。

T20 は同じ 2 種の Fixture で false を明示して構築し、「component.column_fk_group」「column_fk_anchors」「column_fk_ctls」が空（None または空の dict）であること、および「self.getName("skirtColFk_grp")」の名前のノードが存在しないことを調べる。
「columnOffsetMatrix」の multiIndices は空、「columnMaterialU」は既定の空 doubleArray、両属性への入力接続は空とする。
検査自身が「columnOffsetMatrix[0]」を読み、要素を実体化することを避ける。

### 4.2 T18 の岸間隔と腰行

「Fixture("1:0,5:0")」を使い、腰も両岸に分かれる条件で gap 1 を調べる。wave と post_collision は Fixture 既定の false とする。
FK の変位と solver の応答を区別するため、構築後に collider の「nodeState=1」（HasNoEffect）として基準を採り、同じ状態で操作後を採る。plugin 契約 2.4 により HasNoEffect でも列の変位は base に乗る（solver、relax、follow だけを省く）。
比較は fit や pin の出力を経由せず、「outputPatches[id].surface」の E 座標で行う。
「seam_material_u」と「panel_ranges」を周期差 1.0e-9 以内で照合し、対象 seam を終端に持つ区画 L と始端に持つ区画 R を選ぶ。
L の「panel_columns」の末尾列を cL、R の先頭列を cR とする。これが gap 1 の隣接 2 列であることも確認する。
「δ=0.1 * guide_size」を試験入力とし、cL の ctl.tx を −δ、cR の ctl.tx を +δ にする。他の ctl は identity のままとする。
δ は操作量であり、成功を判定する岸間隔の閾値ではない。
「_surface」が返す MFnNurbsSurface の「cvPosition(u, v)」で、L の最終 U 索引「numCVsInU−1」、R の先頭 U 索引 0 から、最終 V 索引「numCVsInV−1」の裾点 hL、hR と V 索引 0 の腰点 wL、wR を操作前後に採る（区画面の U は材料 U 昇順、V は腰から裾の順）。
合格式は「|hR_after−hL_after| > |hR_before−hL_before|」、かつ「|wL_after−wL_before| > 0」「|wR_after−wR_before| > 0」とする。増加量の下限は設けない。
端値保持は「hL_after−hL_before=−δ*T_cL」「hR_after−hR_before=+δ*T_cR」を各 E 成分 eps 以内で比較し、腰の各変位も同じ期待値と比較する。
T は 2.1 で保持した E のフレーム（「component.column_fk_frames[col]」の第 0 行）から読む。anchor の objectSpace 第 0 行は waistRef 局所の値なので E の T と直接比較しない（E に戻すには W の 3×3 を右から掛ける）。この検査は solver を通した全姿勢で岸間隔が単調に増えることまでは要求しない。

### 4.3 T19 の向き

seam なしの「Fixture(reverse=False)」と「Fixture(reverse=True)」（seams は既定の空文字。予約区画 0 だけが存在する）で「cell_winding_sign」がそれぞれ −1、+1 であることを T11 と同じ方法で確認する。
各列を独立に調べ、毎回全 ctl を rest に戻し、対象 ctl.tx のみ +δ（T18 と同量）へ変更する。出力は T18 と同じ HasNoEffect で採る。
操作前の予約区画 0 を POSI で「u=material_u[col], v=0」に採り（collider は HasNoEffect）、tangentU から 2.1 の T を求め、「component.column_fk_frames[col]」の第 0 行と各成分 eps 以内で比較する。
同区画の「u=material_u[col]」と、区画面の V ノット域を等分した 3 点の v における点を操作前後に採り、その列の変位について「平均(after−before)·T > 0」を要求する（fit 面の surface_v_values は collider 面の V 域と異なるので使わない）。
角度の増減は巻き方向で符号が変わるので要求しない。T は材料 U 増加向きに固定されており、判定は保持した E フレームの第 0 行との一致と「平均(after−before)·T > 0」だけとする。col 番号増加と材料 U 増加を同一視しない。

### 4.4 T21 と実行環境

「Fixture()」の guide を選択して settings を開き、既定で root の「columnFk」とチェック状態がともに true であることを確認する。
チェックを false にして root 属性が false、閉じて開き直しても false であることを確認し、root 属性を true に変更して再表示したとき true になることも確認する。
false と true のそれぞれで guide scene を試験用一時ファイルへ保存し、新規 scene から再読込して root 属性、Guide の「setFromHierarchy」後の values、再表示したチェック状態を厳密な bool 一致で比較する。
T21 は Qt が要る手動検査とし、mayapy の gate（run_component_tests.bat）の合否に含めない。テストコードでは guide の root 属性の保存と再読込（一時ファイルへの保存、新規 scene での読込、Guide の setFromHierarchy）までを自動化し、ダイアログの操作は README に手順を書いて手動で確認する。保存ファイルは試験が所有する一時領域に限る。
T1〜T15 と T17〜T20 は既存の mayapy 実行方式、T16 は plugin 側で検証する。WSL からの Windows 実行は既存の bat を cmd.exe /c 経由で使う。
本書の起草では Maya の実行結果を取得していない。

## 5. 反例と未決の問い

### 5.1 検討した反例と本文の扱い

| 反例 | 本文の扱い |
| --- | --- |
| col 順、角度を割った U、区画内 U を plugin の材料 U と取り違える。 | 2.1 と 2.3 は較正済み材料 U と col の論理索引を別々に固定し、T19 は巻き方向の両方を検査する。 |
| anchor を cell npo の下へ置く、または ring と同じ surface follow を接続すると循環する。 | 2.2 は root 側の静的親と採取済み行列だけを使う。 |
| world の差分を入力すると root の配置を拾う。 | 2.3 は ctl.matrix を直結し、余分な multMatrix を作らない。 |
| 近似 identity を受理すると bit 一致が成立しない。 | 2.2 は明示初期化と許容差 0 の検査、T17 は出力の bytes 比較を行う。 |
| seam の両岸を平均する、外挿する、腰だけ固定すると操作が届かない。 | plugin の端値保持と全行適用を維持し、T18 で裾と腰を分けて検査する。 |
| FK ctl を既存の fk_ctls に足すと root relative や joint 索引が変わる。 | 3 章は cell の登録列へ混ぜない。 |

### 5.2 二通りの読みで結果が変わる未決事項

| 問い | 二通りの読みと未確定の影響 |
| --- | --- |
| Q1 採取する腰曲線は未変形か（裁定済み） | HasNoEffect（nodeState=1）で採る。solver 前の基準行が出力されるため plugin の C と一致する。 |
| Q2 構築後に腰参照が変化したときの rest（裁定済み） | anchor 群を waistRef の下に置く。腰の剛体運動では ctl の見た目の軸と plugin の現在フレームが一致する。bellScale の変化など非剛体の変化では一致しないが、それは許容する。 |

T18 と T19 の採取（HasNoEffect）は 2.1 の採取と同じ状態である。テストが anchor の第 0 行（T）を E で読むときは、anchor の objectSpace 行列に構築時の waistRef の E 行列（self.bell_matrix）を右から掛けて E に戻す。
