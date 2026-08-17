# VoyageSkill 架构与代码评审报告

评审日期：2026-08-14　评审对象：/Users/xp/code/voyage-skill（v0.1.0）
评审方式：三个并行只读分析线程（源码、契约与测试、文档体系）+ 评审者逐行通读全部运行时代码（core.py 951 行、cli.py 431 行）交叉验证 + 行业实践对照

## 执行摘要

VoyageSkill 是一个面向长周期多智能体软件工作的项目级操作控制系统。其核心运行时——追加式哈希链账本、全量重演的状态机校验、原子写与文件锁——实现质量高于同体量项目的常见水平，"每条事件提交前必须通过全部不变量重演"的设计从根本上保证了经 CLI 写入的状态永远自洽。当前最大的风险不在代码内部，而在三个已发生且无人监护的漂移：schemas/ 是与代码零接线的"死契约"，且仓库自身的真源注册表已违反自家 schema；规范文档对恢复协议与工作/规则状态机的承诺超出实现；CLI 约 24 个子命令在任何权威文档中均无记载。三者都直接削弱项目最核心的卖点——"真源可验证、恢复可重放"。修复成本低，建议优先处理。

## 背景与评审方法

VoyageSkill 以 Skill 形态分发（SKILL.md 入口 + agents/openai.yaml 平台元数据），运行时为零第三方依赖的 Python 3.9+ CLI（scripts/voyage.py → src/voyage_skill/），通过 init/validate/recover 等命令管理项目控制面（.voyage/ 目录），辅以 6 个 JSON Schema、11 份治理/设计文档与 18 个单元测试。项目已自我托管：仓库根的 .voyage/ 由自家 CLI 初始化，账本含 project.initialized 与 decision.recorded 两条事件，哈希链衔接成立。

本次评审由三个只读分析线程并行执行：源码线程负责模块地图与命令链路数据流；契约线程负责 6 个 schema 与代码的一致性、agents/ 配置、.voyage/ 自托管状态与测试覆盖；文档线程负责 11 份文档的权威层级与文档-代码一致性。所有关键结论由评审者通读完整源码后复核，行号引用以当前工作区为准。外部参照来自微信公众号近一年的多智能体工程治理与 Agent Skills 实践文章（见参考资料）。

## 架构评估

### 总体架构

架构为严格的单向三层：scripts/voyage.py（12 行免安装 shim）→ cli.py（431 行，argparse 两级子命令，负责参数到事件载荷的映射与 JSON 输出）→ core.py（951 行，全部领域逻辑，仅依赖标准库）。无循环依赖，无全局可变状态，数据一律落盘于 .voyage/（manifest、graph、resources、gates、ledger、evidence）。控制面单一入口 project_paths()（core.py:87-113）统一解析 manifest，并对全部 6 个路径字段做逃逸防护（core.py:97-100），是干净且安全的控制面设计。

三条主链路数据流清晰：init 做防护检查后原子写入 5 个控制文件与可选模板文档，随后以 append_event 追加首事件（core.py:121-236）；validate 依次校验 manifest、真源注册表（含单 domain 单 active 源约束，core.py:829-831）、graph、resources、gates、账本哈希链，零错误时完整重演全部状态机不变量（core.py:796-873）；recover 先跑完整 validate，再输出含 ledger_head、逐工作项 next_safe_action、租约过期标注与易变资源复探清单的快照（core.py:909-934）。

### 值得保留的设计亮点

其一，append_event 在持有排他 flock 的临界区内先重放全链校验完整性、构造新事件、再将"旧事件 + 新事件"完整重演一遍，不变量通过后才追加并 fsync（core.py:715-741）——任何违反状态机、职责分离或强制门的事件在 CLI 路径上根本无法落账，校验即写入。其二，JSON 写全部走临时文件 + fsync + os.replace 的原子写（core.py:72-84），崩溃不会留下半写文件。其三，职责分离不是文档口号而是代码不变量：执行者不能给自己的交付做质量终审（core.py:488）、规则提议者不能自批（core.py:639）、应用者不能自验（core.py:653）、阻塞发起者不能自解封（core.py:565-566），且门禁结果必须锚定当前交付锚点（core.py:505,528）。其四，register_resource 在事件追加失败时回滚资源文件（core.py:781-793），具备基本的补偿意识。这些机制与行业近期讨论的"Harness 分层治理"与"消息治理优于消息传递"的方向一致。

## 代码质量评估

核心逻辑集中在一个 386-698 行的大 if/elif 事件分发（replay_events），26 种事件类型每种 5-15 行，当前体量下可读性尚可，但已接近单文件舒适区上限；新增事件类型需同时触碰 replay、CLI、测试三处，扩展成本随事件数线性上升。命名、类型标注（from __future__ annotations 全覆盖）、错误消息质量均属上乘，VoyageError 统一承载确定性错误的约定清晰。

发现的代码级问题如下，均已逐行核实。确定性校验器存在未包装异常路径：validate_project 只捕获 VoyageError（core.py:871-872），而 replay 直接以 payload["expires_at"]（core.py:613）、event["type"] 等键索引（core.py:401-404）——手工篡改或损坏的账本事件若缺这些键，会先通过哈希链字段检查（payload 仅检查"是对象"，core.py:339-340），再在重演阶段抛出裸 KeyError，使 validate 以 traceback 而非结构化错误报告崩溃；这正是该系统最应鲁棒应对的"人工改账"场景，属中危缺陷。质量计数校验存在层间不对称：gate.recorded 在 core 层校验计数自洽（core.py:511-513），quality.passed/rejected 却只在 CLI 层校验（cli.py:257-260），直接 API 调用可写入不自洽计数（core.py:496）。每次追加都做全链加载加全量重演，追加成本 O(n)、累计 O(n²)，对"长周期项目"这一定位构成可预见的扩展性天花板，当前规模可接受但应记入决策。fcntl（core.py:3）使运行时仅支持 Unix，与 README "any Python 3.9+ package installer" 的平台口径存在出入。事件 subject 语义不一致：resource.claimed 的 subject 是资源 ID，而 release/recover 的 subject 是租约 ID（cli.py:326-340），给按 subject 追溯事件流的消费者制造歧义。init 无失败回滚，中途失败会留下部分初始化的 .voyage/。next_safe_action 中 canceled 与 superseded 两个分支（core.py:949-950）无任何事件可达，属死代码，其根源在文档-代码漂移（见文档体系评估）。

## 契约层评估

这是评审发现的最系统性问题。结论明确：schemas/ 下 6 个 JSON Schema 是死文档——全库检索确认运行时代码从不加载、解析或校验它们（无 jsonschema 依赖，setup.cfg 无 install_requires，README 明示零第三方依赖），代码中的 "schema" 仅是硬编码常量 SCHEMA_VERSION（core.py:18）。实质是两套平行契约：手写校验与 JSON Schema 互不完全等价、各自漂移。

漂移已经发生且有实锤：仓库自身 dogfooding 的真源注册表 docs/truth-registry.json:4 含顶层 updated_at 字段，违反 truth-registry.schema.json:28 的 additionalProperties:false——按自家 schema，当前规范注册表是非法文件，而 voyage validate 发现不了它，因为代码只查 active 源的 domain/path 存在性（core.py:814-818）。抽样比对显示两套契约双向分叉：一致面（事件 12 个必需字段、资源 type/mode 枚举、manifest 8 字段）吻合良好；但代码校验是 schema 的真子集且已弱化六处——事件不拒额外属性（core.py:317-343 vs event.schema.json:24）、manifest 的 project_id 存在性与格式从不校验（core.py:800-801 vs manifest.schema.json:6,9）、gates 仅要求"数组加字符串 id"（core.py:372-383 vs gates.schema.json:13 的四必需字段）、graph 不查 uniqueItems 与四 loop 完备（core.py:836-838 vs graph.schema.json:9-15）、真源非 active 条目字段不查（core.py:814-818 vs truth-registry.schema.json:14）。反向地，代码也有 schema 没有的条款（单 domain 单 active 源、哈希链、状态机），且 gates.schema.json:18 把 required_loop 限死为 quality，与 core.py:507-508 的泛化读取形成名义冲突（实际因 core.py:501 已强制 quality 而不可达，属冗余死条款）。二选一即可：接入 jsonschema 校验让 schema 活过来，或删除/降级其为"仅供参考"并从文档移除其规范地位——维持现状等于对外宣称了一个无人执行的契约。

另有两处契约周边问题：agents/openai.yaml（3 行平台展示元数据）在仓库内零引用，其 short_description 与 SKILL.md:3 的 description 双源维护、漂移不可检出；docs/truth-registry.json 中 D-0001 的 version 记为 "1"，而 D-0001 文档头并无 Version 字段，版本主张无出处。

## 测试评估

18 个测试用例（test_core.py 15 + test_cli.py 3）质量中上：全部以临时目录隔离、CLI 测试走真实子进程端到端黑盒、错误断言精确到消息文案、并已有首个安全纵深测试（哈希篡改检测）。覆盖面上，工作流主链（create→authorize→start→deliver→quality pass→accept→close）、关键职责分离不变量、资源冲突、哈希篡改均有覆盖。

盲区集中在三处。租约时间语义从未执行：所有测试把过期时间写死 2099 年，parse_time、new_lease_expiry、active_leases 的 expired/recovery_required 分支（core.py:884-906）零覆盖，recover 输出的"易变资源复探"清单因此从未被验证。事件类型覆盖约三分之二，quality.rejected、resource.released/recovered、observation/channel/environment/audit 等 8 种事件及"未知事件类型"错误路径（core.py:694）未测；CLI 层 status、gate record、resource claim/release/list、rule 全部 6 子命令、event record 未测。最具系统性的是两个缺失的守护测试：没有任何 fixture 对照 schemas/ 做 schema 回归（死契约无人监护，updated_at 漂移即直接后果），也没有"对仓库根 .voyage/ 执行 validate"的自检测试（dogfooded 状态腐化不会报警）。补这两个测试各只需几十行，收益远超成本。

## 文档体系评估

文档层级声明基本自洽：README → truth-registry → 5 份 active 规范（product/governance/system/operations/D-0001），SKILL.md 自称稳定入口而非项目状态，design/ 与 research/ 的降级声明是明显亮点（v0.1-proposal 头部准确声明了自身历史地位且与 D-0001 逐条吻合）。无悬空 markdown 链接，README quick start 三条命令经核对可运行。

问题集中在规范对代码的承诺超出实现，共四处实锤。第一，恢复协议四类状态不可达：SKILL.md:27-28 与 runbook 承诺恢复输出"区分 observed、declared、unknown、conflicting 四类状态"，recovery_snapshot 实际输出 work/active_leases/active_blocks/rules/volatile_recheck_required（core.py:924-934），没有任何四分类——这直接伤"可无记忆接班"的核心卖点。第二，工作生命周期漂移：graph.md:53-60 定义了 ready 态与 canceled/superseded 侧态，实现中 work.started 从 authorized 直进 active（core.py:449-460），无任何事件可达 canceled/superseded（next_safe_action 两个分支因此成为死代码）。第三，规则生命周期漂移：authority.md:55-58 定义 verified 独立态与 deprecated 态，实现中 rule.verified 直置 active（core.py:649-655）、无 deprecated 事件；这是"有意裁剪"还是"实现缺口"无任何 ADR 记录。第四，CLI 命令面整体未入文档：runbook 的九步 Work protocol 只出现 validate/recover/resource register，而代码实现的 work 11 个子命令、gate record、resource claim/release/recover/list、rule 6 个子命令、event record 全部未出现在任何权威文档——新成员越过 recover 后只能读 --help 和源码，与项目"文档即权威操作协议"的定位存在系统性落差。

此外，init 模板与官方文档布局不兼容：init 生成的注册表指向 docs/voyage/{product,governance,system,operations}.md 且 source id 为 product 等（core.py:186-192），而 SKILL.md:54-58 的指针指向 docs/product/contract.md 等本仓库 dogfood 布局——对新 init 的项目，SKILL.md 的 5 个权威指针全部落空。registry 与 SKILL.md 的非权威名单也不逐字一致（registry 含 docs/design/，SKILL.md 未提）。research/graph-engineering.md 是唯一未标"非权威"横幅的研究文档，内含旧项目自进化指令与硬编码外部路径，新成员易误读为可执行指令。最后，权威栈顶层未形式化：SKILL.md 与 README 均不在 registry 的 sources 中，"registry 是最高权威"靠惯例维系，无 decision 锚定；decisions/ 目前只有 D-0001，而 general-pm-skill-proposal（2026-08-14 草案）已处于"活跃设计意图但无决策锚点"的灰色状态超过一天。

## 综合分析

把三个线程的发现叠在一起，浮现出同一个元问题：这个项目最擅长保证的事（不变量可机器校验、历史可重放）目前只覆盖了运行时层，而规范层与契约层没有任何防漂移机制。代码内的不变量由重演强制；但 schemas、SKILL.md 指针、runbook 承诺、状态机文档这些"关于系统的陈述"没有任何等价物去校验它们——于是 updated_at 混进注册表、ready 态留在文档里、约 24 个命令只存在于代码里。项目自己的方法论（真源注册、单一 active 源、决策留痕）正是解药：为"文档承诺 vs 实现"建立校验回路（哪怕只是 CI 里一个对照脚本加一个 dogfood 自检测试），比继续扩张功能更符合项目自身哲学。

对照外部实践：近一年中文技术社区的讨论集中在多智能体 Harness 分层治理、消息治理（"哪些话值得被系统听见"）、编排税，以及 Agent Skills 的"简洁入口加渐进披露"惯例。VoyageSkill 的四环职责分离、证据强制（block/quality/lease 均要求 evidence）、append-only 账本与这些方向高度吻合，SKILL.md 的入口设计也符合 Skills 最佳实践；其差异化资产恰是 recover 协议，因此恢复输出承诺与实现的落差应排在修复优先级最前。另需明确信任模型的边界：actor 身份无认证，任何 CLI 调用者可自称任意 loop（仅由 coordination_boundary: single-repository-single-machine 隐含背书）——系统是防篡改留痕（tamper-evident）而非防越权（tamper-proof）。这作为设计取舍成立，但应在 authority.md 中显式声明，避免使用者高估防护强度。

## 问题登记册

| ID | 严重度 | 领域 | 问题 | 关键证据 |
|---|---|---|---|---|
| H1 | 高 | 契约 | schemas/ 为死契约且已被自家数据违反 | docs/truth-registry.json:4 含 updated_at，违反 truth-registry.schema.json:28；代码零引用 schemas |
| H2 | 高 | 文档/实现 | 恢复输出四分类承诺未实现 | SKILL.md:27-28 vs core.py:924-934 |
| M1 | 中 | 文档/实现 | 工作状态机漂移：ready/canceled/superseded 无实现，含死代码 | graph.md:53-60 vs core.py:449-460, 949-950 |
| M2 | 中 | 文档/实现 | 规则状态机漂移：verified 独立态与 deprecated 缺失，无 ADR | authority.md:55-58 vs core.py:649-655 |
| M3 | 中 | 文档 | CLI 约 24 个子命令未入任何权威文档；init 模板布局与 SKILL.md 指针不兼容 | cli.py:55-211 vs runbook；core.py:186-192 vs SKILL.md:54-58 |
| M4 | 中 | 代码 | 校验器未包装异常路径：损坏账本可致 validate 崩溃 | core.py:613, 401-404, 871-872 |
| M5 | 中 | 契约 | 代码校验为 schema 真子集，六处弱化加一处冗余死条款 | core.py:317-343, 372-383, 800-801, 814-818, 836-838；gates.schema.json:18 |
| M6 | 中 | 治理 | ADR 稀缺：general-pm 草案、状态机裁剪、schema 定位、权威顶层均无决策锚点 | docs/decisions/ 仅 D-0001 |
| L1 | 低 | 代码 | 追加时全链重演，累计 O(n²)，长周期扩展性天花板 | core.py:715-741 |
| L2 | 低 | 代码 | fcntl 限定 Unix，与 README 平台口径不符 | core.py:3 vs README.md:21-22 |
| L3 | 低 | 测试 | 租约时间语义、8 种事件、CLI 半数命令零覆盖；缺 schema 回归与 dogfood 自检 | tests/ 覆盖矩阵 |
| L4 | 低 | 代码 | quality 计数校验仅在 CLI 层；subject 语义不一致；init 无回滚 | cli.py:257-260 vs core.py:496；cli.py:326-340；core.py:178-225 |
| L5 | 低 | 契约 | openai.yaml 与 SKILL.md 描述双源维护；D-0001 版本号无出处 | agents/openai.yaml vs SKILL.md:3；truth-registry.json:42 |
| L6 | 低 | 信任模型 | actor 无认证（防篡改非防越权），未在规范中显式声明 | core.py 全部 loop 检查 vs manifest coordination_boundary |

## 改进路线图

按"修复成本低于漂移成本"排序，建议分三步走。第一步（本周可完成，纯低成本守护）：删除注册表中的 updated_at 或放宽 schema；为 schemas/ 定位做出决策（接入 jsonschema 校验，或降级为参考资料）并留 ADR；新增 schema 回归测试与 dogfood 自检测试；给 research/graph-engineering.md 补"非权威"横幅。第二步（下一迭代，修复承诺落差）：实现恢复输出四分类或修改 SKILL.md/runbook 口径；对 ready/canceled/superseded 与规则 verified/deprecated 做"实现补齐或规范声明 v0.1 子集"二选一并留 ADR；修复 validate 的未包装异常路径；把 quality 计数校验下沉到 core 层。第三步（结构性改进）：生成式 CLI 命令参考并入 runbook；统一 init 模板布局与 SKILL.md 指针；裁决 general-pm 草案并锚定权威栈顶层；为账本重演设计增量校验或快照机制以缓解 O(n²)；在 authority.md 中显式声明 tamper-evident 信任边界。

## 结论

VoyageSkill 的运行时内核设计克制而坚实：单向三层、零依赖、原子写、哈希链、重演强制不变量，是一份可以直接依赖的 v0.1 底座，自我托管的做法也验证了其可用性。它当前的问题几乎全部是"同一哲学执行不彻底"：用机器校验保证运行时状态的系统，却没有用同样的手段保证契约与文档陈述。修复路线清晰且低成本——先补守护（schema 回归、dogfood 自检、ADR），再修承诺落差（恢复四分类、状态机对齐），最后做结构统一（命令文档化、模板布局、增量校验）。按此路线执行，项目可以完全兑现"真源可验证、恢复可重放"的核心承诺。

## 局限性

本评审基于 2026-08-14 的工作区快照，行号随代码演进会失效。评审为静态分析加源码逐行复核，未运行动态负载或并发压测；flock 在多进程并发追加下的行为、O(n²) 重演的实际拐点未经实测。文档一致性核查覆盖了 docs/ 全部现存文件，但不排除存在未入库的外部约定。外部实践对照基于微信公众号公开文章的标题与摘要层面检索，用于方向性参照而非逐条论证。

## 参考资料

1. [多智能体系统的工程治理之道：Harness 四层架构解析（AI 认知馆，2026-03-16）](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgS0wJUuXmWDUZlCaSUzqlXXo7QsJE5Dg-71qXa8Fplpd9n05mxTRcWvMN_eB9sYx4NFTPdygt2xg-kaDdF1BKf_7J0PY3HfpDg4iW4IQUdnCorKiPqtjZBL0o8-_uAbz0nYMZFf4QA-zhewoft8ntqpn_WSuUj6bDLNv9Hfp7TauSdjaCtVnDIzyTcPlqG6moGXD2BpUjd_5EJ4FlvQvPC_HFcvUoAZZH7Q..&type=2&query=%E5%A4%9A%E6%99%BA%E8%83%BD%E4%BD%93%E5%8D%8F%E4%BD%9C%20%E5%B7%A5%E7%A8%8B%E6%B2%BB%E7%90%86)
2. [多智能体通信，难点不在"能发消息"，而在"哪些话值得被系统听见"（宇恒随想录，2026-08-02）](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgS0wJUuXmWDUZlCaSUzqlXXo7QsJE5Dg-71qXa8Fplpd9L6ummORhp2fkW5-BFcpyr5ouZH7N1WP8lD_ww_J2L3AldPkgEz4yzV4bRT4pTmP1Oj7NZKfmIJ99HUOHMfKzQ6ij4e0yxrz0IrEzTB3-SeP3KO_FLzSd6xcWtFeJcRXgVe0WC6Sbi7DA..&type=2&query=%E5%A4%9A%E6%99%BA%E8%83%BD%E4%BD%93%E5%8D%8F%E4%BD%9C%20%E5%B7%A5%E7%A8%8B%E6%B2%BB%E7%90%86)
3. [AI 编程进入"注意力经济"：多智能体协作中被忽视的隐性税（鹭岛io，2026-08-05）](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgS0wJUuXmWDUZlCaSUzqlXXo7QsJE5Dg-71qXa8Fplpd9YMyNovRwFQcsXwWQnEJ4rghqxR-cFQdUCCihvwKge5_CayXsgWvtpjw3KYBlsFTVX_QBLbLhMESXpKqp3-N5DTafulelOSf9S1WjG2LtmKcdx_1ZEus2FhHIDJieV3-aj9WD3v7_lv3a7Jo-E90DMRx8KOuOgwZYykfn7YYxvTF535pjGOOjYg..&type=2&query=%E5%A4%9A%E6%99%BA%E8%83%BD%E4%BD%93%E5%8D%8F%E4%BD%9C%20%E5%B7%A5%E7%A8%8B%E6%B2%BB%E7%90%86)
4. [企业级 Agent SKILL 最佳实践（三只灵猫，2026-03-26）](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgS0wJUuXmWDUZ8J7tJNJzjgA7QsJE5Dg-71qXa8Fplpd98oDF6x03Ty2sRpO6SrPo9ZkxBRr-itJ72r6Uzg9H_Fo_7iwMlJjU1x6ofweIjDdvKeI1sjg6CVAMp9UeEIdslx-ooNOV6BVWW14cc0NHAO1TjB_wK1ZKN1qhXHruAVs8trThiHZT3u9dL8PSw96wsZmRJA6XLjoVhfEzp17OV2nrUpg570WR_xsQXl1YksT5tENPLihNXIa_1LSgwyq3EY4lUEKeUCLR4sskra9De-SVFqINYKJpoIDYPmZt7P5IFqnWGDtDOlQeLKROJBjQH7pCxQ..&type=2&query=Agent%20Skills%20%E5%BC%80%E5%8F%91%20%E5%AE%9E%E8%B7%B5)
5. [Agent 开发实战指南：Skill 与 SubAgent 的选择之道（CMFans，2026-03-21）](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgS0wJUuXmWDUZ8J7tJNJzjgA7QsJE5Dg-71qXa8Fplpd9ui5Zrjf72PAdFZzScM2o8uV5n22Kcv9BvFlvXonTjtocFv8Nvu0QJABHBtYVWLOUO3UO8Pj_V4lD_ww_J2L3AldPkgEz4yzV4bRT4pTmP1Oj7NZKfmIJ99HUOHMfKzQ6ij4e0yxrz0IrEzTB3-SeP3KO_FLzSd6xcWtFeJcRXgVe0WC6Sbi7DA..&type=2&query=Agent%20Skills%20%E5%BC%80%E5%8F%91%20%E5%AE%9E%E8%B7%B5)
6. [JSON Schema 官方文档](https://json-schema.org/)
7. [Python fcntl — Unix 文件锁（仅 Unix 可用）](https://docs.python.org/3/library/fcntl.html)

注：第 1-5 条为搜狗微信搜索跳转链接，可能有时效性；微信文章内容仅作行业实践参照，本项目事实均以本地代码与文档为准。
