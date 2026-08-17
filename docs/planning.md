# VoyageSkill 开发计划与完整记录

> 文档性质：追加式 planning 真源
>
> 建立日期：2026-08-17
>
> 建立依据：User 明确要求“每次开发都更新此文档，不删除旧内容，只追加新内容”。

## 追加规则

1. 既有内容不得删除、覆盖、重排或静默修订。
2. 新计划、状态变化、纠错、延期、替代和验收结果一律追加新的日期记录。
3. 每次开发至少追加两条记录：开始前的计划记录，以及结束后的交付记录。
4. 后一条记录可以使用 `supersedes` 引用旧记录，但旧记录仍保留。
5. 状态只认提交、测试、命令输出、不可变制品和真实读回；会话摘要不能单独改变计划状态。
6. 每条开发记录至少包含：记录 ID、日期、基线、范围、非目标、风险、依赖、验收门禁、实际结果和锚点。
7. 未完成事项不得因开启新会话而自动变成完成；必须在新记录中明确继承、阻塞或替代。

---

## 2026-08-17 · PLAN-0001 · 最小内核收敛计划

### 记录状态

- Status: active
- Baseline: `cf9f465644154881738ffbb4bf08c9bf08f888d8`
- Branch: `xp/plan-minimal-kernel`
- Authority: User
- Supersedes: none
- Inputs:
  - `docs/design/voyage-skill-v0.1-proposal.md`
  - `docs/decisions/D-0001-v0.1-baseline.md`
  - `docs/research/graph-engineering-summary.md`
  - `research_report_voyage_skill_review.md`
  - 2026-08-17 User 提供的“最小内核”评审对话

### 当前判断

VoyageSkill v0.1 已经具备正确的安全骨架，但仍是“标准模式框架原型”，尚未完全兑现从最小内核渐进生长的产品原则。

已经成立、必须保留的内核包括：

- Skill 只作为发现和恢复入口；
- User 决策、项目真源和追加式账本相互分离；
- 执行、质量、治理、审计的权限边界；
- 不可变交付、独立质量、资源租约和门禁；
- 严格风险引用真实 User 决策；
- 哈希链、事件重放、跨会话校验和恢复。

下一阶段不增加新的节点类型或供应商适配。优先修复两类根问题：

1. 系统不能自动把未确认内容声明为真源；
2. 系统必须验证证据所声称的事实，而不只是验证字段非空。

### 总体开发原则

1. **先真实性，后丰富度**：先验证真源、锚点和证据，再扩展图查询和调度能力。
2. **先消除漂移，后新增状态**：正式文档、Schema、CLI 和状态机必须同版本一致。
3. **最小状态优先**：没有真实用例支撑的状态和节点先退出 active 合同，而不是为了文档完整而实现。
4. **核心不可压缩**：不可变锚点、独立质量、账本完整性和授权边界在所有风险模式下保留。
5. **扩展按需激活**：复杂审计、环境、通道、配额和图查询不在初始化时自动启用。
6. **每个里程碑独立可合流**：代码、测试、迁移、正式文档和 planning 记录在同一交付中闭环。

## 执行顺序总览

| 顺序 | Work ID | 优先级 | 目标 | 依赖 |
| --- | --- | --- | --- | --- |
| 0 | MK-000 | P0 | 建立契约守卫和关键设计决策 | PLAN-0001 |
| 1 | MK-101 | P0 | Bootstrap / draft / truth activate | MK-000 |
| 2 | MK-102 | P0 | 类型化锚点与证据验证 | MK-000、MK-101 |
| 3 | MK-103 | P0 | 状态机、文档、Schema 和 CLI 收敛 | MK-000、MK-102 |
| 4 | MK-104 | P0 | 恢复输出四类事实 | MK-102、MK-103 |
| 5 | MK-201 | P1 | 最小内核与可选扩展分层 | MK-101～MK-104 |
| 6 | MK-202 | P1 | 风险压缩变为可执行策略 | MK-201 |
| 7 | MK-301 | P2 | 派生运行图与一致性查询 | MK-104、MK-201 |
| 8 | MK-302 | P2 | 长账本性能、平台与信任模型收口 | MK-103、MK-301 |

## MK-000 · 契约守卫与设计决策

### 目的

在功能修改前先阻止新的“文档说一套、实现跑一套”。

### 范围

1. 新增决策记录，明确：
   - 真源激活权限；
   - v0.2 最小工作状态机；
   - v0.2 最小规则状态机；
   - JSON Schema 与 Python 校验器谁是规范来源；
   - actor 身份仅 tamper-evident、并非 tamper-proof 的信任边界。
2. 修复当前真源注册表与 `truth-registry.schema.json` 的冲突。
3. 为仓库根 `.voyage/` 增加 dogfood 自检测试。
4. 增加 Schema/实现一致性测试，禁止 Schema 继续成为死契约。
5. 让 `validate` 捕获损坏事件造成的 `KeyError`、`TypeError`、时间解析错误，统一输出结构化错误而非 traceback。
6. 将 quality 计数自洽校验下沉到 core，禁止绕过 CLI 写入假统计。

### 推荐决策

- Python core validator 作为运行时规范；
- JSON Schema 作为由同一模型生成或受一致性测试约束的交换契约；
- 不为了 Schema 引入与最小内核无关的常驻服务；
- 文档中的状态表由可执行定义生成或由测试逐项对照。

### 非目标

- 不增加新节点；
- 不重构整个事件分发器；
- 不做性能优化。

### 验收门禁

- 损坏账本只产生确定性错误报告；
- 仓库自身 `voyage validate` 进入自动测试；
- 所有正式 JSON 实例通过其声明的 Schema；
- 状态机和命令清单漂移能被测试发现；
- 原有安全不变量测试全部通过。

## MK-101 · Bootstrap、Draft 与真源激活

### 目的

消除 `voyage init` 自动制造“已生效真源”的治理缺口。

### 设计

```text
voyage init
→ bootstrap 项目
→ 生成 draft 合同
→ User 审阅产品目标、非目标和授权边界
→ 记录 User decision
→ voyage truth activate
→ 项目进入 operational
→ 才能授权首个工作项
```

### 范围

1. `manifest` 增加项目阶段：`bootstrap | operational`。
2. 新生成的 product、governance、system、operations 文档和注册项均为 `draft`。
3. 新增：
   - `voyage truth list`
   - `voyage truth status`
   - `voyage truth activate <source-id> --decision <user-decision-id>`
4. 激活必须验证：
   - 决策确由 User loop 记录；
   - 决策 scope 覆盖目标真源；
   - 文件存在并通过契约校验；
   - 同领域不存在另一个 active 真源，或存在明确 supersedes。
5. 只有 product、governance、system、operations 四个必需领域均 active，项目才进入 `operational`。
6. `work authorize` 在 bootstrap 阶段必须拒绝。
7. `--truth-registry` 采用已有真源时仍需验证激活证据，不因“文件已存在”自动信任。

### 兼容策略

- v0.1 项目读取时标记为 legacy bootstrap state；
- 已有 active 真源不自动失效，但首次写操作前要求生成一次迁移/确认决定；
- 迁移不得改写旧账本，使用追加事件记录。

### 验收门禁

- 全新 init 后不能授权工作；
- 无 User decision、scope 不匹配或合同校验失败时不能 activate；
- 四领域全部激活后才允许授权首个工作项；
- 冷启动能明确报告“bootstrap 未完成”的缺口与下一步；
- v0.1 dogfood 仓库可通过显式迁移恢复 operational。

## MK-102 · 类型化锚点与证据验证

### 目的

把“有人填写了字符串”提升为“系统能够验证这项事实”。

### 最小证据模型

所有锚点和证据使用带版本的对象，而不是无结构字符串：

```json
{
  "kind": "git-commit",
  "version": 1,
  "claim": "delivery-source",
  "locator": {"repository": ".", "revision": "<full-sha>"},
  "observed_at": "<RFC3339>",
  "producer": "<principal-id>"
}
```

第一批验证器：

| Kind | 必须验证的事实 |
| --- | --- |
| `git-commit` | 仓库存在、完整 SHA 对应 commit、对象可读取 |
| `artifact-digest` | 文件存在、路径不逃逸、算法允许、重新计算摘要一致 |
| `command-result` | argv、cwd、退出码、stdout/stderr 摘要、完整统计和时间齐全 |
| `runtime-readback` | 环境 ID、目标版本、观测时间、新鲜度、关键字段齐全且未过期 |
| `user-decision` | 决策事件存在、actor/loop 正确、scope 与动作匹配、未撤销 |

### 存储

- 证据正文使用内容寻址存入 `.voyage/evidence/sha256/<digest>.json`；
- 账本只保存稳定 evidence ID、摘要和声明；
- 验证结果追加记录验证器版本、时间和结果；
- 原始命令输出可作为制品保存，不能只保存过滤后的“pass”文本。

### 旧数据处理

- v0.1 字符串 anchor/evidence 可读取，但统一标记 `legacy-unverified`；
- legacy 证据不能满足 v0.2 新创建交付的强制门禁；
- 提供显式迁移/重新验证命令，不静默升级可信度。

### 验收门禁

- 不存在的 `commit:abc` 必须失败；
- 修改过的制品摘要必须失败；
- 过期 runtime readback 必须进入 unknown，而不是 pass；
- User 决策 scope 不覆盖动作时必须失败；
- 修复产生新锚点后，旧质量结论自动失效；
- 执行者仍不能签发自己的最终质量结论。

## MK-103 · 状态机、文档、Schema 与 CLI 收敛

### 目的

让 active 真源只承诺真实存在且可验证的机制。

### 最小状态决策

遵循最小内核原则，不优先实现没有真实用例的状态。

#### Work durable states

```text
draft → authorized → active → delivered
      → quality-passed → accepted → closed
```

保留实际已使用的 `rejected`、`blocked`、`awaiting-user`。`ready`、`canceled`、`superseded` 暂时退出 active v0.2 合同，等真实用例出现再通过决策加入。

#### Rule durable states

```text
proposed → approved → applied → active
active → retired | superseded
```

`rule.verified` 是使 `applied → active` 的证据事件，不再同时宣称一个独立 durable `verified` 状态。`deprecated` 暂不进入核心。补充最小安全失败路径：验证失败时规则保持非 active，并可由治理执行 rollback。

### 其他收敛项

1. 从 argparse 定义生成或校验 CLI 命令参考，纳入权威 runbook。
2. Skill 不再硬编码某一种项目文档布局；只通过 manifest 和 truth registry 发现领域真源。
3. init 模板、dogfood 项目和 Skill 的发现协议使用同一套领域名称。
4. 明确事件 subject 约定，资源事件同时提供 resource ID 与 lease ID，不依赖不一致的 subject 推断。
5. `agents/openai.yaml` 与 `SKILL.md` 元数据增加一致性校验。
6. 研究文档统一加“非权威、不可执行”标识。

### 验收门禁

- 文档状态表与 replay 可达状态完全一致；
- 不再存在 next_safe_action 的不可达分支；
- 所有 CLI 子命令均可从权威操作文档发现；
- 新 init 项目能通过同一个 Skill 发现协议冷启动；
- 生成/校验步骤在 CI 中可重复且无手工双写。

## MK-104 · 恢复输出四类事实

### 目的

兑现 Skill 和 runbook 已承诺的 `observed / declared / unknown / conflicting` 恢复语义。

### 输出合同

```json
{
  "observed": [],
  "declared": [],
  "unknown": [],
  "conflicts": []
}
```

每个恢复项至少包含：subject、claim、来源事件、证据 ID、证据种类、验证时间、新鲜度、当前结论、阻塞范围和下一安全动作。

### 分类规则

- **observed**：适配的类型化证据已经通过验证且仍在新鲜期；
- **declared**：主体作出声明，但缺少满足门禁的独立观测；
- **unknown**：无法探测、证据过期、legacy 未验证或必要信息缺失；
- **conflicts**：两个有效声明/观测在同一 scope 内互相矛盾。

### 验收门禁

- 声明“已释放”但端口仍被占用时进入 conflicts；
- 过期租约与未复探外部资源进入 unknown；
- legacy 字符串证据进入 declared 或 unknown，不能进入 observed；
- 相同账本与相同探测输入产生确定性相同的恢复结果；
- 恢复输出可直接给出下一安全动作与所需权限。

## MK-201 · 最小内核与可选扩展分层

### 永久内核

- 真源注册与 User 决策；
- 工作项与不可变交付；
- 类型化证据与独立质量；
- 已知资源与冲突控制；
- 追加式账本与恢复；
- 执行、质量、治理、审计权限边界；
- 最小规则变更安全链。

### 可选扩展

- advanced-audit：复杂阻塞、周期复盘和申诉工作流；
- channel-tracking：sent / acknowledged / started；
- environment-control：环境水位、部署与运行读回；
- quota-cost：额度、预算和付费授权；
- advanced-rules：复杂规则生命周期和自动到期；
- derived-graph：查询、路径和可视化。

### 实施约束

- init 只启用永久内核；
- 扩展必须显式 `enable`，记录决策、版本和新增门禁；
- 未启用扩展的项目不生成对应文件、状态和日常流程；
- 审计权限始终存在，但 advanced-audit 流程不强制所有低风险项目运行。

### 验收门禁

- 最小项目初始化产物和上下文体积显著减少；
- 未启用扩展不会影响核心工作闭环；
- 启用/停用扩展可恢复、可审计、不可静默放宽门禁；
- Skill 只在任务需要时加载扩展参考。

## MK-202 · 风险压缩的可执行策略

### 策略矩阵

| 控制项 | Light | Standard | Strict |
| --- | --- | --- | --- |
| 不可变锚点 | 必须 | 必须 | 必须 |
| 独立质量 | 必须 | 必须 | 必须 |
| 追加式账本 | 必须 | 必须 | 必须 |
| 额外门禁 | 核心最少集 | 项目定义 | 风险域完整集 |
| 审计运行 | 事件触发 | 周期或事件 | 强制检查点 |
| 真实环境读回 | 有环境变更时 | 有环境变更时 | 动作前后均必须 |
| User 授权 | 进入高风险时 | 进入高风险时 | 每个严格动作必须 |
| 资源探测 | 冲突资源 | 所有声明资源 | 动作前复探且保留读回 |

### 验收门禁

- 三种模式具有可观察的门禁差异；
- Light 不减少锚点、独立质量或账本完整性；
- Strict 缺 User decision 或新鲜读回时不能执行；
- 风险未知、证据缺失或分类争议自动升级；
- 每个策略差异都有正反用例。

## MK-301 · 派生运行图与一致性查询

### 目的

在不引入通用图数据库的前提下，让“运行图”成为可观察的派生视图，而不只是状态机隐喻。

### 范围

1. 从真源、账本、资源和证据派生节点与边；
2. 提供只读命令：
   - `voyage graph derive`
   - `voyage graph check`
   - `voyage graph path <from> <to>`
3. 检测孤立对象、悬空引用、失效锚点、无解除路径阻塞和循环依赖；
4. 输出稳定 JSON，后续可由外部工具可视化。

### 非目标

- 不建设图数据库；
- 不在核心中加入图形 UI；
- 不用图查询替代事件账本。

### 验收门禁

- 派生图可由相同输入重复生成；
- 当前工作项、资源、证据、门禁和阻塞路径均可追溯；
- 悬空内部依赖和孤立 active 对象会导致检查失败；
- 图视图不成为新的可写真源。

## MK-302 · 性能、平台与信任模型收口

### 范围

1. 建立账本长度基准，测量全链重演的实际拐点；
2. 只有达到量化阈值后才设计校验快照或增量索引；
3. 快照必须引用账本头哈希，可删除重建，不能成为第二真源；
4. 明确 `fcntl` 的 Unix 平台边界，决定是否提供 Windows 锁适配；
5. 在 authority 合同中声明 actor ID 无密码学认证：v0.x 提供防篡改留痕，不提供对恶意本机调用者的强防越权；
6. 统一资源事件 subject 和查询语义；
7. 为 init 建立失败回滚或可恢复 bootstrap 标记。

### 验收门禁

- 性能改动有基准数据，不凭假设引入复杂度；
- 删除派生快照后可从账本恢复相同状态；
- 支持平台与信任边界在 README、Skill 和治理合同中一致；
- 初始化中断可以安全重试或明确恢复。

## 每个开发包的统一交付门禁

每个 Work ID 合流前必须同时满足：

1. 范围、非目标和风险已在本文件追加开始记录；
2. 实现引用不可变 commit；
3. 单元、负向、迁移和端到端测试通过，完整报告 pass/fail/skip/unknown；
4. 独立质量验证针对同一 commit；
5. 仓库自身 `voyage validate` 和 `voyage recover` 通过；
6. 正式文档、Schema、CLI 帮助和状态机同提交更新；
7. 未引入未启用扩展或供应商绑定；
8. 在本文件末尾追加结束记录，列出实际结果、遗留问题、测试证据和 commit；
9. push 后读取远端水位，确认远端确实包含目标 commit。

## 下一立即动作

下一个开发包为 `MK-000`。其开始前必须在本文末尾追加 `DEV-0001 START` 记录；完成后追加 `DEV-0001 CLOSE`，不得修改本条 PLAN-0001。

---

## 后续追加模板

```text
## YYYY-MM-DD · DEV-NNNN · <Work ID> · START|UPDATE|CLOSE

- Status:
- Baseline:
- Anchor:
- Supersedes:
- Scope:
- Non-goals:
- Risk:
- Dependencies:
- Acceptance gates:
- Actual result:
- Tests (pass/fail/skip/unknown):
- Readback:
- Remaining issues:
- Next safe action:
```

---

## 2026-08-17 · DEV-0001 · MK-000 · START

- Status: in-progress
- Baseline: `e971047c99ceeded8d7bfadf47cd1427711bf5e0`
- Anchor: pending
- Supersedes: none
- Scope: 契约决策、Schema 守卫、dogfood 自检、损坏输入结构化错误、core 层质量计数校验
- Non-goals: bootstrap 激活流程、类型化证据、状态机收敛、恢复四分类、图查询
- Risk: standard；涉及验证器和正式契约，但不涉及外部系统或不可逆数据
- Dependencies: PLAN-0001、D-0001、当前 v0.1 账本兼容性
- Acceptance gates: 以下测试矩阵全部通过；全量回归无失败或跳过；Voyage validate/recover 通过；独立验证针对最终提交
- Actual result: pending
- Tests: defined before implementation, not run yet
- Readback: pending
- Remaining issues: pending
- Next safe action: 先添加测试并确认它们在当前实现上按预期失败

### DEV-0001 子任务与测试矩阵

#### ST-0001 · Schema 与正式实例一致性

实现前测试用例：

1. `schema_manifest_accepts_initialized_project`：init 产出的 manifest 通过 manifest schema。
2. `schema_graph_accepts_initialized_project`：init 产出的 graph 通过 graph schema，并包含四层 loop。
3. `schema_resources_accepts_initialized_project`：资源定义通过 resources schema。
4. `schema_gates_accepts_initialized_project`：门禁定义通过 gates schema。
5. `schema_events_accept_all_initialized_ledger_events`：账本每条事件通过 event schema。
6. `schema_truth_registry_accepts_dogfood_registry`：仓库 active truth registry 通过 schema。
7. `schema_rejects_unknown_top_level_property`：`additionalProperties: false` 生效。
8. `schema_rejects_missing_required_field`：缺少 required 字段时失败并给出 JSON path。
9. `schema_rejects_invalid_enum_pattern_and_const`：枚举、正则和 const 均被执行。
10. `schema_unique_and_contains_are_enforced`：graph 的 uniqueItems 和四 loop contains 被执行。

预期当前失败：dogfood registry 含 schema 未声明的 `updated_at`；运行时代码未执行正式 Schema。

#### ST-0002 · Dogfood 与契约防漂移

实现前测试用例：

1. `repository_root_is_a_valid_voyage_project`：对仓库根运行 `validate_project`，必须零错误。
2. `all_active_truth_sources_exist`：注册表中每个 active source 均存在。
3. `one_active_truth_source_per_domain`：同领域不能有两个 active source。
4. `schema_files_are_exercised_by_tests`：六份 schema 均至少校验一个有效实例和一个无效实例。
5. `skill_frontmatter_and_openai_metadata_agree`：名称与默认 prompt 引用保持一致。
6. `planning_is_registered_as_active_truth`：追加式 planning 文件可由 registry 发现。

预期当前失败：缺少仓库级 dogfood 测试与元数据一致性守卫。

#### ST-0003 · 损坏输入必须产生结构化错误

实现前测试用例：

1. `validate_reports_missing_lease_expiry`：重算哈希后的 resource.claimed 缺 `expires_at`，返回错误列表而非 traceback。
2. `validate_reports_invalid_lease_timestamp`：非法 RFC3339 时间在 validate/recover 中返回确定性错误。
3. `validate_reports_wrong_event_payload_shape`：payload 形状错误时不泄漏 `KeyError`/`TypeError`。
4. `validate_reports_wrong_truth_source_shape`：registry 中 source 非对象时返回带路径错误。
5. `validate_reports_bad_gate_definition`：gate 缺 required 字段时失败。
6. `validate_reports_bad_graph_definition`：graph 缺四层 loop 或存在重复类型时失败。
7. `cli_validate_never_prints_traceback_for_project_data_error`：CLI 返回非零与 JSON 错误，不输出 Python traceback。

预期当前失败：若事件通过基础哈希检查但破坏 replay 假设，`validate_project` 可能抛裸异常。

#### ST-0004 · Quality 计数必须由 core 强制

实现前测试用例：

1. `core_rejects_quality_counts_that_do_not_sum`：绕过 CLI 调用 append_event 也不能写入不自洽计数。
2. `core_rejects_negative_quality_counts`：任一负数失败。
3. `core_rejects_non_integer_quality_counts`：布尔、字符串或浮点失败。
4. `core_rejects_passing_quality_with_failed_unknown_or_skipped`：pass 不允许 failed/unknown/skip。
5. `core_accepts_complete_passing_quality_counts`：完整 3/3 通过。
6. `core_accepts_complete_rejection_counts`：reject 必须至少包含 failed 或 unknown，且总数自洽。
7. `failed_append_does_not_advance_ledger_head`：被拒绝事件不会写入账本。

预期当前失败：quality 统计只在 CLI 层严格校验，core 直接调用可以绕过。

#### ST-0005 · 决策与正式文档

实现前测试用例：

1. `decision_d0002_is_registered_and_active`：新契约决策进入 decisions 真源或由现有 decisions 域发现。
2. `authority_documents_tamper_evident_boundary`：正式治理合同明确 actor 无密码学认证。
3. `system_contract_names_runtime_contract_authority`：正式系统合同明确 Python validator 与 JSON Schema 的关系。
4. `planning_history_remains_append_only`：本次开发只在 planning 尾部追加 START/CLOSE，不修改 PLAN-0001。

预期当前失败：缺少 D-0002，信任边界与 Schema 权威关系未正式化。

### DEV-0001 测试执行顺序

1. 添加上述测试，不改实现；运行目标测试，保存预期失败证据。
2. 按 ST-0001 → ST-0005 顺序逐项实现；每完成一个子任务立即运行其目标测试。
3. 每个目标测试通过后运行此前全部目标测试，防止子任务间回归。
4. 全部实现完成后运行完整测试套件，报告 pass/fail/skip/unknown。
5. 运行仓库 dogfood `validate` 与 `recover`。
6. 对最终不可变提交执行独立前向验证。
7. 在本文末尾追加 `DEV-0001 CLOSE`，不得修改本 START 记录。

---

## 2026-08-17 · DEV-0001 · MK-000 · UPDATE

- Status: implementation-complete; awaiting immutable Git anchor
- Baseline: `e971047c99ceeded8d7bfadf47cd1427711bf5e0`
- Anchor: pending Git write permission
- Supersedes: none
- Scope: ST-0001 through ST-0005 implemented as defined in DEV-0001 START
- Non-goals: unchanged
- Risk: standard; no external or irreversible project action performed
- Dependencies: Git metadata write required to create immutable review anchor
- Acceptance gates: implementation gates passed; immutable-anchor and push gates pending
- Actual result: zero-dependency Schema subset added; dogfood drift guards added; malformed project data is structured; quality counts are core-enforced; D-0002 and formal trust/contract authority are active
- Tests: 53 pass, 0 fail, 0 skip; dogfood validate/recover pass; compileall pass; clean-project forward lifecycle pass; invalid quality counts rejected before ledger advance
- Readback: final forward project recovered as `closed` with next action `none`
- Remaining issues: official `quick_validate.py` is unknown because its environment lacks PyYAML and temporary dependency installation was denied by approval-service 403; equivalent YAML/frontmatter validation passed
- Next safe action: User creates the implementation commit in the development worktree, then development appends CLOSE against that immutable commit and reruns final gates

---

## 2026-08-17 · DEV-0001 · MK-000 · CLOSE

- Status: complete
- Baseline: `e971047c99ceeded8d7bfadf47cd1427711bf5e0`
- Anchor: `3fc28e01c9b257f5f972f06edacaf060b1fe0415`
- Supersedes: DEV-0001 UPDATE completion blocker
- Scope: ST-0001 through ST-0005 delivered without expanding into MK-101 or later work
- Non-goals: bootstrap activation, typed evidence, state-machine convergence, recovery four-way classification, extensions, and graph queries remain deferred to their planned work packages
- Risk: standard; no production, destructive, paid, credential, or external-write action performed
- Dependencies: D-0001, D-0002, Python 3.9+, project-local Voyage control files
- Acceptance gates: all MK-000 implementation gates passed against the immutable anchor
- Actual result: formal JSON instances are exercised against six Schemas; repository dogfood and metadata drift are guarded; malformed registry, graph, gate, event, lease, and timestamp inputs produce structured errors; quality counts cannot bypass core replay; runtime/Schema authority and actor trust boundaries are recorded
- Tests: 53 pass, 0 fail, 0 skip; dogfood validate/recover pass; compileall pass; clean-project forward lifecycle pass; invalid quality counts rejected without advancing the ledger
- Readback: local HEAD resolves to the anchor; recovery reports no blocks or leases; forward project on the same anchor recovered as `closed` with next action `none`
- Remaining issues: official `quick_validate.py` remains unknown because its external environment lacks PyYAML; equivalent frontmatter rules and repository metadata tests pass. This is a validator-environment issue, not an MK-000 product failure
- Next safe action: commit and push this append-only CLOSE record, verify the remote branch contains the implementation anchor, then begin MK-101 with a new START record and test matrix

---

## 2026-08-17 · DEV-0002 · MK-101 · START

- Status: in-progress
- Baseline: `58d6dffe64b3224038c785c901137d23f84f8a95`
- Anchor: pending
- Supersedes: none
- Scope: bootstrap stage、draft contracts、User-scoped truth activation、operational gate、legacy v0.1 migration、truth CLI and recovery gaps
- Non-goals: typed evidence objects、MK-103 state convergence、MK-104 four-way recovery classification、optional extensions、derived graph
- Risk: standard；改变新项目初始化和首个工作授权前置条件，但不执行生产或外部写入
- Dependencies: MK-000、D-0002、现有 append-only ledger 和 truth registry
- Acceptance gates: 以下测试全部先于实现定义并通过；原有回归适配新 bootstrap 语义后全部通过；dogfood 显式迁移；不可变提交与远端读回
- Actual result: pending
- Tests: defined below before implementation
- Readback: pending
- Remaining issues: pending
- Next safe action: 写入 ST-1011 至 ST-1016 测试并确认当前 v0.1 实现按预期失败

### DEV-0002 子任务与测试矩阵

#### ST-1011 · Bootstrap 初始化合同

实现前测试用例：

1. `new_manifest_starts_in_bootstrap`：新 manifest 声明 `project_stage=bootstrap` 且通过 Schema。
2. `generated_required_truth_starts_as_draft`：product、governance、system、operations 注册项和文件均为 draft。
3. `generated_contracts_expose_unresolved_review_fields`：模板显式保留目标、非目标、权限和运行边界待确认项，不可被误认成已确认事实。
4. `bootstrap_recovery_lists_required_domain_gaps`：recover 明确报告四个缺口和下一安全动作。
5. `bootstrap_rejects_work_authorization`：可创建工作，但未 operational 前不能 authorize。
6. `bootstrap_project_remains_structurally_valid`：draft 项目仍可 validate 和冷启动。

#### ST-1012 · User-scoped 真源激活

实现前测试用例：

1. `activation_rejects_unknown_decision`：未知 decision ID 不得激活。
2. `activation_rejects_non_user_decision`：非 User loop 不能产生可用激活决定。
3. `activation_rejects_scope_mismatch`：decision 未覆盖 `truth.activate`、项目或 source ID 时拒绝。
4. `activation_rejects_missing_contract_file`：文件不存在时拒绝且 registry/ledger 不前移。
5. `activation_rejects_unresolved_bootstrap_contract`：仍含 TODO 或缺必需章节时拒绝。
6. `activation_records_decision_and_exact_source`：成功事件引用 decision、source、domain、path，并将 registry/文档置为 active。
7. `failed_activation_is_atomic`：任何失败均不改 manifest、registry、文档和 ledger head。

#### ST-1013 · Operational 门禁与替代

实现前测试用例：

1. `partial_activation_remains_bootstrap`：少于四个必需领域时保持 bootstrap。
2. `four_verified_domains_become_operational`：四领域 active 且各有激活事件后才切换 operational。
3. `operational_stage_allows_work_authorization`：进入 operational 后可授权工作。
4. `duplicate_active_domain_requires_supersedes`：同领域已有 active 时必须显式 supersedes。
5. `supersedes_must_target_same_domain`：跨领域替代拒绝。
6. `successful_supersession_is_atomic_and_auditable`：旧源变 superseded，新源 active，事件引用两者与 User decision。
7. `activation_cannot_be_replayed_for_same_source`：同一 source 不可用重复事件伪造新确认。

#### ST-1014 · 采用已有真源

实现前测试用例：

1. `adopted_active_sources_do_not_auto_operationalize`：已有文件和 active 标签不构成激活证据。
2. `adopted_source_requires_user_scoped_activation`：已有 active source 仍必须逐项记录 User-scoped activation。
3. `adopted_all_required_domains_need_all_evidence`：四领域齐全但缺任一激活事件仍为 bootstrap。
4. `adopted_registry_is_not_rewritten_on_failed_activation`：失败不改用户提供的 registry。

#### ST-1015 · v0.1 兼容迁移

实现前测试用例：

1. `legacy_manifest_recovers_as_legacy_bootstrap`：缺 stage 的 v0.1 项目可读，但 recover 明确标记 legacy 和迁移动作。
2. `legacy_first_write_requires_confirmation`：除记录 User decision 外的首次写操作在迁移前拒绝。
3. `legacy_migration_rejects_missing_or_mismatched_decision`：未知、错误 action 或错误 project scope 均拒绝。
4. `legacy_migration_requires_four_existing_active_domains`：缺正式领域时不能迁移 operational。
5. `legacy_migration_appends_without_rewriting_history`：旧账本字节前缀保持不变，只追加迁移事件。
6. `legacy_migration_sets_operational_and_unblocks_writes`：成功后 manifest operational，recover 清除迁移缺口并允许授权。
7. `already_staged_project_cannot_use_legacy_migration`：新 bootstrap 项目不能绕过逐项激活。

#### ST-1016 · CLI、正式文档与 dogfood

实现前测试用例：

1. `cli_truth_list_and_status_are_structured`：list/status 输出 source 状态、证据、缺口和下一动作。
2. `cli_truth_activate_requires_decision`：CLI 缺 decision 或 scope 错误时稳定非零且无 traceback。
3. `cli_bootstrap_to_operational_end_to_end`：编辑四份合同、记录决定、激活、授权工作完整通过。
4. `cli_truth_migrate_handles_legacy_project`：显式迁移命令只接受匹配的 User 决定。
5. `skill_and_runbook_document_bootstrap_protocol`：Skill 保持精简入口，详细激活/迁移命令由 runbook 承载。
6. `dogfood_repository_is_explicitly_operational`：仓库自身通过追加决定和迁移事件进入 operational。
7. `manifest_and_registry_schemas_accept_bootstrap_and_legacy`：Schema 接受新字段并保留 v0.1 读取兼容，不把 legacy 静默视为 operational。

### DEV-0002 测试执行顺序

1. 新增上述测试与测试辅助代码，不修改产品实现；运行并保存预期失败。
2. 按 ST-1011 → ST-1016 顺序实现；每完成一项立即运行目标测试和此前累计测试。
3. 实现完成后适配原有测试，使其显式选择 bootstrap 或完成激活，不提供隐藏后门。
4. 运行全量 unittest、dogfood validate/recover、compileall、Skill 校验和干净临时项目前向验证。
5. 对不可变提交重复质量验证；在文件末尾追加 DEV-0002 CLOSE，不修改历史记录。

---

## 2026-08-17 · DEV-0002 · MK-101 · UPDATE

- Status: in-progress; pre-commit hardening
- Baseline: `58d6dffe64b3224038c785c901137d23f84f8a95`
- Anchor: pending
- Supersedes: none
- Scope: add ST-1017 runtime anti-bypass checks discovered during full-regression review
- Non-goals: unchanged
- Risk: standard; prevents direct core API and manifest edits from manufacturing operational truth
- Dependencies: ST-1011 through ST-1016 passing 91/91 full regression
- Acceptance gates: four tests below fail before implementation, pass after implementation, then 95-test full regression passes
- Actual result: pending
- Tests: defined before implementation below
- Readback: dogfood migration already operational through decision and migration events
- Remaining issues: runtime/registry drift checks not yet centralized
- Next safe action: add ST-1017 tests, confirm red, implement one candidate-state consistency validator

### ST-1017 · 运行时一致性与 direct API 防绕过

实现前测试用例：

1. `validate_reports_manifest_stage_drift`：仅手改 manifest 为 operational 不能改变 ledger 派生阶段，validate 报冲突。
2. `direct_activation_cannot_target_draft_registry`：直接 append `truth.activated` 不能绕过 draft registry 状态。
3. `direct_activation_must_match_registry_identity`：事件中的 source/domain/path 必须与 registry 精确一致。
4. `operational_registry_requires_verified_current_sources`：operational 项目的每个当前 active 必需领域源都必须有匹配激活证据。

---

## 2026-08-17 · DEV-0002 · MK-101 · UPDATE

- Status: in-progress; optional truth readback hardening
- Baseline: `58d6dffe64b3224038c785c901137d23f84f8a95`
- Anchor: pending
- Supersedes: none
- Scope: ST-1018 closes active-but-unverified optional truth ambiguity found by dogfood readback
- Non-goals: optional domains do not become required operational domains
- Risk: standard; only adds scoped activation evidence and preserves the four-domain operational gate
- Dependencies: ST-1017 passing; dogfood operational migration event present
- Acceptance gates: tests below fail first, then pass; dogfood status has no unverified active source
- Actual result: pending
- Tests: defined before implementation below
- Readback: planning and decisions currently appear in `unverified_active_sources`
- Remaining issues: optional domain activation is currently rejected by core
- Next safe action: add two tests, allow non-empty optional domains, append scoped dogfood activation evidence

### ST-1018 · Optional active truth evidence

实现前测试用例：

1. `optional_truth_source_can_be_activated_without_changing_required_gate`：optional source 可按同一 User-scoped 流程激活，但不能替代四个必需领域。
2. `dogfood_has_no_unverified_active_truth`：仓库所有 active truth source 均有 ledger 激活或迁移证据。

---

## 2026-08-17 · DEV-0002 · MK-101 · UPDATE

- Status: in-progress; adopted registry identity hardening
- Baseline: `58d6dffe64b3224038c785c901137d23f84f8a95`
- Anchor: pending
- Supersedes: none
- Scope: ST-1019 binds an adopted truth registry to the initialized project before control files are written
- Non-goals: no remote registry or signature verification
- Risk: standard; rejects ambiguous adoption earlier
- Dependencies: ST-1018 passing; adopted registry support
- Acceptance gates: mismatch test fails first, then passes without partial `.voyage` initialization; full regression remains green
- Actual result: pending
- Tests: defined before implementation below
- Readback: current initializer accepts a registry whose `project` differs from `--project-id`
- Remaining issues: pending test and fix
- Next safe action: add mismatch/atomicity test, enforce project identity before initialization writes

### ST-1019 · Adopted registry project identity

实现前测试用例：

1. `adopted_registry_project_must_match_manifest_without_partial_init`：registry `project` 与 `--project-id` 不同必须拒绝，且不留下 `.voyage/manifest.json`。

---

## 2026-08-17 · DEV-0002 · MK-101 · UPDATE

- Status: implementation-complete; immutable-anchor verification pending
- Baseline: `58d6dffe64b3224038c785c901137d23f84f8a95`
- Anchor: pending
- Supersedes: none
- Scope: ST-1011 through ST-1019 complete; bootstrap drafts, scoped truth activation, explicit supersession, legacy migration, operational authorization gate, runtime anti-bypass validation, optional truth evidence, and adopted-registry identity checks implemented
- Non-goals: no typed delivery evidence, state-machine reconciliation beyond MK-101, recovery four-bucket redesign, or extension-layer work
- Risk: standard; bootstrap truth can no longer become authoritative without recorded User scope and real ledger readback
- Dependencies: MK-000 and D-0002 complete; all MK-101 test-first records above satisfied
- Acceptance gates: 98-test full regression, compileall, dogfood validate/truth status/recover, adopted-project forward CLI scenario, append-only planning check, and diff hygiene
- Actual result: implementation complete; 98 passed, 0 failed, 0 skipped; compileall passed; dogfood is operational with six verified active truth sources; dogfood validate and recover passed; adopted-project bootstrap-to-operational-to-authorized forward scenario passed; `git diff --check` passed
- Tests: ST-1011 through ST-1019 were defined and observed failing before their corresponding implementation; cumulative and full suites pass after implementation
- Readback: dogfood ledger head is `evt-469b9c218d594ab0bd21c75dde697ca3`; migration and optional truth activations are append-only ledger evidence
- Remaining issues: official `quick_validate.py` remains unknown because its external environment lacks PyYAML and dependency-install approval returned 403; equivalent Ruby YAML/frontmatter validation passed
- Next safe action: commit the MK-101 implementation, rerun the complete acceptance set against that immutable commit, append DEV-0002 CLOSE with the commit anchor, then commit and push the close record before starting MK-102

---

## 2026-08-17 · DEV-0002 · MK-101 · CLOSE

- Status: complete
- Baseline: `58d6dffe64b3224038c785c901137d23f84f8a95`
- Anchor: `b1256896c941e2e8f67f77c06d8fe234b5739cdf`
- Supersedes: none
- Scope: bootstrap truth activation and legacy migration safety boundary delivered as specified by ST-1011 through ST-1019
- Non-goals: unchanged; typed evidence is MK-102, state-machine reconciliation is MK-103, recovery four-bucket output is MK-104, and extension layering is MK-105
- Risk: standard; accepted after independent readback from the immutable implementation anchor
- Dependencies: MK-000 complete; D-0002 active; implementation anchor exists locally
- Acceptance gates: complete full regression, compilation, dogfood validation/status/recovery, append-only planning enforcement, adopted-project forward scenario, and immutable diff hygiene
- Actual result: PASS; immutable anchor rerun produced 98 passed, 0 failed, 0 skipped; compileall passed with cache rooted under `/tmp`; `voyage validate` returned no errors; `truth status` reported operational with no missing domains or unverified active sources; `recover` reported the same ledger head and operational stage; `git diff HEAD^ HEAD --check` passed
- Tests: all ST-1011 through ST-1019 cases and all pre-existing regression tests passed against the exact anchor above
- Readback: implementation commit contains 14 changed files, including the new bootstrap test suite and support helpers; dogfood ledger head remains `evt-469b9c218d594ab0bd21c75dde697ca3`
- Remaining issues: official `quick_validate.py` is still unknown because its external environment lacks PyYAML and approval infrastructure returned 403; equivalent repository metadata/frontmatter validation passed before the anchor and no related files changed afterward
- Next safe action: commit this append-only CLOSE record, push `xp/plan-minimal-kernel`, verify the remote branch contains both the implementation anchor and close commit, then start MK-102 with a new START record and failing typed-evidence tests

---

## 2026-08-17 · DEV-0003 · MK-102 · START

- Status: in-progress; test design complete, implementation not started
- Baseline: `73b460d45d5554c127016c2022db6814e7a01d54`
- Anchor: pending
- Supersedes: none
- Scope: versioned typed evidence, content-addressed storage, five minimum validators, append-only verification records, CLI read/write/readback, and typed enforcement for delivery, independent quality, and gate results
- Non-goals: no MK-103 lifecycle reconciliation, MK-104 four-bucket recovery redesign, remote artifact download, signature/PKI, arbitrary plugin validators, background freshness monitor, or extension-layer decomposition
- Risk: standard; changes the trust boundary for newly recorded delivery evidence while preserving legacy ledger readability
- Dependencies: MK-000 and MK-101 complete; content-addressed evidence directory already registered by the manifest
- Acceptance gates: all tests below must be written before implementation and observed failing; each validator subtask must pass its target tests plus cumulative evidence tests; final full regression, compileall, dogfood validation/recovery, CLI forward scenario, schema coverage, and diff hygiene must pass
- Actual result: pending
- Tests: ST-1021 through ST-1028 defined below
- Readback: local and remote branch both resolve to `73b460d45d5554c127016c2022db6814e7a01d54`; worktree was clean at START
- Remaining issues: evidence objects, validators, verification events, and typed gate enforcement do not yet exist
- Next safe action: add all MK-102 tests without product changes, run them to capture the expected red baseline, then implement ST-1021 first

### DEV-0003 固定接口与兼容边界

1. Evidence ID 使用 `sha256:<64-hex>`，正文以 canonical JSON 存放在 `.voyage/evidence/sha256/<digest>.json`。
2. 证据正文统一包含 `kind`、`version`、`claim`、`locator`、`observed_at`、`producer`；kind-specific 数据放在 `locator`，不得依赖会话记忆补全。
3. 验证结果为 `valid`、`invalid` 或 `unknown`，每次显式记录/复验追加 `evidence.verified` 事件，包含验证器版本、验证时间、状态和原因。
4. `work.delivered` 的 anchor 必须是有效 `git-commit` 或 `artifact-digest`；delivery、quality 和 gate 的 evidence 必须是当前有效的类型化 evidence ID；quality/gate 继续严格绑定同一 anchor。
5. 已存在 ledger 的自由字符串保持可重放并标记为 legacy；从 DEV-0003 起新追加的 delivery、quality 和 gate 不得用 legacy 字符串满足门禁。
6. `runtime-readback` 过期返回 `unknown`；unknown 与 invalid 均不能满足强制门禁。
7. Evidence 文件属于声明，验证器必须在消费时重新读回真实 Git 对象、文件摘要、原始命令输出、时间或 User 决定，不能只信历史验证事件。

### ST-1021 · 内容寻址存储与通用合同

实现前测试用例：

1. `evidence_is_stored_by_canonical_sha256_and_deduplicated`：相同正文产生同一 ID 和单一文件。
2. `tampered_evidence_document_is_rejected_by_digest_readback`：内容与路径摘要不一致时复验为 invalid。
3. `evidence_requires_versioned_common_fields`：缺 kind/version/claim/locator/observed_at/producer 或错误类型必须拒绝。
4. `evidence_verification_appends_versioned_ledger_record`：显式记录产生含 validator version、时间、状态、原因的追加事件。

### ST-1022 · Git commit validator

实现前测试用例：

1. `git_commit_accepts_existing_full_commit_sha`：项目内真实仓库的完整 commit SHA 可读并验证为 valid。
2. `git_commit_rejects_short_or_missing_revision`：短 SHA 和不存在的完整 SHA 均为 invalid。
3. `git_commit_rejects_repository_escape_or_non_repository`：仓库定位不得逃逸项目根，且目标必须是 Git repository。
4. `new_delivery_rejects_legacy_or_nonexistent_commit_anchor`：`commit:abc` 和不存在的 typed Git anchor 都不能交付。

### ST-1023 · Artifact digest validator

实现前测试用例：

1. `artifact_digest_recomputes_sha256`：现存项目文件的允许算法和真实摘要为 valid。
2. `artifact_digest_detects_changed_artifact`：存证后文件修改使复验 invalid，不能继续满足门禁。
3. `artifact_digest_rejects_escape_directory_and_unsupported_algorithm`：路径逃逸、目录目标和非 sha256 算法拒绝。

### ST-1024 · Command result validator

实现前测试用例：

1. `command_result_requires_argv_cwd_exit_code_counts_and_time`：命令、目录、退出码、完整统计、观测时间缺一不可。
2. `command_result_verifies_raw_stdout_and_stderr_artifacts`：stdout/stderr 必须指向项目内原始制品并匹配 bytes 与 sha256。
3. `command_result_rejects_inconsistent_counts_or_passing_claim`：分类总和错误，或 passing claim 含 failed/skipped/unknown 时 invalid。
4. `command_result_detects_raw_output_tampering`：原始输出改变后复验 invalid。

### ST-1025 · Runtime readback validator

实现前测试用例：

1. `runtime_readback_accepts_fresh_complete_observation`：环境 ID、目标版本、关键字段、观测时间和新鲜期完整时 valid。
2. `runtime_readback_expires_to_unknown`：超过 max_age_seconds 后必须为 unknown，不得继续作为 pass。
3. `runtime_readback_rejects_missing_identity_future_time_or_empty_fields`：身份/版本/字段缺失或未来时间为 invalid。

### ST-1026 · User decision validator

实现前测试用例：

1. `user_decision_evidence_validates_exact_action_project_and_source_scope`：真实 User-loop 决定覆盖精确范围时 valid。
2. `user_decision_evidence_rejects_missing_non_user_or_scope_mismatch`：不存在、非 User loop或 action/project/source 不匹配时 invalid。
3. `revoked_user_decision_evidence_becomes_invalid`：追加 User 撤销后，历史证据实时复验为 invalid。

### ST-1027 · 强制门禁集成与 legacy 兼容

实现前测试用例：

1. `typed_delivery_quality_and_gate_complete_lifecycle`：有效 anchor 与独立 command evidence 完成 delivery、quality、gate、accept 和 close。
2. `quality_and_gate_revalidate_evidence_at_consumption_time`：证据制品在 delivery 后被篡改，quality/gate 必须拒绝。
3. `repair_anchor_invalidates_old_quality_conclusion`：新交付 anchor 使旧 anchor 的质量结论不能用于 acceptance。
4. `executor_still_cannot_sign_final_quality_with_typed_evidence`：类型化证据不改变执行/质量分离。
5. `legacy_ledger_replays_but_legacy_refs_cannot_satisfy_new_events`：现有自由字符串账本仍 validate，新事件门禁拒绝 legacy refs。

### ST-1028 · CLI、Schema、文档与 dogfood

实现前测试用例：

1. `cli_evidence_record_show_and_verify_are_structured`：CLI 可从 JSON 文件记录、按 ID 读取并实时复验，输出稳定字段。
2. `evidence_schema_accepts_all_five_kinds_and_rejects_bad_common_contract`：正式 schema 覆盖五类对象和通用必填字段。
3. `event_schema_accepts_evidence_verification_events`：新增验证事件保持 ledger schema 可验证。
4. `skill_and_runbook_document_typed_evidence_protocol`：Skill 只提示验证入口，runbook 承载记录、复验、legacy 与 freshness 细节。
5. `dogfood_repository_remains_valid_with_legacy_history`：仓库自身旧 ledger 不被静默升级，但 validate/recover 继续通过。

---

## 2026-08-17 · DEV-0003 · MK-102 · UPDATE

- Status: in-progress; red baseline captured
- Baseline: `73b460d45d5554c127016c2022db6814e7a01d54`
- Anchor: pending
- Supersedes: none
- Scope: all ST-1021 through ST-1028 tests added before product implementation
- Non-goals: unchanged
- Risk: standard
- Dependencies: DEV-0003 START test matrix
- Acceptance gates: MK-102 module must fail for missing typed-evidence behavior before implementation
- Actual result: expected FAIL; 31 tests ran, 2 existing compatibility readbacks passed, remaining cases failed or errored because evidence APIs, validators, schema, CLI, docs, revocation, and typed gate enforcement are absent; legacy `commit:abc` was still accepted
- Tests: `PYTHONPATH=src python3 -B -m unittest tests.test_evidence -v`
- Readback: failures directly expose the planned gaps rather than unrelated fixture or import failures; temporary Git fixtures initialized successfully
- Remaining issues: all ST-1021 through ST-1028 implementation work remains
- Next safe action: implement ST-1021 common contract, canonical store, digest readback, and append-only verification event; run EvidenceStorageTests before proceeding

---

## 2026-08-17 · DEV-0003 · MK-102 · UPDATE

- Status: in-progress; ST-1021 through ST-1028 green, cold-start hardening required
- Baseline: `73b460d45d5554c127016c2022db6814e7a01d54`
- Anchor: pending
- Supersedes: none
- Scope: add ST-1029 so project validation re-reads content-addressed evidence and facts already consumed by typed transitions
- Non-goals: no recovery four-bucket presentation or background monitoring
- Risk: standard; without this check, a later evidence/artifact mutation can evade cold-start validation even though live append paths revalidate
- Dependencies: ST-1021 through ST-1028 target tests pass; 31/31 MK-102 tests pass; 26/26 adapted legacy core/quality/CLI tests pass
- Acceptance gates: tests below fail before implementation, then pass with full MK-102 and repository regression
- Actual result: pending
- Tests: defined below before implementation
- Readback: current `validate_project` checks ledger hashes and state transitions but does not resolve typed evidence IDs after replay
- Remaining issues: cold-start integrity and consumed-evidence readback gap
- Next safe action: add ST-1029 tests, capture red, then add deterministic validation without treating unused invalid/unknown evidence claims as project corruption

### ST-1029 · 冷启动证据完整性与消费事实读回

实现前测试用例：

1. `validate_detects_tampered_content_addressed_document`：任何 verification event 指向的正文摘要不匹配时项目 invalid。
2. `validate_rechecks_evidence_consumed_by_historical_transition`：交付/质量/gate 已消费的制品或原始输出改变后，冷启动 validate 报 invalid/unknown。
3. `validate_allows_recorded_invalid_or_unknown_evidence_when_unused`：仅记录但未用于强制 transition 的 invalid/unknown claim 不污染项目状态。
4. `validate_detects_missing_document_for_verification_event`：验证事件引用的 evidence 正文丢失时项目 invalid。

---

## 2026-08-17 · DEV-0003 · MK-102 · UPDATE

- Status: in-progress; ST-1029 green, acceptance boundary hardening required
- Baseline: `73b460d45d5554c127016c2022db6814e7a01d54`
- Anchor: pending
- Supersedes: none
- Scope: ST-1030 revalidates the current delivery and mandatory gate evidence at accept and close
- Non-goals: no historical verdict deletion and no global block on repair transitions
- Risk: standard; cached pass state must not outlive the evidence it claims to prove
- Dependencies: ST-1029 passes 4/4
- Acceptance gates: tests below fail before implementation, then pass without preventing rejected work from creating a new delivery anchor
- Actual result: pending
- Tests: defined below before implementation
- Readback: quality/gate state currently stores anchor and counts but not evidence IDs, so accept cannot re-read their facts
- Remaining issues: acceptance and closure can currently rely on a stale cached verdict
- Next safe action: add ST-1030 tests, capture red, retain evidence refs in derived state, and revalidate only the current acceptance path

### ST-1030 · Accept/close 当前证据复验

实现前测试用例：

1. `acceptance_revalidates_current_delivery_and_gate_evidence`：quality pass 后证据制品改变，accept 必须拒绝。
2. `closure_revalidates_accepted_delivery_and_gate_evidence`：accept 后、close 前证据改变，close 必须拒绝。
3. `stale_historical_evidence_does_not_block_repair_with_new_anchor`：rejected attempt 的旧证据失效不能阻止 start/new delivery，只有当前 acceptance path 受约束。

---

## 2026-08-17 · DEV-0003 · MK-102 · UPDATE

- Status: in-progress; final authorization consistency hardening
- Baseline: `73b460d45d5554c127016c2022db6814e7a01d54`
- Anchor: pending
- Supersedes: none
- Scope: ST-1031 makes decision revocation effective at every existing authorization consumer, not only the new user-decision validator
- Non-goals: no generalized decision lifecycle beyond recorded/revoked
- Risk: standard; a revoked decision must not retain authority through a legacy direct-reference path
- Dependencies: ST-1030 passes 3/3; full repository regression passes 136/136 before ST-1031
- Acceptance gates: tests below fail before implementation, then pass with all 136 prior tests
- Actual result: pending
- Tests: defined below before implementation
- Readback: `_require_decision_scope` and strict work/resource/resume checks currently test membership only and ignore the new revoked flag
- Remaining issues: authorization consumers disagree with typed user-decision verification after revocation
- Next safe action: add ST-1031 tests, capture red, centralize active-decision checks, rerun full regression

### ST-1031 · 撤销决定的全路径一致性

实现前测试用例：

1. `revoked_decision_cannot_authorize_strict_work`：strict work 不得引用已撤销 User 决定。
2. `revoked_scoped_decision_cannot_activate_truth`：truth activate 的 action/project/source 全覆盖也不能绕过撤销。
3. `revoked_decision_cannot_resume_or_claim_strict_resource`：resume 和 strict resource 消费点同样拒绝撤销决定。

---

## 2026-08-17 · DEV-0003 · MK-102 · UPDATE

- Status: implementation-complete; immutable-anchor verification pending
- Baseline: `73b460d45d5554c127016c2022db6814e7a01d54`
- Anchor: pending
- Supersedes: none
- Scope: ST-1021 through ST-1031 complete; content-addressed typed evidence, five live validators, verification events, CLI/schema/docs, mandatory transition enforcement, cold-start integrity, accept/close revalidation, legacy read compatibility, and decision-revocation consistency implemented
- Non-goals: MK-103 lifecycle/schema convergence beyond evidence contracts, MK-104 four-bucket recovery presentation, signatures, remote evidence, validator plugins, and background freshness monitoring remain deferred
- Risk: standard; newly appended delivery, quality, and gate transitions now require real typed facts while existing free-form ledger history remains readable but untrusted
- Dependencies: MK-000 and MK-101 complete; all DEV-0003 test-first records satisfied
- Acceptance gates: 139-test full regression, compileall, dogfood validate/recover, evidence CLI forward read/write/readback, schema coverage, append-only planning enforcement, and diff hygiene
- Actual result: PASS before commit; 139 passed, 0 failed, 0 skipped; compileall passed with cache under `/tmp`; dogfood validate returned no errors and recover remained operational at ledger head `evt-469b9c218d594ab0bd21c75dde697ca3`; `git diff --check` passed
- Tests: all ST-1021 through ST-1031 cases were defined before their fixes; initial MK-102 run captured 31-test red baseline; ST-1029, ST-1030, and ST-1031 each captured independent red before green; legacy core/quality/CLI fixtures were migrated to real typed evidence without a product bypass
- Readback: only negative tests and planning text retain `commit:abc`; Git validator requires exact repository root and full readable SHA; artifact/command facts are recomputed; expired runtime is unknown; User scope and revocation are live-read; accept/close revalidate the current path
- Remaining issues: official `quick_validate.py` remains unknown because its external environment lacks PyYAML and approval infrastructure previously returned 403; equivalent repository schema/frontmatter tests pass
- Next safe action: commit the MK-102 implementation, rerun all 139 tests and dogfood gates against the immutable commit, append DEV-0003 CLOSE with its SHA, then commit and push the close record before MK-103
