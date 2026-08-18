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

---

## 2026-08-17 · DEV-0003 · MK-102 · CLOSE

- Status: complete
- Baseline: `73b460d45d5554c127016c2022db6814e7a01d54`
- Anchor: `59997f57a3a7d8a3f5f9ef5aaa3fe1154c88d185`
- Supersedes: none
- Scope: typed anchors and evidence validation delivered through ST-1021 through ST-1031
- Non-goals: unchanged; MK-103 state/schema convergence, MK-104 recovery classification, extensions, signatures, remote evidence, and plugin validators remain deferred
- Risk: standard; accepted only after immutable-anchor readback
- Dependencies: MK-000 and MK-101 complete; implementation anchor exists locally
- Acceptance gates: full regression, compilation, dogfood validation/truth/recovery, schema and append-only contract tests, evidence CLI behavior, exact commit diff hygiene, and legacy-read compatibility
- Actual result: PASS; immutable anchor rerun produced 139 passed, 0 failed, 0 skipped; compileall passed; dogfood validate returned no errors; truth status remained operational with six verified active sources; recover reported the same operational stage and ledger head; `git diff HEAD^ HEAD --check` passed
- Tests: every DEV-0003 subtask captured tests before implementation; ST-1021 through ST-1031 and all prior tests pass against the exact anchor above
- Readback: anchor contains 12 changed files, including the formal evidence schema and 530-line typed-evidence suite; no working-tree changes existed before this CLOSE append
- Remaining issues: official `quick_validate.py` remains unknown due its external missing PyYAML/403 approval environment; repository-owned equivalent metadata, schema, and frontmatter checks pass
- Next safe action: commit this append-only CLOSE record, push `xp/plan-minimal-kernel`, verify remote head, then begin MK-103 with a new test-first START record

---

## 2026-08-18 · DEV-0004 · MK-103 · START

- Status: in-progress; test design complete, implementation not started
- Baseline: `bc68706b3167c393588d07f4fc9cdcf0c3449955`
- Anchor: pending
- Supersedes: none
- Scope: converge work/rule lifecycle claims, add rule failure/rollback, generate and check authoritative CLI reference, remove Skill layout assumptions, align truth domains, normalize resource-event subjects, constrain event exchange schema, and label all research inputs non-authoritative/non-executable
- Non-goals: no new speculative work state, no generalized rule revision graph, no MK-104 recovery classification, no plugin/profile architecture, no remote schema registry, and no cryptographic actor authentication
- Risk: standard; this change removes unsupported promises and adds only the minimum rule failure path already required by active governance truth
- Dependencies: MK-000 through MK-102 complete; D-0002 active
- Acceptance gates: every test below is added before product changes and observed failing; each subtask passes its own tests plus cumulative convergence tests; final full regression, compileall, dogfood validate/truth/recover, CLI-reference checker, schema coverage, research-marker check, and diff hygiene pass
- Actual result: pending
- Tests: ST-1032 through ST-1038 defined below
- Readback: local and remote branch both resolve to `bc68706b3167c393588d07f4fc9cdcf0c3449955`; worktree was clean at START
- Remaining issues: active graph/governance/runbook/Skill claims currently drift from runtime and argparse
- Next safe action: add the complete MK-103 convergence suite without product edits, capture the red baseline, then implement ST-1032 first

### DEV-0004 固定收敛决策

1. Work durable states are exactly `draft`, `authorized`, `active`, `delivered`, `quality-passed`, `accepted`, `closed`; side states are exactly `rejected`, `blocked`, `awaiting-user`.
2. Work `ready`, `canceled`, and work `superseded` are absent from active v0.2 truth and next-action tables; truth-source/rule supersession remains valid in its own domain.
3. Rule durable states are exactly `proposed`, `approved`, `applied`, `active`, `retired`, `superseded`; `rule.verified` transitions applied directly to active.
4. `rule.verification-failed` leaves the durable state at applied and records failed verification metadata; `rule.rolled-back` requires that failure, governance authority, and evidence, then returns the rule to approved for revision/reapply.
5. Resource lease events use resource ID as event subject and include both `resource_id` and `lease_id` in payload; registration remains resource-only.
6. Authoritative CLI reference is derived deterministically from argparse leaf commands and checked between stable markers in the active runbook.
7. Skill discovers active domain truth only through manifest and registry; repository-specific truth paths stay in the registry, not the stable Skill entry.

### ST-1032 · Work 状态与 next action 收敛

实现前测试用例：

1. `work_state_contract_matches_exact_runtime_sets`：runtime 暴露的 durable/side 集合与 D-0002 完全一致。
2. `system_graph_documents_only_reachable_work_states`：active graph 的 lifecycle/side states 与 runtime 集合一致，不含 ready/canceled/work superseded。
3. `next_safe_action_covers_only_reachable_work_states`：next-action 表无不可达键，所有可达状态均有非 fallback 动作。
4. `blocked_and_awaiting_user_restore_exact_previous_state`：两类暂停状态解除后恢复真实 previous state，不制造 ready 等中间态。

### ST-1033 · Rule 失败验证与 rollback

实现前测试用例：

1. `rule_state_contract_matches_exact_runtime_sets`：durable rule 状态只包含 proposed/approved/applied/active/retired/superseded。
2. `failed_rule_verification_remains_applied_and_records_failure`：独立 verifier 可失败规则，状态仍为 applied 且记录失败事件/actor。
3. `rule_rollback_requires_failure_governance_and_evidence`：未失败、错误 loop 或无 evidence 均不能 rollback。
4. `successful_rule_rollback_returns_to_approved_and_can_reapply`：rollback 后可治理修订/重新 apply/独立 verify 到 active。
5. `rule_cli_exposes_verify_fail_and_rollback`：CLI 两条命令映射精确事件与权限。
6. `governance_and_graph_document_only_real_rule_states_and_failure_path`：verified 是事件不是 durable state，deprecated 退出核心合同。

### ST-1034 · Argparse 派生 CLI 参考

实现前测试用例：

1. `cli_reference_contains_every_leaf_command_exactly_once`：runbook 标记区覆盖 argparse 全部叶命令且无幽灵命令。
2. `cli_reference_render_is_deterministic`：相同 parser 多次渲染字节一致。
3. `cli_reference_check_detects_drift`：检查器对当前 runbook pass，对删改命令的副本 fail。
4. `cli_reference_script_supports_check_and_print`：仓库脚本可供 CI 重复检查并打印生成内容。

### ST-1035 · Skill 发现协议与领域一致性

实现前测试用例：

1. `skill_has_no_repository_specific_truth_paths`：Skill 不包含 `docs/product/...` 等固定布局，只要求 manifest/registry/domain 发现。
2. `skill_names_the_same_required_domains_as_runtime`：Skill、init registry、dogfood registry 与 runtime 的四个必需领域一致。
3. `custom_registry_paths_are_discoverable_without_skill_change`：采用任意项目内路径的 registry 后，truth status/Skill 协议仍可发现。
4. `metadata_and_skill_identity_remain_consistent`：name、display name、default prompt 和 skill invocation 一致。

### ST-1036 · Resource event subject 合同

实现前测试用例：

1. `claim_release_and_recover_use_resource_subject_with_both_ids`：三类 lease 事件 subject 均为 resource ID，payload 同时含 resource/lease ID。
2. `resource_event_rejects_subject_or_payload_identity_mismatch`：subject、resource_id、lease 实际绑定不一致时拒绝。
3. `resource_cli_resolves_resource_id_for_release_and_recovery`：仅输入 lease ID 的 CLI 会从真实状态解析 resource ID 后写事件。
4. `event_data_validation_reports_legacy_ambiguous_resource_identity`：冷启动校验明确报告不一致而非依赖 subject 猜测。

### ST-1037 · Runtime、Schema 与 CLI exchange 收敛

实现前测试用例：

1. `event_schema_enum_matches_runtime_supported_events`：event schema type enum 与 runtime 支持事件集合完全一致。
2. `all_runtime_event_types_have_replay_coverage`：每个声明事件都有 replay 分支或明确通用观察分支。
3. `all_cli_transition_events_are_in_runtime_and_schema`：CLI 产生的事件不超出 runtime/schema 合同。
4. `new_rule_and_resource_events_validate_against_event_schema`：新增事件实例通过正式 schema，坏 type 被拒绝。

### ST-1038 · Research 输入隔离与 dogfood

实现前测试用例：

1. `every_research_document_has_standard_non_authoritative_marker`：`docs/research/*` 每份文档都有统一 research-input 标识。
2. `research_marker_explicitly_forbids_execution_and_truth_use`：标识同时写明 non-authoritative 与 non-executable。
3. `dogfood_registry_keeps_research_non_authoritative`：registry 明确排除 research 目录。
4. `dogfood_validate_recover_and_schema_coverage_remain_green`：收敛后仓库自身仍可冷启动且全部 schema 有测试实例。

---

## 2026-08-18 · DEV-0004 · MK-103 · UPDATE

- Status: in-progress; red baseline captured
- Baseline: `bc68706b3167c393588d07f4fc9cdcf0c3449955`
- Anchor: pending
- Supersedes: none
- Scope: all ST-1032 through ST-1038 tests added before product implementation
- Non-goals: unchanged
- Risk: standard
- Dependencies: DEV-0004 START matrix
- Acceptance gates: convergence suite must fail for the documented drift before implementation
- Actual result: expected FAIL; 30 tests ran and exposed missing runtime state/event constants, unsupported rule failure/rollback, absent CLI reference module/script/markers, unconstrained event type schema, ambiguous resource release identity, hardcoded Skill truth paths, stale active lifecycle text, and missing research isolation markers; existing custom-registry/domain and dogfood compatibility checks passed
- Tests: `PYTHONPATH=src python3 -B -m unittest tests.test_convergence -v`
- Readback: failures map to the planned MK-103 gaps; one test-only lease-event count was corrected from three to four because the scenario intentionally creates two claims
- Remaining issues: all ST-1032 through ST-1038 implementation work remains
- Next safe action: implement ST-1032 runtime work-state constants, exact next-action map, and graph markers; run WorkStateConvergenceTests before proceeding

---

## 2026-08-18 · DEV-0004 · MK-103 · UPDATE

- Status: implementation complete; immutable anchor pending
- Baseline: `bc68706b3167c393588d07f4fc9cdcf0c3449955`
- Anchor: pending
- Supersedes: none
- Scope: ST-1032 through ST-1038 implemented; runtime, active truth, argparse reference, event schema, resource identity, Skill discovery, and research isolation now share one tested contract
- Non-goals: unchanged; MK-104 recovery classification, optional extensions, signatures, remote evidence, and plugin validators remain deferred
- Risk: standard; unsupported state promises were removed, required rule failure/rollback behavior was added, and all event producers now converge on the runtime/schema exchange contract
- Dependencies: MK-000 through MK-102 complete; DEV-0004 START decisions and red baseline satisfied
- Acceptance gates: 169-test full regression, compileall, dogfood validate/truth/recover, deterministic CLI-reference checker, exact runtime/schema/CLI event coverage, research-marker isolation, append-only planning enforcement, and diff hygiene
- Actual result: PASS before commit; 169 passed, 0 failed, 0 skipped; compileall passed with cache under `/tmp`; dogfood validate returned no errors, truth status remained operational with six activation-verified active sources, recover remained operational at ledger head `evt-469b9c218d594ab0bd21c75dde697ca3`, CLI reference was current, and `git diff --check` passed
- Tests: all 30 convergence tests pass after their recorded failing baseline; every ST-1032 through ST-1038 behavior is covered, and all 139 prior tests remain green
- Readback: work durable/side states and rule durable states exactly match the fixed decisions; rule verification failure and rollback are executable; release/recover resolve the real resource subject; schema event enum equals runtime events; argparse generates the runbook reference; Skill discovery uses manifest and registry domains; all four research inputs retain their original content with only the non-authoritative/non-executable header added
- Remaining issues: official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; repository-owned equivalent frontmatter, metadata, identity, schema, and invocation tests pass
- Next safe action: commit the MK-103 implementation, rerun all 169 tests and acceptance gates against the immutable commit, append DEV-0004 CLOSE with its SHA, then commit and push the close record before MK-104

---

## 2026-08-18 · DEV-0004 · MK-103 · CLOSE

- Status: complete
- Baseline: `bc68706b3167c393588d07f4fc9cdcf0c3449955`
- Anchor: `bf77f1066b74ae5c86892af34b02927fd528ba6e`
- Supersedes: none
- Scope: ST-1032 through ST-1038 delivered; runtime and active truth state contracts converge, rule failure/rollback is executable, CLI reference is argparse-derived, Skill discovery is registry-based, resource event identities are unambiguous, event exchange is schema-constrained, and research inputs are isolated
- Non-goals: unchanged; MK-104 recovery classification, optional extensions, signatures, remote evidence, and plugin validators remain deferred
- Risk: standard; accepted only after immutable-anchor readback
- Dependencies: MK-000 through MK-102 complete; DEV-0004 test-first START, red baseline, and implementation-complete UPDATE satisfied
- Acceptance gates: full regression, compilation, dogfood validation/truth/recovery, deterministic CLI-reference checker, exact runtime/schema/CLI event coverage, schema and append-only contract tests, research isolation, clean implementation anchor, and exact commit diff hygiene
- Actual result: PASS; immutable anchor rerun produced 169 passed, 0 failed, 0 skipped; compileall passed; dogfood validate returned no errors; truth status remained operational with six activation-verified active sources; recover reported the same operational stage and ledger head; CLI reference was current; `git diff HEAD^ HEAD --check` passed
- Tests: all 30 ST-1032 through ST-1038 convergence tests and all 139 prior tests pass against the exact anchor above
- Readback: anchor contains 15 changed files with 883 insertions and 41 deletions, including the deterministic reference script/module and 388-line convergence suite; the worktree was clean before this CLOSE append
- Remaining issues: official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; repository-owned equivalent frontmatter, metadata, identity, schema, invocation, and dogfood checks pass
- Next safe action: commit this append-only CLOSE record, push `xp/plan-minimal-kernel`, verify the remote head, then begin MK-104 with a new test-first START record

---

## 2026-08-18 · DEV-0005 · MK-104 · START

- Status: in-progress; test design complete, implementation not started
- Baseline: `3ee37c582fd987a743925f3ff3df7947ae44e569`
- Anchor: pending
- Supersedes: none
- Scope: derive deterministic `observed`, `declared`, `unknown`, and `conflicts` recovery facts from the validated ledger, typed evidence readback, lease freshness, registered resource probes, and current replay state
- Non-goals: no new durable event types, no background monitor, no arbitrary probe/plugin execution, no remote evidence retrieval, no probabilistic conflict inference, no MK-201 extension layering, and no derived graph engine
- Risk: standard; recovery is a read-only derived view, but false observation or over-broad conflict classification could incorrectly authorize or block work
- Dependencies: MK-102 typed evidence and MK-103 converged event/resource contracts complete; local and remote branch both resolve to the baseline above
- Acceptance gates: every ST-1041 through ST-1045 test below is added before product implementation and observed failing for the documented gap; each subtask passes its own tests plus cumulative recovery tests; final full regression, compileall, dogfood validate/truth/recover, CLI reference, append-only planning enforcement, deterministic readback, and diff hygiene pass
- Actual result: pending
- Tests: ST-1041 through ST-1045 defined below
- Readback: MK-103 CLOSE is the only change in baseline commit; worktree was clean at START; current recover output has no four-bucket fact contract
- Remaining issues: current recovery mixes replayed declarations with volatile state, does not reverify evidence into fact buckets, and cannot surface contradictions or item-scoped permissions/actions
- Next safe action: add the complete MK-104 recovery suite without product edits, capture the red baseline, then implement ST-1041 first

### DEV-0005 固定恢复决策

1. Recovery remains a derived, read-only view; it never appends verification or probe events and never mutates project state.
2. The top-level fact buckets are exactly `observed`, `declared`, `unknown`, and `conflicts`; existing bootstrap/work/lease/block/rule fields remain for backward-compatible operational context.
3. Every fact item includes `subject`, `claim`, `source_event`, `evidence_id`, `evidence_kind`, `verified_at`, `freshness`, `conclusion`, `blocking_scope`, `next_safe_action`, and `required_loop`; unavailable fields are explicit `null`, never omitted.
4. A typed evidence reference is observed only when live verification is valid. Expired runtime readback, missing/tampered evidence, unverified legacy evidence, expired leases, and stateful resources without a fresh adapted probe are unknown.
5. A replayed current-state claim without qualifying independent observation is declared. One fact appears in only one primary bucket unless a conflict replaces its otherwise observed/declared representation.
6. Conflicts require deterministic contradiction in the same scope: mutually different valid runtime observations for the same environment/version/field, or a released port whose registered readback still reports occupied. Do not infer conflict from absence alone.
7. Recovery accepts an injectable verification time and port-probe function internally so identical ledger, evidence, time, and probe inputs produce byte-equivalent fact buckets. CLI uses real UTC time and the real port probe.
8. Ordering is deterministic by bucket, subject, claim, source event, and evidence ID. Conflict and unknown items block only their named scope and provide the minimum safe next action and required loop.

### ST-1041 · 四类输出与事实项合同

实现前测试用例：

1. `recovery_exposes_exact_fact_buckets_and_complete_item_contract`：四个 bucket 均存在，事实项包含全部固定字段且 null 显式保留。
2. `recovery_preserves_existing_operational_context`：bootstrap、work、active leases、blocks、rules、ledger head 等 v0.2 字段保持兼容。
3. `recovery_fact_order_and_fixed_time_are_deterministic`：固定 now/probe 对相同输入连续运行得到完全相同 bucket 和 `validated_at`。
4. `recovery_is_read_only_and_does_not_append_events`：恢复前后 ledger 字节与 head 不变。

### ST-1042 · 类型化证据与 legacy 分类

实现前测试用例：

1. `valid_typed_evidence_is_observed_with_live_verification_metadata`：有效 typed evidence 进入 observed，并报告 kind、验证时间、fresh freshness 和 source event。
2. `expired_runtime_readback_is_unknown_not_observed`：过期 runtime readback 只进入 unknown，结论与下一动作要求重新读回。
3. `missing_or_tampered_typed_evidence_is_unknown`：缺失或内容寻址不一致的引用进入 unknown，不使 recovery 崩溃或误报 observed。
4. `legacy_string_evidence_is_never_observed`：legacy 字符串证据只能 declared/unknown，并给出迁移到 typed evidence 的动作。

### ST-1043 · 租约、资源探测与冲突

实现前测试用例：

1. `expired_active_lease_is_unknown_with_minimal_scope`：过期 active lease 进入 unknown，blocking scope 仅为对应 resource/lease。
2. `unprobed_stateful_resource_is_unknown`：未适配实时探测的 stateful resource 即使租约未过期也进入 unknown。
3. `released_port_still_occupied_is_conflict`：账本声明 released 但同一注册端口读回 occupied 时进入 conflicts，要求 governance reconcile。
4. `released_port_readback_free_is_observed_without_conflict`：released 与端口 free 一致时形成 observed release，不进入 conflicts。
5. `probe_failure_is_unknown_not_conflict`：探测异常或不可得进入 unknown，不伪造冲突。

### ST-1044 · 同 scope 有效观测冲突与去重

实现前测试用例：

1. `contradictory_valid_runtime_fields_in_same_scope_conflict`：同 environment/version/field 的两个新鲜有效读回值不同，生成一个确定性 conflict。
2. `different_runtime_scopes_do_not_conflict`：环境或版本不同的观测分别进入 observed。
3. `identical_runtime_observations_are_deduplicated_without_conflict`：同 scope 同值读回不冲突并稳定去重。
4. `conflicted_observations_do_not_remain_in_observed_bucket`：参与冲突的事实仅出现在 conflicts，避免双重结论。

### ST-1045 · CLI、文档与 dogfood 收敛

实现前测试用例：

1. `recover_cli_emits_four_bucket_json_and_is_repeatable_with_fixed_fixture`：CLI JSON 暴露四 bucket，且不依赖会话记忆补全字段。
2. `skill_runbook_and_graph_define_same_recovery_contract`：Skill、active runbook、system graph 与 runtime bucket/字段/分类规则一致。
3. `dogfood_recovery_classifies_without_mutation`：仓库自身 recover 成功、四类输出合法、ledger 不变。
4. `recovery_unknown_and_conflict_actions_name_required_permission`：每个 unknown/conflict 都给出非空最小动作与 required loop。

---

## 2026-08-18 · DEV-0005 · MK-104 · UPDATE

- Status: in-progress; red baseline captured
- Baseline: `3ee37c582fd987a743925f3ff3df7947ae44e569`
- Anchor: pending
- Supersedes: none
- Scope: all 21 ST-1041 through ST-1045 tests added before product implementation
- Non-goals: unchanged
- Risk: standard
- Dependencies: DEV-0005 START matrix and fixed recovery decisions
- Acceptance gates: recovery suite must expose the missing four-bucket contract, evidence classification, resource readback, conflict detection, deterministic inputs, and active-document markers before implementation
- Actual result: expected FAIL; 21 tests ran, with 5 assertion failures, 14 bucket-missing errors, and 2 existing compatibility/read-only checks passing
- Tests: `PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/voyage-skill-pycache python3 -B -m unittest tests.test_recovery -v`
- Readback: failures are limited to absent `observed`/`declared`/`unknown`/`conflicts`, absent recovery constants and injectable inputs, missing typed/legacy/resource classification, missing contradiction handling, and missing Skill/runbook/graph markers; fixtures and existing recovery context are valid
- Remaining issues: all ST-1041 through ST-1045 implementation work remains
- Next safe action: implement the ST-1041 fact item constructor, deterministic ordering, injectable time/probe contract, and backward-compatible snapshot buckets; run RecoveryContractTests before ST-1042

---

## 2026-08-18 · DEV-0005 · MK-104 · UPDATE

- Status: implementation complete; immutable anchor pending
- Baseline: `3ee37c582fd987a743925f3ff3df7947ae44e569`
- Anchor: pending
- Supersedes: none
- Scope: ST-1041 through ST-1045 implemented; recovery now emits deterministic observed/declared/unknown/conflicts facts while preserving the existing operational context
- Non-goals: unchanged; no new event type, background monitor, arbitrary probe plugin, remote evidence, MK-201 extension layering, or derived graph engine was added
- Risk: standard; classification is read-only and conflicts block only the exact resource or runtime field scope
- Dependencies: MK-102 typed evidence, MK-103 converged contracts, DEV-0005 START decisions, and recorded red baseline satisfied
- Acceptance gates: 191-test full regression, 22-test recovery suite, compileall, dogfood validate/truth/recover, deterministic fixed-time/probe readback, CLI JSON and reference checks, append-only planning enforcement, active-document contract markers, ledger non-mutation, and diff hygiene
- Actual result: PASS before commit; 191 passed, 0 failed, 0 skipped; all 22 recovery tests passed; compileall passed with cache under `/tmp`; dogfood validate returned no errors, truth remained operational with six activation-verified active sources, recover emitted all four buckets at the unchanged ledger head, CLI reference was current, and `git diff --check` passed
- Tests: the original 21 recovery cases captured 5 failures, 14 errors, and 2 existing passes before implementation; a supplementary current-work declaration test was then added and observed failing before its state-view implementation; ST-1041 through ST-1045 were each run independently before the cumulative and full suites
- Readback: live-valid typed evidence is observed; expired/missing/tampered evidence and unprobed stateful or expired lease facts are unknown; legacy and current replay state are declared; same-scope runtime field disagreements and released-but-occupied ports are conflicts; conflicting observations are removed from observed; every fact has the fixed 11-field contract, scoped action, and required loop
- Remaining issues: official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; repository-owned frontmatter, metadata, identity, schema, invocation, dogfood, and recovery contract checks pass
- Next safe action: commit the MK-104 implementation, rerun all 191 tests and acceptance gates against the immutable commit, append DEV-0005 CLOSE with its SHA, then commit and push the close record before MK-201

---

## 2026-08-18 · DEV-0005 · MK-104 · CLOSE

- Status: complete
- Baseline: `3ee37c582fd987a743925f3ff3df7947ae44e569`
- Anchor: `6f08ebf0d68ca8ac10ff8ee18a31842d5ad82178`
- Supersedes: none
- Scope: ST-1041 through ST-1045 delivered; recover now separates observed, declared, unknown, and conflicts with deterministic evidence readback, resource probing, scoped actions, and explicit required loops
- Non-goals: unchanged; no new event type, monitor, arbitrary probe plugin, remote evidence, extension layering, or derived graph engine was introduced
- Risk: standard; accepted only after immutable-anchor readback
- Dependencies: MK-102 and MK-103 complete; DEV-0005 test-first START, red baseline, supplementary red test, and implementation-complete UPDATE satisfied
- Acceptance gates: full regression, focused recovery suite, compilation, dogfood validation/truth/recovery, deterministic fixed-input readback, CLI/reference/document convergence, append-only planning, ledger non-mutation, clean implementation anchor, and exact commit diff hygiene
- Actual result: PASS; immutable anchor rerun produced 191 passed, 0 failed, 0 skipped; focused recovery rerun produced 22 passed; compileall passed; dogfood validate returned no errors; truth remained operational with six activation-verified active sources; recover emitted all four buckets at the unchanged ledger head; CLI reference was current; `git diff HEAD^ HEAD --check` passed
- Tests: all ST-1041 through ST-1045 cases and all 169 prior tests pass against the exact anchor above
- Readback: anchor contains 6 changed files with 926 insertions and 13 deletions, including the 377-line recovery suite; the worktree was clean before this CLOSE append
- Remaining issues: official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; repository-owned frontmatter, metadata, identity, schema, invocation, dogfood, and recovery checks pass
- Next safe action: commit this append-only CLOSE record, push `xp/plan-minimal-kernel`, verify the remote head, then begin MK-201 with a new test-first START record

---

## 2026-08-18 · DEV-0006 · MK-201 · START

- Status: in-progress; test design complete, implementation not started
- Baseline: `7cd0a041883b523da4e71d6d80701b36d22cadab`
- Anchor: pending
- Supersedes: none
- Scope: separate the permanent kernel from optional extension contracts, minimize new-project graph declarations, add explicit decision-bound extension enable/disable state, gate extension event writes, preserve legacy replay, and expose deterministic CLI/recovery status
- Non-goals: no advanced audit scheduler or appeal engine, no delivery/deployment automation, no quota billing, no automatic rule expiry, no derived graph queries, no extension plugin loader, and no remote catalog
- Risk: standard; an incorrect split could silently remove a core guard or allow extension behavior without authorization
- Dependencies: MK-101 through MK-104 complete; local and remote branch both resolve to the baseline above
- Acceptance gates: every ST-2011 through ST-2016 test below is added before product implementation and observed failing for the documented gap; each subtask passes its own tests plus cumulative extension tests; final full regression, compileall, dogfood validate/truth/recover, CLI reference, schema coverage, append-only planning, legacy compatibility, and diff hygiene pass
- Actual result: pending
- Tests: ST-2011 through ST-2016 defined below
- Readback: current init declares 17 node types and 19 edge types including optional channel/environment semantics; runtime accepts extension events without an enable decision; no extension lifecycle or recovery status exists
- Remaining issues: active docs describe all mechanisms as one layer and Skill has no conditional extension-loading protocol
- Next safe action: add the complete MK-201 suite without product edits, capture the red baseline, then implement ST-2011 first

### DEV-0006 固定分层决策

1. The permanent kernel remains: truth/User decisions, work and immutable delivery, typed evidence and independent quality, known resources and leases, append-only ledger and recovery, four loop boundaries, blocks, mandatory gates, and the minimal propose/approve/apply/verify/retire rule chain.
2. New init graph types are exact runtime contract constants and exclude optional `channel` and `environment` nodes plus `acknowledged-by` and `readback-of` edges. Audit loop authority, resource type `environment`, and runtime-readback evidence remain core capabilities; only advanced workflows are optional.
3. Extension state lives in append-only `extension.enabled`/`extension.disabled` events. Init creates no extension-specific file and no enabled extension state.
4. The catalog has six stable IDs: `advanced-audit`, `channel-tracking`, `environment-control`, `quota-cost`, `advanced-rules`, and `derived-graph`. The first three are available because their existing events are implemented; the last three are `reserved` and cannot be enabled until their own milestones deliver behavior.
5. Enable and disable require governance authority plus an existing non-revoked User decision scoped to the exact project, action (`extension.enable` or `extension.disable`), extension ID, and catalog version. The event records the immutable catalog contract including added event/node/edge/gate sets.
6. In explicit-extension projects, `audit.finding`, `channel.sent`/`acknowledged`/`started`, and `environment.readback` require their mapped extension to be enabled at that ledger point. Core work/resource/rule/audit-block operations remain available without extensions.
7. Projects initialized before explicit-extension mode replay legacy extension events without inventing enable history. New extension lifecycle events opt that project into explicit mode; new init starts explicit immediately.
8. Disable never rewrites or deletes past facts, requires User approval, records the disabled version, and prevents later extension events. Recovery reports enabled and disabled history with next safe actions.
9. No extension may remove or weaken a core mandatory gate. Catalog gate additions are additive; MK-201 available extensions add no mandatory global gate because their scope-specific gate semantics are not yet implemented.
10. Skill reads the active system extension contract only for extension-related tasks and never loads reserved extension implementation as if it existed.

### ST-2011 · 最小永久内核 init

实现前测试用例：

1. `new_init_graph_matches_exact_kernel_contract`：node/edge/loop 集合精确等于 runtime kernel constants，不含 channel/environment 扩展类型。
2. `new_init_creates_no_extension_specific_files_or_enabled_state`：init 不创建 extension 目录/配置文件，replay 的 extensions 为空。
3. `kernel_init_still_supports_complete_core_work_lifecycle`：无扩展项目仍可完成授权、资源、交付、独立质量、接受与关闭。
4. `kernel_contract_keeps_audit_authority_and_environment_resources`：audit loop 与 environment 资源类型仍属于永久内核，不被错误移除。

### ST-2012 · 扩展目录与显式 enable

实现前测试用例：

1. `extension_catalog_has_six_stable_versioned_entries`：六个 ID、版本、availability、event/node/edge/gate 集合确定且可序列化。
2. `available_extension_enable_requires_exact_user_scope`：缺 decision、非 User、被撤销、错误 project/action/extension/version 均拒绝。
3. `extension_enable_records_catalog_contract_and_state`：成功 enable 事件携带精确 catalog snapshot，state 标记 enabled/version/decision/event。
4. `reserved_or_unknown_extension_cannot_enable`：reserved 和未知 ID 明确拒绝，不制造半状态。
5. `duplicate_or_version_mismatched_enable_is_rejected`：重复 enable 和非 catalog version 均拒绝。

### ST-2013 · disable、审计与门禁不可静默放宽

实现前测试用例：

1. `extension_disable_requires_exact_user_scope_and_enabled_version`：disable 使用独立 action decision，且必须匹配当前 enabled version。
2. `extension_disable_preserves_history_and_marks_disabled`：历史 enable 不删除，state/recovery 保留 enabled/disabled event 和 decisions。
3. `disable_without_decision_or_with_active_mismatch_is_atomic`：失败 disable 不追加事件、不改变 head。
4. `extension_contract_cannot_remove_core_gate`：catalog additions 与 effective contract 只能叠加，`independent-quality` 永远存在且 mandatory。

### ST-2014 · 扩展事件写门禁与 legacy replay

实现前测试用例：

1. `explicit_project_rejects_extension_events_before_enable`：三组扩展事件在未启用时分别拒绝。
2. `enabled_extension_allows_only_its_mapped_events`：启用 channel 不会放开 environment/audit，启用对应扩展后才允许。
3. `disabled_extension_rejects_later_events`：disable 后未来同类事件拒绝，既有事件仍可 replay/recover。
4. `core_events_and_minimal_audit_block_work_without_extensions`：work、resource、minimal rule、work.blocked 不依赖扩展。
5. `legacy_project_replays_pre_layer_extension_events`：无 explicit marker 的旧 project/ledger 可读取旧 channel/environment/audit 事件。

### ST-2015 · CLI、恢复与 schema 收敛

实现前测试用例：

1. `extension_cli_lists_catalog_and_current_status`：`extension list/status` 输出稳定 JSON、availability 和 effective core contract。
2. `extension_cli_enable_disable_round_trip`：CLI 使用 decision 完成 enable/disable，恢复输出一致。
3. `recovery_reports_extension_history_and_next_safe_action`：recover 显式报告 enabled/disabled/reserved，不将 reserved 伪装为 active。
4. `extension_events_match_runtime_schema_and_replay`：新事件进入 runtime/schema/CLI exchange 精确集合并有 replay 覆盖。
5. `cli_reference_includes_all_extension_leaf_commands`：argparse 派生 runbook 覆盖 list/status/enable/disable。

### ST-2016 · Active 文档、Skill 与 dogfood

实现前测试用例：

1. `system_graph_documents_exact_kernel_and_catalog_contract`：active system truth 的 marker 与 runtime constants/catalog 一致。
2. `skill_loads_extension_contract_only_for_extension_tasks`：Skill 明确先看 status，仅在相关任务加载 active system extension section，不硬编码扩展文件路径。
3. `runbook_documents_decision_bound_enable_disable_and_legacy_behavior`：operations truth 描述 exact decision scope、reserved 拒绝和 legacy replay 边界。
4. `dogfood_project_remains_valid_and_reports_legacy_extension_mode`：仓库自身作为已存在项目保持 valid/recoverable，明确 legacy-compatible 而非伪造 enable history。
5. `minimal_init_artifact_contract_is_smaller_than_v01_baseline`：新 graph node/edge 总数低于 17/19，且无扩展文件。

---

## 2026-08-18 · DEV-0006 · MK-201 · UPDATE

- Status: in-progress; red baseline captured
- Baseline: `7cd0a041883b523da4e71d6d80701b36d22cadab`
- Anchor: pending
- Supersedes: none
- Scope: all 28 ST-2011 through ST-2016 tests added before product implementation
- Non-goals: unchanged
- Risk: standard
- Dependencies: DEV-0006 START matrix and fixed layering decisions
- Acceptance gates: extension suite must expose oversized init, missing catalog/lifecycle/status, absent decision scope, unguarded extension events, missing CLI/schema/recovery integration, and absent active-document markers before implementation
- Actual result: expected FAIL; 28 tests ran, with 7 assertion failures and 24 errors including subtests; the existing core lifecycle and minimal audit-block/rule behavior passed
- Tests: `PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/voyage-skill-pycache python3 -B -m unittest tests.test_extensions -v`
- Readback: failures map only to the planned MK-201 gaps; CLI absence, missing constants/APIs/state, 17/19 init graph, permissive extension events, and missing markers are all visible
- Remaining issues: all ST-2011 through ST-2016 implementation work remains
- Next safe action: implement ST-2011 exact kernel constants, smaller init graph, and explicit extension mode marker; run KernelInitializationTests before ST-2012

---

## 2026-08-18 · DEV-0006 · MK-201 · UPDATE

- Status: implementation complete; immutable anchor pending
- Baseline: `7cd0a041883b523da4e71d6d80701b36d22cadab`
- Anchor: pending
- Supersedes: none
- Scope: ST-2011 through ST-2016 implemented; new projects now start from a 15-node/17-edge permanent kernel, optional behavior is represented by a six-entry versioned catalog, and available extensions use decision-bound append-only enable/disable events with explicit event gates, recovery state, and CLI operations
- Non-goals: unchanged; no extension plugin loader, remote catalog, advanced scheduler, appeal engine, quota billing, derived graph query, automatic rule expiry, delivery automation, or deployment automation was added
- Risk: standard; core independent quality, audit authority, environment resources, runtime-readback evidence, minimum-scope blocks, and the minimal rule chain remain available without an extension
- Dependencies: MK-101 through MK-104, DEV-0006 fixed layering decisions, complete pre-implementation test matrix, and recorded red baseline satisfied
- Acceptance gates: 219-test full regression, 28-test extension suite, 22-test recovery suite, compileall, dogfood validate/truth/recover/extension status, CLI reference, schema/runtime/replay convergence, append-only planning, legacy compatibility, read-only recovery, and diff hygiene
- Actual result: PASS before commit; 219 passed, 0 failed, 0 skipped; all 28 extension tests and all 22 recovery tests passed; compileall passed with cache under `/tmp`; dogfood validate returned no errors, truth remained operational with six activation-verified active sources, recover and extension status reported `legacy-compatible` with no invented enable history, CLI reference was current, and `git diff --check` passed
- Tests: all 28 ST-2011 through ST-2016 cases were added before product implementation and exposed 7 assertion failures plus 24 errors including subtests; after implementation, the focused extension suite and the full suite passed; recovery fixtures were migrated to enable `environment-control` through a real scoped User decision before runtime-readback events, preserving the new gate and read-only ledger assertions
- Readback: explicit projects reject audit/channel/environment extension events until the mapped available extension is enabled and reject them again after disable; decisions must match action, project, extension, and version; reserved and unknown extensions cannot enable; enable/disable history remains replayable; effective contracts are additive and keep `independent-quality` mandatory; legacy projects replay old events without fabricated lifecycle state; init creates no extension file or enabled state
- Remaining issues: official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; repository-owned frontmatter, metadata, identity, schema, invocation, dogfood, CLI, replay, extension, and recovery checks pass
- Next safe action: commit the MK-201 implementation, rerun all 219 tests and acceptance gates against the immutable commit, append DEV-0006 CLOSE with its SHA, then commit and push the close record before MK-202

---

## 2026-08-18 · DEV-0006 · MK-201 · CLOSE

- Status: complete
- Baseline: `7cd0a041883b523da4e71d6d80701b36d22cadab`
- Anchor: `a18af8f1486444019ddf27f90d51711f0aeb24f9`
- Supersedes: none
- Scope: ST-2011 through ST-2016 delivered; the permanent kernel is separated from versioned optional extensions, new projects use explicit extension mode, available extension lifecycle changes require scoped User decisions, extension events are gated, and legacy projects remain replay-compatible without fabricated state
- Non-goals: unchanged; no plugin loader, remote catalog, advanced scheduler, appeal engine, quota billing, derived graph query, automatic rule expiry, delivery automation, or deployment automation was introduced
- Risk: standard; accepted only after immutable-anchor readback confirmed that no core gate, authority loop, resource capability, evidence kind, block behavior, or minimal rule transition was weakened
- Dependencies: MK-101 through MK-104 complete; DEV-0006 test-first START, fixed decisions, red baseline, recovery-fixture migration, and implementation-complete UPDATE satisfied
- Acceptance gates: full regression, focused extension and recovery suites, compilation, dogfood validation/truth/recovery/extension status, deterministic CLI reference, runtime/schema/replay convergence, append-only planning, legacy compatibility, ledger non-mutation, clean implementation anchor, and exact commit diff hygiene
- Actual result: PASS; immutable anchor rerun produced 219 passed, 0 failed, 0 skipped; focused extension rerun produced 28 passed; focused recovery rerun produced 22 passed; compileall passed; dogfood validate returned no errors; truth remained operational with six activation-verified active sources; recover and extension status remained `legacy-compatible` with no enabled or disabled extension history; CLI reference was current; `git diff HEAD^ HEAD --check` passed
- Tests: all 28 ST-2011 through ST-2016 cases and all 191 prior tests pass against the exact anchor above; extension enable/disable scope, reserved rejection, event gating, additive core contracts, legacy replay, recovery reporting, CLI exchange, schema coverage, document markers, and smaller init artifacts are exercised
- Readback: anchor contains 10 changed files with 976 insertions and 24 deletions, including the 432-line extension suite; HEAD exactly matched the anchor and the worktree was clean before this CLOSE append
- Remaining issues: official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; repository-owned frontmatter, metadata, identity, schema, invocation, dogfood, CLI, replay, extension, recovery, and append-only contract checks pass
- Next safe action: commit this append-only CLOSE record, push `xp/plan-minimal-kernel`, verify the remote head contains both the implementation anchor and CLOSE commit, then begin MK-202 with a new test-first START record

---

## 2026-08-18 · DEV-0007 · MK-202 · START

- Status: in-progress; test design complete, implementation not started
- Baseline: `2e9a59b9cec2a3654a61d7b3c373068bdce1ea09`
- Anchor: pending
- Supersedes: none
- Scope: turn light/standard/strict from descriptive labels into a versioned work-scoped policy; persist automatic escalation reasons; enforce mode-specific gate, audit, runtime-readback, User-decision, and resource-probe controls; expose policy and work status through CLI and recovery
- Non-goals: no probabilistic risk scorer, remote policy service, identity authentication, background audit scheduler, automatic deployment, arbitrary probe plugin, quota billing, gate waiver, or weakening of the permanent kernel
- Risk: strict; incorrect compression could authorize high-risk execution without User authority or silently omit a slow-loop mandatory gate
- Dependencies: MK-201 complete and remote branch verified at the baseline above; MK-102 typed evidence and MK-104 classified recovery provide the evidence/readback substrate
- Acceptance gates: every ST-2021 through ST-2026 test below is added before product implementation and observed failing for the documented gap; every subtask passes its focused tests before the next begins; final full regression, compileall, dogfood validate/truth/recover/risk status, CLI reference, schema/runtime/replay convergence, append-only planning, legacy replay, and diff hygiene pass
- Actual result: pending
- Tests: ST-2021 through ST-2026 defined below
- Readback: runtime currently stores the declared work risk and only checks a generic decision for strict authorization plus stateful-resource evidence; Light and Standard follow the same gates, Strict has no scoped execution decision, pre/post readback, or audit checkpoint, and no policy/status command exists
- Remaining issues: risk classification evidence, escalation provenance, risk-domain gates, claim probe retention, strict checkpoints, CLI/recovery visibility, and active-document convergence are absent
- Next safe action: add the complete MK-202 suite without product edits, capture the red baseline, then implement ST-2021 only

### DEV-0007 固定风险策略决策

1. Risk policy version 1 is work-scoped. A new `work.created` event records requested mode, effective mode, domains, environment-change flag, escalation reasons, and policy version; older ledgers without this marker replay with their historical behavior.
2. Mode order is `light < standard < strict` and an effective mode never becomes lower than the requested mode or any required resource risk.
3. Light compression requires at least one currently valid typed classification evidence reference. Missing classification evidence upgrades Light to Standard; invalid evidence cannot justify compression.
4. Unknown or disputed classification, any strict resource, or the domains production, persistent-data, security, credentials, permissions, material-cost, public-external-write, gate-relaxation, and irreversible upgrade the work to Strict.
5. Immutable delivery anchors, independent final quality, append-only ledger integrity, truth-defined mandatory gates, loop separation, and User authority boundaries remain required in every mode.
6. Optional gate definitions may name `risk_modes` and `risk_domains`. Mandatory gates always apply; mode gates apply to their named effective mode; domain gates apply to matching Strict work. Compression never removes a mandatory gate.
7. Strict authorization is action-scoped. `work.authorize`, `work.start`, and `resource.claim` reference a non-revoked User decision covering the exact project, work, action, and, for claims, resource. The reference is recorded on each strict action.
8. Strict start requires a fresh valid `runtime-readback` evidence reference. Strict acceptance requires a separate fresh post-action readback and an independent `audit.checked` event on the current immutable delivery anchor.
9. Light and Standard require a fresh post-action runtime readback when the work declares an environment change. They do not acquire Strict pre-action or audit checkpoints merely because an environment changed.
10. Resource claim probes are typed and retained on the lease. Light requires them for conflict-prone resources; Standard requires them for every declared resource; Strict requires them for every declared resource plus the exact User decision above.
11. `audit.checked` belongs to the permanent audit loop, not `advanced-audit`; it is a scoped checkpoint result, not a finding, scheduler, appeal, or project-wide block.
12. `voyage risk policy`, `voyage risk status <work>`, recovery, active truth, and the generated CLI reference expose the same deterministic contract and escalation provenance.

### ST-2021 · 策略目录、分类与自动升级

实现前测试用例：

1. `risk_policy_matrix_has_three_ordered_modes_and_kernel_invariants`：三种模式、顺序和不可压缩内核控制精确且可序列化。
2. `light_with_valid_typed_classification_evidence_remains_light`：有效类型化分类证据允许低风险工作保持 Light。
3. `light_without_valid_classification_evidence_escalates_to_standard`：无证据或 legacy 字符串不能支撑 Light，事件和派生状态记录升级原因。
4. `unknown_disputed_or_strict_domain_escalates_to_strict`：unknown、disputed 和每个高风险域分别自动选择 Strict。
5. `resource_risk_and_requested_mode_are_monotonic`：资源风险和请求模式只允许维持或上调，不能降级。
6. `risk_assessment_is_canonical_in_event_state_status_and_recovery`：同一版本化 assessment 在账本、state、status、recover 中一致。

### ST-2022 · 不可压缩门禁与风险域门禁

实现前测试用例：

1. `all_modes_keep_immutable_anchor_and_independent_quality`：Light/Standard/Strict 均不能绕过交付锚点和独立质量。
2. `mandatory_gate_applies_to_every_mode`：项目 mandatory gate 对三个模式均生效，Light 不构成 waiver。
3. `mode_gate_applies_only_to_named_modes`：非 mandatory 的 `risk_modes` gate 只约束声明的 Standard/Strict 模式。
4. `strict_domain_gate_applies_only_to_matching_domain`：Strict 风险域完整集只要求与工作 domain 匹配的 gate。
5. `gate_policy_fields_are_schema_and_runtime_validated`：risk_modes/risk_domains 类型、枚举和重复值均被 schema/runtime 一致检查。

### ST-2023 · Strict User 决策与前后真实读回

实现前测试用例：

1. `strict_authorize_requires_exact_user_decision_scope`：缺失、非 User、撤销、错误 project/work/action 均拒绝且不追加事件。
2. `strict_start_requires_separate_exact_action_decision`：authorize 决策不能自动替代 start 决策，start 引用被持久化。
3. `strict_start_rejects_missing_invalid_expired_or_wrong_kind_readback`：缺失、无效、过期或非 runtime-readback 均不能执行。
4. `strict_start_accepts_fresh_runtime_readback`：精确决策与新鲜 pre-action 读回共同满足后进入 active。
5. `strict_accept_requires_fresh_post_action_readback`：pre-action 读回不能冒充 post-action，过期或缺失读回阻止验收。
6. `environment_change_requires_post_readback_in_light_and_standard`：环境变更时 Light/Standard 也需新鲜 post-action 读回，普通工作不额外要求。

### ST-2024 · 资源探测与 Strict 审计检查点

实现前测试用例：

1. `light_probes_conflict_resources_but_not_rebuildable_nonconflict_resources`：Light 只为冲突资源承担探测成本。
2. `standard_claim_requires_valid_typed_probe_for_every_resource`：Standard 每个声明资源领取前均需有效 command-result 或 runtime-readback。
3. `strict_claim_requires_probe_and_exact_user_scope`：Strict 同时要求探测证据与精确 project/work/resource/action 决策。
4. `lease_retains_probe_evidence_and_recovery_exposes_it`：领取事件、lease state 和恢复输出保留探测引用。
5. `strict_accept_requires_independent_audit_checkpoint_on_current_anchor`：缺 checkpoint、自审、旧 anchor 或无类型化证据均拒绝；Light/Standard 不被强制。

### ST-2025 · CLI、事件、恢复与原子性

实现前测试用例：

1. `risk_cli_policy_and_status_emit_stable_json`：policy/status 输出模式、控制、assessment、原因和下一安全动作。
2. `work_cli_risk_inputs_drive_automatic_escalation`：risk-domain、unknown、disputed、environment-change 和 evidence 参数进入规范 assessment。
3. `strict_cli_round_trip_enforces_authorize_start_claim_audit_accept`：CLI 完成精确决策、资源探测、pre-readback、audit checkpoint 和 post-readback 链。
4. `audit_checked_matches_runtime_schema_cli_and_replay_sets`：新事件在 runtime、schema、CLI exchange 和 replay 覆盖集合精确一致。
5. `failed_policy_transition_is_atomic`：任何策略门禁失败均不改变 ledger bytes 或 head。
6. `recovery_reports_effective_risk_requirements_and_probe_refs`：跨会话恢复无需记忆即可看见 effective mode、升级原因、缺口和 lease probe。

### ST-2026 · Active 文档、Skill、legacy 与 dogfood

实现前测试用例：

1. `authority_documents_exact_executable_policy_matrix`：active governance truth 的模式矩阵与 runtime 常量一致。
2. `system_and_runbook_document_assessment_scopes_and_checkpoints`：active system/operations truth 描述版本化 assessment、精确 decision scope、读回、探测、audit checkpoint 和 legacy 边界。
3. `skill_preserves_kernel_and_loads_risk_detail_progressively`：Skill 保留不可压缩项，并只在风险任务加载 active governance/system 细节。
4. `cli_reference_contains_risk_and_audit_leaf_commands`：派生 reference 精确包含 risk policy/status 与 audit check。
5. `legacy_work_without_policy_marker_replays_historical_behavior`：旧工作事件不被追溯强加新 scope/readback/checkpoint。
6. `dogfood_project_remains_valid_recoverable_and_policy_visible`：仓库自身 valid/recoverable，旧账本不伪造 assessment，policy contract 可见。

---

## 2026-08-18 · DEV-0007 · MK-202 · UPDATE

- Status: in-progress; red baseline captured
- Baseline: `2e9a59b9cec2a3654a61d7b3c373068bdce1ea09`
- Anchor: pending
- Supersedes: none
- Scope: all 34 ST-2021 through ST-2026 test methods added before product implementation
- Non-goals: unchanged
- Risk: strict
- Dependencies: DEV-0007 START matrix and fixed risk-policy decisions
- Acceptance gates: the suite must expose absent policy constants/status, non-executable mode differences, missing automatic escalation, permissive strict authorization/readback/resource transitions, absent audit checkpoint, missing schema/CLI/recovery convergence, and absent active-document markers before implementation
- Actual result: expected FAIL; 34 tests ran with 32 assertion failures and 13 errors including subtests; only existing immutable-anchor/independent-quality enforcement, failed-transition atomicity, and historical legacy behavior passed
- Tests: `PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/voyage-skill-pycache python3 -B -m unittest tests.test_risk_policy -v`
- Readback: failures map to the planned gaps; missing runtime constants/APIs, unchanged declared risk, permissive gates/claims/strict starts, unsupported `audit.checked`, absent CLI arguments/commands, missing recovery fields, schema rejection of policy gate fields, and missing Skill/active-truth markers are all directly visible
- Remaining issues: all ST-2021 through ST-2026 implementation work remains
- Next safe action: implement ST-2021 versioned policy constants, work assessment normalization, monotonic escalation, status, and recovery projection; run RiskAssessmentTests before ST-2022

---

## 2026-08-18 · DEV-0007 · MK-202 · UPDATE

- Status: in-progress; supplementary review tests captured red
- Baseline: `2e9a59b9cec2a3654a61d7b3c373068bdce1ea09`
- Anchor: pending
- Supersedes: none
- Scope: add explicit missing-control status and cold-start semantic revalidation of policy evidence at the original action time
- Non-goals: unchanged
- Risk: strict
- Dependencies: primary 34-test suite green and first 253-test full regression green after fixture migration
- Acceptance gates: status must name missing Strict controls; a hash-consistent ledger that substitutes valid command evidence for a required runtime readback must fail validation
- Actual result: expected FAIL; 2 tests ran with one missing-field error and one assertion failure because validation returned no semantic policy error
- Tests: `tests.test_risk_policy.RiskCliRecoveryTests.test_risk_status_names_missing_strict_controls` and `test_validate_rechecks_policy_evidence_kind_at_action_time`
- Readback: append-time enforcement is correct, but the derived status is not sufficiently explicit and cold validation currently checks document integrity without rechecking the action-specific evidence kind
- Remaining issues: implement deterministic gaps and event-time semantic evidence validation, then rerun the focused, MK-202, and full suites
- Next safe action: add read-only missing-control derivation and policy evidence validation without changing transition permissions

---

## 2026-08-18 · DEV-0007 · MK-202 · UPDATE

- Status: implementation complete; immutable anchor pending
- Baseline: `2e9a59b9cec2a3654a61d7b3c373068bdce1ea09`
- Anchor: pending
- Supersedes: none
- Scope: ST-2021 through ST-2026 implemented; risk policy version 1 now persists requested/effective modes and escalation provenance, selects mandatory/mode/domain gates, enforces exact Strict User scopes, pre/post runtime readbacks, typed resource probes, retained lease evidence, and current-anchor audit checkpoints, and exposes deterministic policy/status/recovery/CLI contracts
- Non-goals: unchanged; no probabilistic scorer, remote policy service, authentication system, background scheduler, arbitrary probe plugin, quota billing, gate waiver, deployment automation, or weakening of the permanent kernel was introduced
- Risk: strict; accepted before commit only after cold validation, append-time enforcement, immutable-anchor/independent-quality invariants, exact decision scopes, audit-evidence revalidation, atomic failures, and legacy replay were exercised
- Dependencies: MK-101 through MK-201, DEV-0007 fixed decisions, complete pre-implementation matrix, primary red baseline, and supplementary review red cases satisfied
- Acceptance gates: focused risk suite, full regression, compilation, dogfood validate/truth/recover/risk policy, generated CLI reference, runtime/schema/replay convergence, append-only planning, legacy compatibility, Skill metadata validation, and diff hygiene
- Actual result: PASS before commit; 39 risk-policy tests passed and the complete 258-test suite passed with 0 failures, 0 errors, and 0 skips; compileall passed; dogfood validate returned no errors; truth remained operational with six activation-verified active sources and no missing domains; recovery reported zero work, zero unknown/conflicts, six declared legacy facts, and risk policy version 1; `risk policy` returned the ordered Light/Standard/Strict matrix and nine Strict domains; CLI reference and `git diff --check` passed
- Tests: the original 34 tests were written before product implementation and produced 32 assertion failures plus 13 errors including subtests; five supplementary review tests also demonstrated red before their fixes: missing-control status was absent, command evidence could impersonate historical runtime readback, a Light creation could lose classification evidence without cold-validation error, invalid work risk leaked `ValueError`, and tampered current audit-checkpoint evidence did not block Strict acceptance; all 39 now pass
- Readback: Light without valid typed classification evidence upgrades to Standard; unknown/disputed, Strict resources, and all nine fixed domains upgrade to Strict; all modes keep immutable anchors, independent quality, ledger integrity, mandatory gates, and authority separation; Strict authorize/start/claim decisions are exact and non-revoked; start/accept readbacks and resource probes are semantically rechecked at original action time; acceptance revalidates current audit evidence; failed policy actions append nothing; legacy work without the policy marker retains historical behavior
- Fixture migration: existing tests that create version-1 Standard work now provide real typed resource probes, and Strict fixtures provide exact scoped User decisions; recovery fixtures retain a valid typed probe while still testing live unknown/conflict classification, so compatibility was not obtained by weakening the new controls
- Remaining issues: the official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; the repository-owned metadata test and a dependency-free equivalent frontmatter validator pass, `SKILL.md` remains 96 lines, and all runtime/schema/invocation/dogfood checks pass; immutable implementation anchor is still pending
- Next safe action: commit the MK-202 implementation, rerun all 258 tests and acceptance gates against the immutable commit, append DEV-0007 CLOSE with its SHA, then commit and push the close record before MK-301

---

## 2026-08-18 · DEV-0007 · MK-202 · CLOSE

- Status: complete
- Baseline: `2e9a59b9cec2a3654a61d7b3c373068bdce1ea09`
- Anchor: `1559561882e100e50f05d721af54e73dad4ce650`
- Supersedes: none
- Scope: ST-2021 through ST-2026 delivered; executable work-scoped risk policy version 1 now provides monotonic classification, mode/domain gates, exact Strict decisions, pre/post runtime readbacks, typed resource probes, retained lease evidence, independent current-anchor audit checkpoints, cold semantic evidence validation, deterministic CLI/status/recovery output, active documentation, and legacy compatibility
- Non-goals: unchanged; no probabilistic scorer, remote policy service, authentication system, background scheduler, arbitrary probe plugin, quota billing, gate waiver, deployment automation, or kernel weakening was introduced
- Risk: strict; accepted only after immutable-anchor readback proved core anchors, independent quality, mandatory gates, loop separation, User authority, typed evidence validity, append atomicity, and historical replay remain enforced
- Dependencies: MK-101 through MK-201 complete; DEV-0007 START, fixed policy decisions, 34-test primary red baseline, five supplementary red review tests, fixture migration, and implementation-complete UPDATE satisfied
- Acceptance gates: exact anchor identity, clean pre-CLOSE worktree, focused risk suite, complete regression, compilation, dogfood validate/truth/recover/risk policy, deterministic CLI reference, schema/runtime/replay convergence, Skill metadata and equivalent validation, legacy replay, append-only planning, and commit diff hygiene
- Actual result: PASS; HEAD exactly matched the anchor; 39 focused risk-policy tests passed; all 258 tests passed with 0 failures, 0 errors, and 0 skips; compileall passed; dogfood validate returned no errors; truth was operational with six activation-verified sources, no gaps, and no unverified active source; recovery reported no work, unknown, or conflict and exposed policy version 1; risk readback returned ordered Light/Standard/Strict modes and nine Strict domains; CLI reference, metadata consistency, equivalent Skill validation, and `git diff HEAD^ HEAD --check` passed
- Tests: all 39 DEV-0007 tests and all 219 prior tests pass against the exact anchor; coverage includes automatic escalation, mandatory/mode/domain gates, decision scope, revoked decisions, readback freshness and kind, resource probe retention, audit independence and evidence revalidation, atomic failures, cold-start semantic checks, CLI/schema/replay exchange, active truth markers, dogfood, and legacy behavior
- Readback: anchor contains 15 changed files with 1536 insertions and 33 deletions, including the 680-line risk-policy suite; the worktree was clean before this CLOSE append; the anchor preserves a 96-line progressively disclosed `SKILL.md`
- Remaining issues: official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; repository-owned metadata, equivalent frontmatter, runtime, schema, invocation, dogfood, recovery, risk, and append-only checks pass
- Next safe action: commit this append-only CLOSE record, push `xp/plan-minimal-kernel`, verify the remote head contains both the implementation anchor and CLOSE commit, then begin MK-301 with a new test-first START record

---

## 2026-08-18 · DEV-0008 · MK-301 · START

- Status: in-progress; test design complete, implementation not started
- Baseline: `cd0416c9a9b1a89eb204d3507f2cf6f74cb0bdc4`
- Anchor: pending
- Supersedes: none
- Scope: make the reserved `derived-graph` catalog entry available through explicit extension governance; derive a deterministic read-only graph from manifest/truth registry, ledger, resource/gate definitions, and content-addressed evidence; add structural consistency checks and deterministic path queries; expose `voyage graph derive`, `voyage graph check`, and `voyage graph path <from> <to>`
- Non-goals: no graph database, persisted index or cache, graph UI, writable graph API, event-ledger replacement, probabilistic inference, arbitrary query language, remote graph service, background monitor, or new authoritative state
- Risk: standard; commands are read-only, but an incorrect projection or consistency result could hide a blocked path, mislabel an invalid anchor, or encourage work from a false graph view
- Dependencies: MK-104 classified recovery, MK-201 extension lifecycle, MK-202 executable risk/readback semantics, clean local and remote baseline at the SHA above
- Acceptance gates: all ST-3011 through ST-3016 tests below are added before product implementation and observed failing for the documented gaps; every subtask passes its focused tests before the next begins; final full regression, compileall, dogfood validate/truth/recover/extension status, CLI reference, derived-graph schema, append-only planning, read-only filesystem/ledger checks, legacy compatibility, and diff hygiene pass
- Actual result: pending
- Tests: ST-3011 through ST-3016 defined below
- Readback: `derived-graph` is currently reserved, no graph command or derived exchange schema exists, runtime relationships remain dispersed across replay state and event payloads, and no generic path or graph consistency report is available
- Remaining issues: extension access, deterministic exchange model, complete node/edge projection, structural checks, path semantics, CLI/schema/docs/Skill convergence, and dogfood behavior remain unimplemented
- Next safe action: add the complete 32-test MK-301 suite without product edits, capture the red baseline, then implement ST-3011 only

### DEV-0008 固定派生图决策

1. `derived-graph` remains an optional extension and becomes catalog-available at version `1.0.0`. Every explicit or legacy-compatible project must append an exact scoped User decision and `extension.enabled` event before graph queries; legacy history never fabricates enabled state.
2. `graph derive`, `graph check`, and `graph path` are read-only. They never append an event, update a manifest, create a cache/index, or write a generated graph file. Disable immediately removes query access without deleting history.
3. Derived graph exchange version 1 contains `schema_version`, `project_id`, `ledger_head`, deterministic source fingerprints, sorted `nodes`, sorted `edges`, and one overall fingerprint. It contains no wall-clock generation timestamp, session field, or nondeterministic ordering.
4. Every node has a namespaced stable ID, kernel/effective node type, status, scope, authority, risk, evidence references, provenance, optional supersession, and deterministic attributes. Every edge has a content-derived stable ID, effective edge type, source, target, status, authority, evidence, provenance, and deterministic attributes.
5. The only derivation inputs are project files resolved by the manifest: active truth registry, append-only ledger, graph/resource/gate definitions, and content-addressed evidence. Chat memory, summaries, worker claims, and unregistered files are never graph facts.
6. Projection covers project, four loop bindings, principals, truth sources, User decisions, work and dependencies, all delivery attempts, immutable anchors, referenced/stored evidence, gates/results, resources/leases, rules/supersession, blocks/appeal targets, and explicit external dependency anchors.
7. Work dependency edges point from dependent work to prerequisite work or explicit external anchor. `graph path` uses directed breadth-first search, sorted edge order, and returns the deterministic shortest path. Unknown endpoints are errors; known disconnected endpoints return `found: false` without mutation.
8. `graph check` returns sorted versioned issues with severity, code, subject, related IDs, and message. Errors include duplicate IDs, unknown types, dangling endpoints/internal dependencies, dependency cycles, invalid immutable anchors, orphan active nodes, and active blocks without an independent resolution target. Findings make CLI check exit 1 with JSON, while usage/project-access errors exit 2.
9. Graph checking must still diagnose hash-consistent damaged work dependency payloads even when normal replay would reject them. It may return a partial diagnostic result, but it must never treat that partial view as valid or authoritative.
10. Active orphan detection uses reachability from the single project node over the undirected form of graph edges. Stored but not yet consumed evidence is non-active and may remain disconnected without failing the check.
11. An active block has a resolution path only when it preserves a non-empty unblock condition and names an appeal target different from the blocking actor. The graph does not claim the appeal succeeds; it only proves a structurally independent target exists.
12. The derived view is disposable. Deleting all hypothetical output leaves project truth unchanged, and identical registered inputs reproduce byte-identical canonical JSON and the same fingerprint.

### ST-3011 · 扩展生命周期与只读访问边界

实现前测试用例：

1. `derived_graph_catalog_is_available_with_stable_empty_additive_contract`：目录仍为六项，`derived-graph` 版本为 1.0.0、available，且不伪造新事件、节点、边或门禁类型。
2. `graph_queries_require_explicit_enabled_extension`：全新 explicit 项目和 legacy-compatible 项目均拒绝 derive/check/path，且 ledger bytes 不变。
3. `derived_graph_enable_requires_exact_user_scope`：缺失、撤销、错误 action/project/extension/version 的 User decision 均不能开放查询。
4. `disable_revokes_graph_query_access_without_deleting_history`：启用后可查询，停用后立即拒绝，enable/disable 历史仍可恢复。
5. `graph_access_checks_do_not_create_control_files_or_events`：成功和失败的访问检查均不创建 graph cache/index，不追加事件。

### ST-3012 · 稳定派生合同与完整节点边投影

实现前测试用例：

1. `derive_is_byte_deterministic_and_fingerprint_bound_to_registered_inputs`：相同输入两次 canonical JSON 完全一致；ledger 或已注册定义改变后 fingerprint 改变。
2. `derive_projects_project_truth_loops_principals_decisions_and_work`：项目、active truth、四 loop、事件 actor、User decision 和 work 节点均具有完整固定字段与可追溯 provenance。
3. `derive_traces_every_delivery_anchor_evidence_and_gate_result`：所有交付尝试、当前/旧 anchor、执行/质量/门禁 evidence 与 verdict 可沿边追溯，不把旧 verdict 转移到新 anchor。
4. `derive_traces_resources_historical_leases_and_release_state`：资源定义、active/released lease、holder、work、probe evidence 和 release 关系均保留。
5. `derive_traces_rules_supersession_blocks_and_appeal_targets`：规则状态/supersession 与 block→work、block→independent appeal target 关系完整。
6. `derived_ids_types_sorting_and_schema_are_exact`：node/edge ID 唯一稳定，类型属于 effective contract，节点/边排序固定，version-1 derived schema 接受输出并拒绝未知字段。

### ST-3013 · 一致性检查与损坏输入诊断

实现前测试用例：

1. `healthy_derived_graph_has_zero_errors_and_stable_summary`：完整合法项目 check 为 valid，错误计数为零且摘要确定。
2. `check_reports_hash_consistent_dangling_internal_dependency`：重算哈希链后的未知内部 work dependency 返回 `dangling-reference`，而非 traceback 或笼统 replay 异常。
3. `check_reports_canonical_dependency_cycle`：损坏但哈希一致的 A→B→A 依赖返回一次规范化 `dependency-cycle` 路径。
4. `check_revalidates_current_immutable_anchor`：删除、篡改或错误 kind 的当前 anchor 返回 `invalid-anchor`，旧 superseded anchor 单独标识而不冒充当前交付。
5. `check_reports_orphan_active_node_and_dangling_edge`：传入损坏派生视图时检测不可达 active 对象与缺失端点，stored 未消费 evidence 不误报。
6. `check_reports_active_block_without_independent_resolution_target`：appeal target 缺失或等于 blocker 时返回 `unresolvable-block`，独立 target 通过。

### ST-3014 · 确定性路径查询

实现前测试用例：

1. `path_returns_deterministic_shortest_project_to_current_anchor_route`：project→work→delivery→anchor 返回稳定最短节点/边序列。
2. `path_traces_work_dependency_to_prerequisite`：dependent work 到 prerequisite 的 directed path 使用 `depends-on` 边。
3. `path_traces_block_to_work_and_independent_appeal_target`：block 可分别到达被阻塞 work 与 appeal principal。
4. `path_known_but_disconnected_returns_not_found_without_mutation`：已知不连通端点返回 `found: false`、空路径且不写账本/文件。
5. `path_unknown_endpoint_is_deterministic_error`：未知 from/to 明确指出端点，不退化为 KeyError 或空成功。

### ST-3015 · CLI、Schema、退出码与原子只读性

实现前测试用例：

1. `graph_cli_reference_contains_all_leaf_commands_once`：argparse 与权威 runbook 各精确包含 derive/check/path 一次。
2. `graph_cli_derive_and_path_emit_stable_json`：CLI 输出与 core API canonical 内容一致，重复调用稳定。
3. `graph_cli_check_uses_exit_one_for_findings_and_json_stdout`：一致性 finding 返回 1 和结构化 JSON；无 traceback；访问/参数错误仍返回 2。
4. `derived_graph_schema_is_exercised_by_repository_contract_tests`：新增 schema 有正反实例，加入“每份 schema 均被测试”守卫。
5. `all_graph_commands_are_read_only_across_ledger_and_control_tree`：三条命令成功、not-found、finding 路径前后 ledger bytes 与 control-tree 内容摘要完全相同。

### ST-3016 · Active 文档、Skill、dogfood 与 legacy

实现前测试用例：

1. `system_truth_documents_exact_derived_graph_contract_and_issue_codes`：active system truth 描述版本、来源、节点/边字段、只读边界和全部错误码。
2. `runbook_documents_enable_derive_check_path_and_exit_semantics`：active operations truth 描述显式 enable、三命令、退出码、无缓存和损坏输入诊断。
3. `skill_loads_graph_detail_only_for_graph_tasks`：Skill 先查 extension status，再解析 active system/runbook，且不硬编码 graph 文件或数据库。
4. `dogfood_remains_valid_recoverable_and_does_not_invent_graph_enablement`：仓库 validate/recover 通过，catalog 显示 available，但 legacy-compatible dogfood 未启用且查询拒绝不变更账本。
5. `docs_and_runtime_reject_graph_database_cache_ui_and_writable_truth_claims`：正式合同与 runtime 均不创建/承诺数据库、缓存、UI、写 API 或第二真源。

---

## 2026-08-18 · DEV-0008 · MK-301 · UPDATE

- Status: in-progress; red baseline captured
- Baseline: `cd0416c9a9b1a89eb204d3507f2cf6f74cb0bdc4`
- Anchor: pending
- Supersedes: none
- Scope: all 32 ST-3011 through ST-3016 test methods added before product implementation
- Non-goals: unchanged
- Risk: standard
- Dependencies: DEV-0008 START matrix and fixed derived-graph decisions
- Acceptance gates: suite must expose reserved extension access, absent derive/check/path APIs and CLI, missing deterministic exchange/schema, absent consistency/path behavior, missing read-only guarantees, and absent active-document/Skill markers before implementation
- Actual result: expected FAIL; 32 tests ran with 3 assertion failures and 32 errors including subtests
- Tests: `PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/voyage-skill-pycache python3 -B -m unittest tests.test_derived_graph -v`
- Readback: `derived-graph` remains reserved; enable fails before scoped decision behavior can be exercised; core has no `derive_graph`, `check_graph`, or `graph_path`; CLI commands, derived schema, reference entries, and documentation markers are absent; failures map to the planned gaps rather than an unrelated regression
- Remaining issues: all ST-3011 through ST-3016 implementation work remains
- Next safe action: implement ST-3011 catalog availability and exact enabled-state read access without adding derivation behavior beyond the minimum access boundary; run GraphExtensionAccessTests before ST-3012

---

## 2026-08-18 · DEV-0008 · MK-301 · UPDATE

- Status: implementation complete; immutable anchor pending
- Baseline: `cd0416c9a9b1a89eb204d3507f2cf6f74cb0bdc4`
- Anchor: pending
- Supersedes: none
- Scope: ST-3011 through ST-3016 implemented; `derived-graph` is now an explicitly governed available extension with deterministic read-only derive, consistency-check, and directed shortest-path queries over registered project inputs
- Non-goals: unchanged; no graph database, persisted index or cache, graph UI, writable graph API, event-ledger replacement, probabilistic inference, arbitrary query language, remote graph service, background monitor, or new authoritative state was introduced
- Risk: standard; accepted before commit only after access control, deterministic exchange, registered-source fingerprints, complete projection, damaged-input diagnostics, anchor readback, path stability, schema/CLI convergence, and filesystem/ledger immutability were exercised
- Dependencies: MK-104, MK-201, MK-202, DEV-0008 fixed decisions, complete 32-test pre-implementation matrix, and captured red baseline satisfied
- Acceptance gates: focused derived-graph suite, full regression, compilation, dogfood validate/truth/recover/extension status, governed disabled-query rejection, ledger readback, generated CLI reference, derived-graph schema coverage, Skill metadata and equivalent validation, append-only planning, legacy compatibility, and diff hygiene
- Actual result: PASS before commit; all 32 MK-301 tests passed and the complete 290-test suite passed with 0 failures, 0 errors, and 0 skips; compileall passed; dogfood validate returned no errors; truth remained operational with six activation-verified active sources and no missing domains; recovery reported no work, unknown, or conflict and retained six declared legacy facts; extension status exposed `derived-graph` as available but not enabled in legacy-compatible dogfood; CLI reference and `git diff --check` passed
- Tests: the 32 tests were written before product implementation and initially produced 3 assertion failures plus 32 errors including subtests; focused completion was ST-3011 5/5, ST-3012 6/6, ST-3013 6/6, ST-3014 5/5, ST-3015 5/5, and ST-3016 5/5; the first complete regression exposed one stale extension-test assumption that every available extension adds events, which was corrected to assert the exact three event-bearing extensions and the empty additive `derived-graph` contract before the final 290/290 pass
- Readback: identical registered inputs produce sorted version-1 nodes and edges with stable source and overall fingerprints; projection includes truth, loops, principals, decisions, work/dependencies, every delivery and anchor, evidence, gates, resources/leases, rules, blocks/appeals, and external anchors; check reports duplicate/unknown/dangling/cycle/invalid-anchor/orphan/unresolvable/project-invalid findings, including hash-consistent dependencies that normal replay rejects; path uses sorted directed BFS; all graph commands and access failures are read-only
- Dogfood immutability: `graph derive` without explicit enable returned exit 2 and `derived-graph extension is not enabled`; `.voyage/ledger/events.jsonl` remained SHA-256 `0a6ba5707c289a63cc277efaec5283ba9916a3426d566231c2c33a2c784c40eb` before and after the rejected query, and no cache, index, or generated graph file appeared
- Remaining issues: the official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; the repository-owned metadata tests and dependency-free equivalent validator pass, `SKILL.md` remains progressively disclosed at 104 lines, and all runtime/schema/invocation/dogfood checks pass; immutable implementation anchor is still pending
- Next safe action: commit the MK-301 implementation, rerun all 32 focused tests, all 290 repository tests, and acceptance gates against the exact immutable commit, append DEV-0008 CLOSE with its SHA, then commit and push the close record

---

## 2026-08-19 · DEV-0008 · MK-301 · CLOSE

- Status: complete
- Baseline: `cd0416c9a9b1a89eb204d3507f2cf6f74cb0bdc4`
- Anchor: `e617cf4cc9c16a62a0e211d3a13f6b53aee2d458`
- Supersedes: none
- Scope: ST-3011 through ST-3016 delivered; the explicitly governed `derived-graph` extension now provides deterministic disposable graph derivation, structural consistency diagnostics, current-anchor validation, and directed stable shortest-path queries over registered project inputs
- Non-goals: unchanged; no graph database, persisted index or cache, graph UI, writable graph API, event-ledger replacement, probabilistic inference, arbitrary query language, remote graph service, background monitor, or second source of truth was introduced
- Risk: standard; accepted only after immutable-anchor readback proved access governance, read-only behavior, deterministic exchange, registered-input provenance, damaged-input diagnostics, schema/CLI convergence, Skill progressive disclosure, legacy compatibility, and repository invariants remain enforced
- Dependencies: MK-104, MK-201, and MK-202 complete; DEV-0008 START, fixed decisions, 32-test red baseline, six focused subtask passes, implementation-complete UPDATE, and exact implementation commit satisfied
- Acceptance gates: exact anchor identity, clean pre-CLOSE worktree, 32 focused tests, complete 290-test regression, compilation, dogfood validate/truth/recover/extension status, governed disabled-query rejection, ledger immutability readback, deterministic CLI reference, derived schema coverage, Skill metadata and equivalent validation, append-only planning, legacy replay, and commit diff hygiene
- Actual result: PASS; HEAD exactly matched the anchor before this CLOSE append; all 32 MK-301 tests passed; all 290 repository tests passed with 0 failures, 0 errors, and 0 skips; compileall passed; dogfood validate returned no errors; truth was operational with six activation-verified sources, no gaps, and no unverified source; recovery reported zero work, zero unknown, zero conflicts, and six declared legacy facts; extension status remained legacy-compatible with no invented enablement; CLI reference and `git diff HEAD^ HEAD --check` passed
- Tests: all 32 DEV-0008 tests and all 258 prior tests pass against the exact anchor; coverage includes exact extension decisions and disable behavior, byte-stable fingerprints, full node/edge projection, duplicate/unknown/dangling/cycle/anchor/orphan/block diagnostics, partial damaged-ledger reporting, deterministic directed BFS, CLI exit semantics, schema positive/negative instances, control-tree and ledger immutability, active documentation, Skill loading, dogfood, and legacy behavior
- Readback: a dogfood `graph derive` without explicit enable returned exit 2 with `derived-graph extension is not enabled`; `.voyage/ledger/events.jsonl` remained SHA-256 `0a6ba5707c289a63cc277efaec5283ba9916a3426d566231c2c33a2c784c40eb` before and after; the anchor contains 10 changed files with 1977 insertions and 6 deletions, including the version-1 exchange schema and 743-line derived-graph suite; the worktree was clean before this CLOSE append; `SKILL.md` remains progressively disclosed at 104 lines
- Remaining issues: the official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; repository-owned metadata tests and the dependency-free equivalent validator pass, along with all runtime, schema, invocation, dogfood, recovery, extension, graph, append-only, and diff checks
- Next safe action: commit this append-only CLOSE record, push `xp/plan-minimal-kernel`, verify the remote head contains both the implementation anchor and CLOSE commit, then select the next planned work item without expanding the permanent kernel

---

## 2026-08-19 · DEV-0009 · MK-302 · START

- Status: in-progress; test design complete, implementation not started
- Baseline: `836e158b779b70b536ddb1458b0f7cb60f0dcc56`
- Anchor: pending
- Supersedes: none
- Scope: add a reproducible versioned full-ledger benchmark and quantitative snapshot-review policy; make the Unix advisory-lock boundary import-safe and visible during recovery; converge the local actor trust statement and resource identity contract; make interrupted initialization resumable through a scoped bootstrap marker
- Non-goals: no snapshot, checkpoint, incremental index, ledger compaction, event deletion, background benchmark, database, remote lock service, speculative Windows locking adapter, cryptographic identity/signature system, multi-host writer coordination, README addition, or weakening of full hash-chain validation
- Risk: standard; performance diagnostics are read-only, but lock fallback, initialization recovery, or misleading trust claims could permit unsafe writes, duplicate initialization, overwrite user-owned inputs, or imply protections the runtime does not provide
- Dependencies: MK-103 converged event/resource contracts and MK-301 full-ledger graph projection complete; local and remote branch both resolve to the baseline; current repository has 290 passing tests and a clean worktree before this append
- Acceptance gates: all ST-3021 through ST-3026 tests below are added before product implementation and observed failing only for documented gaps; every subtask passes focused tests before the next; final complete regression, compilation, dogfood validate/truth/recover, benchmark smoke run, CLI reference if changed, Skill metadata, append-only planning, initialization retry readback, unsupported-lock atomicity, legacy compatibility, and diff hygiene pass
- Actual result: pending
- Tests: ST-3021 through ST-3026 defined below; 31 test methods planned
- Readback: a one-run synthetic baseline on this machine measured full `load_events + validate_hash_chain + replay_events` at 1,000 events/470,748 bytes in 0.0074 seconds, 10,000/4,727,748 in 0.0749 seconds, 50,000/23,727,748 in 0.4353 seconds, and 100,000/47,477,748 in 0.9164 seconds, all with zero chain errors; current import hard-depends on `fcntl`; current init publishes manifest before later artifacts and has no retry marker; actor trust is already documented in governance but is not exposed in recovery or Skill; resource event identity is implemented but lacks one final cross-layer guard
- Remaining issues: benchmark exchange/policy, unsupported-platform import/write behavior, recovery capability readout, trust convergence, resource identity guard, resumable init marker, active documentation, and Skill loading remain unimplemented
- Next safe action: add all 31 tests without product edits, capture the red baseline, then implement ST-3021 only

### DEV-0009 固定性能、平台与信任决策

1. Version-1 benchmark measures three independent phases over a synthetic append-only ledger: JSONL load, complete hash-chain validation, and complete replay. Default event counts are 1,000, 10,000, and 100,000; reports include event/byte counts, per-run samples, medians, errors, Python/platform identity, policy thresholds, and a decision, but no project state or authoritative claim.
2. Snapshot review thresholds are 2.0 seconds median full-chain processing at 100,000 events or 256 MiB ledger size. Crossing either threshold returns `investigate-snapshot`; it never creates a snapshot. Missing the 100,000-event sample returns `insufficient-data`; staying below both returns `retain-full-replay`.
3. The measured 100,000-event baseline is 0.9164 seconds and 47,477,748 bytes, below both thresholds. MK-302 therefore adds no snapshot/checkpoint/index API, file, event, or truth source. Any future snapshot requires a separate User-approved work item, must bind to an exact ledger-head hash, remain disposable, and preserve full-chain validation as the authority.
4. Benchmarking is an explicit diagnostic script, never part of normal init, validate, recover, append, or graph commands. Small custom counts/runs support tests and local calibration; benchmark execution writes only to a temporary directory and cannot mutate a managed project.
5. v0.x write serialization officially supports Unix `fcntl` advisory locks. The module must still import and all read-only validation/recovery must work when `fcntl` is unavailable; every ledger write must then fail deterministically before mutation with the supported-platform boundary and next action. No untested Windows adapter is claimed.
6. Recovery exposes a versioned runtime-capability object naming platform, lock backend/support, append permission, and actor authentication mode. It is a local capability readout, not evidence that another writer or hostile process is absent.
7. Actor IDs and loop labels remain caller assertions. Hashes detect later ledger modification but do not authenticate the caller, prevent a malicious same-account process from appending through the API, or make local history tamper-proof. The trusted boundary is the OS account and worktree permissions; hostile multi-writer use requires an external authenticated gateway or future separately approved signature design.
8. Resource lifecycle identity is canonical: `resource.claimed`, `resource.released`, and `resource.recovered` subjects are the resource ID; payload repeats the same resource ID and carries the lease ID; lease-oriented CLI/API queries must resolve the resource from replayed state rather than reinterpret subject.
9. Interrupted init uses `.voyage/init-state.json` version 1 as a temporary, non-authoritative recovery marker containing exact project ID, registry path/mode, completed phase, and next safe action. Rerunning identical init arguments resumes idempotently; different arguments refuse without mutation; successful completion removes the marker and records exactly one `project.initialized` event.
10. Init may recreate only marker-owned generated bootstrap artifacts. It must never overwrite or delete an adopted truth registry or unrelated user file. Atomic JSON writes remain mandatory; an interrupted project cannot be treated as operational or authorize work.
11. No new README is created because VoyageSkill is a Skill package and `skill-creator` forbids auxiliary documentation. The active product, governance, system, operations truths and concise `SKILL.md` must carry the platform/trust/recovery boundaries consistently.

### ST-3021 · 可重复账本基准与量化策略

实现前测试用例：

1. `benchmark_policy_is_versioned_and_quantitative`：版本、默认规模、100,000 事件、2.0 秒和 256 MiB 阈值均为固定可序列化合同。
2. `small_benchmark_measures_load_hash_and_replay_without_errors`：小规模多次运行输出每阶段样本、中位数、字节数、零链错误和真实末事件读回。
3. `below_threshold_retains_full_replay`：完整目标样本低于时间和大小阈值时决定精确为 `retain-full-replay`。
4. `time_or_size_threshold_requires_investigation_only`：任一阈值达到时只返回 `investigate-snapshot` 与原因，不创建或声称已有快照。
5. `missing_target_sample_is_insufficient_data`：未运行 100,000 事件时不以小样本外推通过，明确返回 `insufficient-data`。
6. `benchmark_script_emits_json_and_mutates_no_project_file`：脚本支持自定义小规模和 runs，输出结构化 JSON，运行前后项目树摘要和账本完全一致。

### ST-3022 · 长账本全链权威与无快照边界

实现前测试用例：

1. `ten_thousand_event_ledger_loads_validates_and_replays_exact_head`：10,000 事件 JSONL 全量加载、哈希验证和重放产生精确 head 与观测计数。
2. `append_after_long_ledger_preserves_chain_and_single_new_head`：长账本追加仍验证全部历史，只增加一条事件且 prev-hash 精确引用旧 head。
3. `runtime_contains_no_snapshot_checkpoint_or_incremental_index_surface`：core、CLI、schema 和初始化产物不存在快照、checkpoint 或增量索引合同。
4. `benchmark_and_docs_require_separate_user_work_before_snapshot`：超过阈值只建议独立 User-approved 工作，删除任何未来派生快照仍以全账本恢复为前提。

### ST-3023 · 平台锁边界与恢复能力读回

实现前测试用例：

1. `runtime_capabilities_report_fcntl_backend_on_supported_host`：当前 Unix 主机报告 `fcntl`、supported/append-safe 为真和版本化字段。
2. `core_import_and_read_only_validation_do_not_require_fcntl`：模拟 `fcntl` 不可用时，加载、校验、重放和 recovery 仍可执行。
3. `unsupported_write_lock_fails_before_ledger_mutation`：无锁后端时 append 返回确定性 VoyageError，账本 bytes/head 不变且不创建误导性事件。
4. `recovery_names_unsupported_platform_next_action`：恢复输出明确只读能力、不可追加和迁移到受支持 Unix/外部序列化写入器的下一动作。
5. `active_docs_state_unix_only_write_support_without_windows_claim`：正式合同与 runbook 明确 `fcntl` Unix 边界、只读可移植性和未提供 Windows adapter。

### ST-3024 · Actor 信任模型收敛

实现前测试用例：

1. `runtime_capabilities_deny_cryptographic_actor_authentication`：运行时合同明确 local asserted identity、cryptographic=false、tamper-evident=true、tamper-proof=false。
2. `authority_product_system_and_skill_share_exact_trust_boundary`：active truth 与 Skill 均说明 OS account/worktree 是边界，actor/loop 为声明，哈希不认证调用者。
3. `docs_do_not_claim_signatures_hostile_writer_protection_or_multi_host_locking`：正式文档不虚构签名、恶意本机写者防护或分布式锁。
4. `skill_keeps_trust_detail_progressively_disclosed`：Skill 只保留一句停止条件并引导解析 active governance/system 真源，不复制长篇平台实现。

### ST-3025 · 资源事件身份与查询合同终检

实现前测试用例：

1. `all_resource_lifecycle_events_use_resource_subject_and_lease_payload`：claim/release/recover 的 subject、payload.resource_id 和 payload.lease_id 始终符合 canonical contract。
2. `resource_identity_mismatch_is_rejected_before_replay_state_changes`：三类事件任一 subject/payload 不一致均确定性失败且不推进 head。
3. `lease_oriented_cli_resolves_resource_from_replayed_state`：release/recover 只给 lease ID 时写出的事件仍以真实 resource ID 为 subject，不接受调用者猜测。
4. `schema_graph_recovery_and_docs_use_the_same_resource_identity`：Schema、派生图、恢复输出和 runbook 对 resource/lease 身份无漂移。

### ST-3026 · 中断初始化标记与幂等恢复

实现前测试用例：

1. `successful_init_removes_recovery_marker_and_records_one_event`：正常 init 无残留 marker，账本恰有一个匹配的 initialization event。
2. `interrupted_init_leaves_versioned_scoped_marker`：在 control/truth/ledger 阶段注入 I/O 中断时保留 marker，记录已完成 phase、精确参数和重试动作。
3. `same_arguments_resume_interrupted_init_idempotently`：相同参数重跑完成合法 bootstrap，不重复 initialization event，不产生额外真源。
4. `resume_after_initial_event_does_not_duplicate_ledger_head`：事件已落盘但 marker 未清除的中断可恢复，最终仍只有一个 initialization event。
5. `mismatched_resume_arguments_refuse_without_mutation`：project ID、registry path 或 adopt/generated mode 改变时拒绝，marker、账本和用户文件 bytes 不变。
6. `adopted_truth_registry_is_never_overwritten_during_retry`：采用已有 registry 的失败与重试全过程保持其摘要不变。
7. `interrupted_project_cannot_validate_as_operational_or_authorize_work`：未完成 init 不会被误认 operational；CLI/core 给出恢复指令而非 traceback 或半初始化成功。

---

## 2026-08-19 · DEV-0009 · MK-302 · UPDATE

- Status: in-progress; red baseline captured
- Baseline: `836e158b779b70b536ddb1458b0f7cb60f0dcc56`
- Anchor: pending
- Supersedes: DEV-0009 START test-count field only; the six detailed ST-3021 through ST-3026 lists remain unchanged
- Scope: all tests were added before product implementation; the START summary's “31 test methods” is corrected to 30 because the fixed detailed groups total 6+4+5+4+4+7
- Non-goals: unchanged
- Risk: standard
- Dependencies: DEV-0009 START fixed decisions and detailed test matrix
- Acceptance gates: the suite must expose absent benchmark module/script/policy, no runtime capability exchange, unconditional `fcntl` import, permissive unsupported writes, missing platform/trust/benchmark active documentation, absent init recovery marker/resume behavior, and any remaining cross-layer resource identity drift before implementation
- Actual result: expected FAIL; 30 tests ran with 4 passes, 15 assertion failures, and 11 errors; the four existing passes prove 10,000-event full replay, long-ledger append/hash continuity, canonical resource lifecycle events, and lease-oriented CLI subject resolution already work
- Tests: `PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/voyage-skill-pycache python3 -B -m unittest tests.test_platform_performance -v`
- Readback: benchmark imports and script are absent; `runtime_capabilities` and recovery capability output are absent; patching the planned `_fcntl` boundary does not stop current writes because core imports `fcntl` directly; initialization ignores the phase hook and leaves no marker; Skill/platform/trust/threshold markers are absent; adopted registry and successful init legacy behavior remain intact; ST-3025 additionally found a real derived-graph null bug where an active executor with `delivery=None` reaches `work.get("delivery", {}).get(...)`
- Remaining issues: all ST-3021 through ST-3026 implementation remains; fix the discovered graph null handling within ST-3025 and add a precise assertion that active undelivered work remains derivable
- Next safe action: implement only ST-3021 benchmark policy/module/script, run BenchmarkPolicyTests, then proceed in order

---

## 2026-08-19 · DEV-0009 · MK-302 · UPDATE

- Status: in-progress; supplementary initialization safety review captured red and fixed
- Baseline: `836e158b779b70b536ddb1458b0f7cb60f0dcc56`
- Anchor: pending
- Supersedes: none
- Scope: add two negative cases found during pre-commit review: invalid adopted-registry input must not create a recovery marker, and fresh init must not overwrite pre-existing default control/truth targets that no marker owns
- Non-goals: unchanged
- Risk: standard
- Dependencies: primary 30-test suite green and ST-3026 marker/resume implementation
- Acceptance gates: both cases fail before their fix, then pass with all InitRecoveryTests; no existing bootstrap/adoption behavior is weakened
- Actual result: expected FAIL first; two test methods produced four assertion failures including three pre-existing target subtests; after preflight was moved ahead of marker publication and marker ownership was enforced, all 9 InitRecoveryTests passed
- Tests: `test_invalid_adopted_registry_does_not_create_recovery_marker` and `test_fresh_init_refuses_preexisting_targets_without_overwrite`; total MK-302 suite is now 32 tests
- Readback: the failed version left `.voyage/init-state.json` for a missing adopted path and silently overwrote `.voyage/graph.json`, `docs/voyage/product.md`, or the default registry; the fixed version validates adopted input and checks all generated targets before marker creation, preserving bytes and leaving no marker on invalid fresh input
- Remaining issues: rerun all 32 MK-302 tests and the complete repository suite, then perform final dogfood/benchmark/Skill/diff acceptance
- Next safe action: run the expanded focused suite and complete regression before appending the implementation-complete record

---

## 2026-08-19 · DEV-0009 · MK-302 · UPDATE

- Status: implementation complete; immutable anchor pending
- Baseline: `836e158b779b70b536ddb1458b0f7cb60f0dcc56`
- Anchor: pending
- Supersedes: none
- Scope: ST-3021 through ST-3026 delivered; version-1 disposable full-ledger benchmarking and quantitative no-snapshot policy, import-safe Unix lock capability, recovery-visible platform/trust boundary, canonical resource identity closure, active documentation, and resumable marker-based initialization are implemented
- Non-goals: unchanged; no snapshot, checkpoint, incremental index, compaction, event deletion, database, remote lock service, Windows locking adapter, cryptographic identity/signature system, multi-host writer coordination, README, or weaker hash validation was introduced
- Risk: standard; accepted before commit only after full-chain authority, invalid benchmark handling, unsupported-lock atomicity, actor trust denial, resource identity, graph projection, interrupted init phases, exact resume arguments, adopted-registry preservation, pre-existing target preservation, and single initialization-event behavior were exercised
- Dependencies: MK-103, MK-301, DEV-0009 fixed decisions, primary red baseline, test-count correction, graph-null discovery, and all supplementary safety review red cases satisfied
- Acceptance gates: focused performance/platform/trust/init suite, complete regression, compilation, dogfood validate/truth/recover capabilities, 100,000-event benchmark readback, CLI reference, Skill metadata/equivalent validation, append-only planning, no marker/snapshot residue, legacy compatibility, and diff hygiene
- Actual result: PASS before commit; all 34 MK-302 tests passed and the complete 324-test repository suite passed with 0 failures, 0 errors, and 0 skips; compileall passed; dogfood validate returned no errors; truth remained operational with six activation-verified sources, no missing domains, and no unverified source; recovery reported zero work, unknown, or conflicts and exposed Darwin/`fcntl` append-safe plus local-caller-asserted non-cryptographic actor identity; CLI reference and `git diff --check` passed
- Tests: the initial 30-test suite was written before product implementation and produced 4 passes, 15 failures, and 11 errors; ST-3021 passed 6/6, ST-3022 4/4, ST-3023 5/5, ST-3024 4/4, ST-3025 4/4, and the original ST-3026 7/7; four supplementary methods separately captured red before fixes for invalid adopted input marker leakage, generated pre-existing target overwrite, adopted-mode control overwrite, and incomplete/invalid 100,000-event sample acceptance, bringing the final total to 34
- Benchmark readback: the version-1 implementation measured one full run at 1,000 events/489,751 bytes/0.0076 seconds, 10,000/4,917,751/0.0772 seconds, and 100,000/49,377,751/0.8732 seconds with zero chain errors and exact heads; the decision was `retain-full-replay`, `creates_snapshot=false`, below 2.0 seconds and 256 MiB
- Platform/trust readback: core imports without `fcntl`; read-only validate/recover remains available when the backend is absent, while append fails before mutation; live recovery reports schema version 1, platform, backend, supported/append-safe, and next action; actor identity is explicitly local-caller-asserted, cryptographic=false, tamper-evident=true, tamper-proof=false across runtime, product, governance, system, operations, and the 112-line progressively disclosed Skill
- Initialization/resource readback: interruption after control, truth, ledger, or initial event leaves the exact version-1 marker and resumes idempotently with one initialization event; mismatched args, invalid adopted input, and pre-existing generated/adopted targets fail without mutation; adopted registry bytes remain unchanged; resource claim/release/recover retain resource subject plus lease payload across Schema, CLI, replay, recovery, and graph; active undelivered work no longer triggers a derived-graph `None.get` failure
- Remaining issues: official `quick_validate.py` remains unknown because its external Python environment lacks PyYAML; repository metadata tests and the dependency-free equivalent validator pass; immutable implementation anchor is pending; snapshot review remains intentionally deferred unless a future measured 100,000-event sample reaches a fixed threshold and a separate User-approved work item is opened
- Next safe action: commit the MK-302 implementation, rerun all 34 focused tests, all 324 repository tests, the 100,000-event benchmark, and acceptance gates against the exact immutable commit, append DEV-0009 CLOSE with its SHA, then commit and push the close record
