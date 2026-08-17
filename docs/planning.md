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
