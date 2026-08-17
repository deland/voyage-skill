# 通用项目管理 Skill 开发方案建议

- 状态：草案（design，非权威）
- 日期：2026-08-14
- 目标：基于 `graph-engineering` skill 的思想与方法，抽象出一个**领域无关的通用项目管理 skill**。
- 参考真源：`docs/research/graph-engineering.md`（R167/R168）、当前 `voyage-skill` 全套实现（SKILL.md / src / schemas / docs）。

---

## 1. 先把两个东西说清楚

阅读后有一个关键判断需要先讲明白，它决定了整个方案的走向：

**`graph-engineering.md` 是"第一代原始形态"，而当前仓库里的 `voyage-skill` 已经是它的"第一次通用化提炼"。** 换句话说，你要做的"通用项目管理 skill"不是从零开始，而是 `voyage-skill` 的**再一次抽象**——把它从"多智能体软件项目"这个具体领域，进一步剥离到"任意可验证协作项目"。

三者的关系可以这样看：

| 层级 | 形态 | 领域绑定 | 特征 |
| --- | --- | --- | --- |
| 第 0 代 | `graph-engineering.md` | 强绑定短剧平台 | 硬编码路径、Kimi/Playwright/8000 端口、worktree、发针/合流黑话 |
| 第 1 代 | `voyage-skill`（现状） | 绑定"多智能体软件工程" | 抽象出四层回路/账本/锚点/租约，但仍假设 repo + git + 交付锚点 + 端口探测 |
| 第 2 代 | **通用 PM skill（本方案）** | 领域无关 | 把"软件交付"降为一个可插拔的 domain profile，核心只留协作治理原语 |

所以本方案的实质是：**识别 `graph-engineering` 里哪些是"普适的协作治理机制"、哪些是"短剧/软件领域的具体投影"，然后把前者固化为内核、把后者变成可替换的插件。**

---

## 2. 从 graph-engineering 提炼出的可迁移思想

`graph-engineering.md` 虽然满纸黑话，但骨架里有 7 条与领域无关的普适原则，这正是通用 PM skill 的地基。

**其一，skill 只是稳定入口，永不承载状态。** 原文"本 skill 是稳定入口层，真身在集成 worktree 的 docs——冲突一律以 docs 为准"。这是最核心的思想：把"入口/索引"与"真源/状态"彻底分离，skill 文件永远短小稳定，真实状态活在版本化文档 + 账本里。

**其二，分层真源与指针化。** 原文的"四层真源"（规矩层/结构层/操作层/协作层）本质是：不同稳定度的知识分层存放，skill 里只放指针不放内容。通用化后就是 `truth-registry` + 分域文档。

**其三，状态只认命令不认记忆。** 原文"状态只认命令不认记忆""8000 三元组读回全绿才算完成"。这是"观测证据 > 声明 > 计划"的三级事实分层——可迁移到任何领域：真实状态必须由可复核的证据（命令输出/读回/外部结果）证明。

**其四，资源互斥与发针前验退。** 原文"E2E 全局互斥""发针前验退""资源注册簿——持有人一律现查不登记"。抽象后就是：共享资源（文件/账号/端口/环境/会话/人力/预算）必须先注册、先探活、后占用，登记只是策略不是证据。

**其五，异步动作钉死不可变引用。** 原文"合流锚 tag/commit 禁分支名""同一病根的三个面"。抽象后：任何异步的评审/验收/合并/交付都必须引用一个不可变锚点，而非会漂移的引用。

**其六，门禁与完整计数。** 原文"术语门禁+plan-freshness""禁止管道 grep 接 commit（退出码会被吃）"。抽象后：验收门必须记录完整计数（通过/失败/跳过/未知），失败不能被过滤文本掩盖。

**其七，自进化与代际假设。** 原文"prompt→context→harness→loop→graph，三年五代——本体系必须假设自己会被下一代替掉"。抽象后：机制自身要有"提议→审批→应用→验证→生效→退役"的规则生命周期，允许受控演化并主动淘汰过时规则。

这 7 条，`voyage-skill` 已经全部实现了（对应 SKILL.md 的 Discover/Recover/Operate/Govern 四段、`core.py` 的 replay 状态机、`graph.md` 的 10 条不变量）。**通用 PM skill 要做的是保留这 7 条内核，剥掉软件领域的具体假设。**

---

## 3. 需要"通用化"改造的软件领域假设

当前 `voyage-skill` 里以下东西是"软件工程投影"，通用 PM skill 必须把它们抽象或插件化：

| 现状（软件专用） | 通用化后 | 说明 |
| --- | --- | --- |
| immutable anchor = git tag/commit hash | 抽象为"内容哈希锚点" | 交付物可以是文档、设计稿、视频、合同——锚点 = 交付内容的 SHA-256 或外部不可变引用（如网盘版本号、S3 versionId） |
| `probe_port()` 真 socket 探测 | 抽象为"资源探针接口" | 端口只是一种 stateful 资源探针；通用层需支持自定义探针（如"会议室是否被占""API 配额是否耗尽""某人是否在假"） |
| 资源类型 file/account/port/environment/session/window/quota | 保留为默认集，允许扩展 | 通用 PM 还需要 person（人力）、budget（预算）、slot（时间档期）等类型 |
| 交付=代码交付、门=测试门 | 交付=任意可交付物、门=任意验收检查 | 门的证据类型从"命令输出/健康检查"扩展到"人工签核/客户确认/指标读回" |
| 单 repo 单机边界 | 保留为默认，接口可换协调后端 | v0.1 明确非目标是分布式锁，通用层同样先守单协调域，但把"协调后端"做成接口 |

**结论：通用化 = 内核不动，把"软件假设"下沉为一个 `domain profile`（领域画像）配置。**

---

## 4. 推荐架构：三层可插拔

```
┌─────────────────────────────────────────────┐
│  L3  Domain Profiles（领域画像 · 可插拔）        │
│   software / content-production / research /  │
│   marketing-campaign / ops ...                │
│   —— 定义：资源类型、探针、锚点种类、门模板、风险映射  │
├─────────────────────────────────────────────┤
│  L2  Core Governance Kernel（治理内核 · 不动）   │
│   四回路 / 账本 replay / 锚点 / 租约 / 门 /       │
│   规则生命周期 / 三级事实分层 / 升级授权           │
├─────────────────────────────────────────────┤
│  L1  Skill Entry（入口 · 稳定短小）              │
│   Discover → Recover → Operate → Govern       │
└─────────────────────────────────────────────┘
```

L1 和 L2 直接复用 `voyage-skill` 现有资产（几乎不改）。**真正的新增工作量在 L3——把领域相关的东西抽出来做成 profile。** 这样一份内核可以服务软件、内容生产（正好是短剧平台）、市场活动、研究项目等多个领域。

---

## 5. Domain Profile 的形态（新增的核心产物）

建议新增 `schemas/domain-profile.schema.json` 与 `profiles/<name>.json`。一个 profile 声明式地描述某领域如何映射到内核原语：

```jsonc
{
  "profile_id": "content-production",
  "resource_types": {
    "person": { "mode": "exclusive", "probe": "roster-check" },
    "render-farm": { "mode": "serialized", "probe": "queue-depth" },
    "review-slot": { "mode": "exclusive", "probe": "calendar" }
  },
  "anchor_kinds": ["content-hash", "asset-version-id", "signed-approval"],
  "gate_templates": [
    { "id": "script-review",  "evidence": "human-signoff" },
    { "id": "compliance",     "evidence": "checklist-readback" },
    { "id": "client-accept",  "evidence": "real-user-outcome" }
  ],
  "risk_map": {
    "publish-to-public": "strict",
    "internal-draft": "light"
  }
}
```

内核读取 profile 后，`register_resource` / `gate.recorded` / `work.authorized` 的校验逻辑完全复用，只是校验时以 profile 的声明为准。**这一步是把"发针前验退""E2E 互斥"这类领域规则，从硬编码变成数据驱动。**

---

## 6. 具体开发计划（按 voyage-skill 自己的方法论推进）

既然要基于这套思想开发，最有说服力的做法是**用 voyage-skill 本身来管理这次开发**（吃自己的狗粮 / dogfooding）。分三阶段：

**阶段一 · 内核领域解耦（1 个 work item，strict 风险因涉及核心状态机）。** 把 `core.py` 里硬编码的 `ALLOWED_RESOURCE_TYPES`、`probe_port`、锚点校验抽成"由 profile 注入"。产出：`domain-profile.schema.json` + profile 加载逻辑 + 内核默认 profile（等价于当前软件行为，保证零回归）。验收门：现有全部 tests 通过（不变量不破）。

**阶段二 · 编写第二个 domain profile 验证抽象是否成立（1 个 work item，standard）。** 用你的短剧平台场景写一个 `content-production` profile，把 graph-engineering 里的"发针前验退""E2E 全局互斥""8000 三元组读回"翻译成 profile 的 gate/resource 声明。这一步是抽象是否成功的试金石——如果短剧场景能纯靠 profile 表达、不用改内核，说明通用化成立。

**阶段三 · 入口与文档收敛（1 个 work item，light）。** 更新 SKILL.md，让 Discover 阶段增加"读取 active domain profile"；补 `docs/product/contract.md` 的通用定位；把 `profiles/` 目录纳入 truth-registry 作为一类新真源。

**验收标准（对应 graph-engineering 的"三元组读回"思想）：** 一份内核 + 两份互不相同的 profile（software、content-production）都能跑通"初始化→创建工作→授权→交付→独立质检→验收"完整旅程，且现有测试零回归。

---

## 7. 关键设计取舍与风险

**取舍一：不要重造 DevSwarm 式固定角色。** graph-engineering 和 voyage-skill 都刻意避免"固定永久职位"，改用"按工作范围绑定权限的四回路"。通用 PM skill 极易被诱惑加"产品经理/开发/测试"这类角色——**必须抵制**，否则又退回领域绑定。回路是 scoped permission，不是 job title，这是整套体系的精髓，务必守住。

**取舍二：先守单协调域。** 通用不等于分布式。沿用 voyage-skill 的"单 repo 单机"边界，把"协调后端"做成接口但不实现分布式锁，避免 v0.1 失控。

**取舍三：profile 不能偷偷放权。** 领域 profile 只能"声明领域数据"，绝不能覆盖内核不变量（如"执行者不能自审""失败门禁止验收"）。schema 校验时要显式禁止 profile 声明任何降低安全边界的字段。

**风险：过度抽象导致空转。** 应对方式就是阶段二——用真实的短剧场景反向验证，抽象必须服务于"少写代码、多复用"，一旦发现某领域必须改内核才能表达，就说明抽象边界画错了，回退重画。

---

## 8. 直接结论与建议

不建议从零新建一个 skill，而是**把 `voyage-skill` 提升为通用内核 + domain profile 架构**，理由是它已经把 graph-engineering 的 7 条普适思想全部沉淀为可运行、有测试、确定性的实现，重写只会丢失这些不变量。

最小可行路径是三个 work item，按 voyage-skill 自身方法论推进（strict → standard → light），核心新增物只有一个：**domain profile 机制**，它把"软件专用假设"下沉为可插拔配置，从而让同一套治理内核既能管短剧平台的内容生产，也能管软件工程、市场活动、研究项目。

成功的唯一判据：短剧平台（content-production profile）与软件工程（software profile）两个截然不同的领域，都只靠写 profile、不改内核，就能跑通完整的"创建→授权→交付→独立质检→验收"旅程，且现有测试零回归。这一条同时呼应了 graph-engineering 最深的那句——"本体系必须假设自己会被下一代替掉"：把领域从内核里剥离出去，正是让内核活得更久、能被更多下一代场景复用的方式。
