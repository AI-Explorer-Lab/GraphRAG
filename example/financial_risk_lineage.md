# financial_risk_lineage.json 说明

这份 JSON 是一个压缩版金融风控 GraphRAG 示例图谱。它把一个可疑资金流场景拆成身份、账户、设备、交易、数据源、特征、模型、规则、决策和处置动作，方便第一次阅读、导入和调试。

当前规模：

| 指标 | 数量 |
| --- | ---: |
| 实体节点 | 30 |
| 显式业务边 | 30 |
| 固定业务边类型 | 6 |

## transitions 到底是什么

这里最容易误解的一点是：`transitions` 不是一种边名，也不是说所有边都叫 transition。

在这个项目当前的 JSON schema 里：

```json
{
  "entities": {},
  "transitions": []
}
```

`transitions` 只是“边列表”的顶层容器。真正的边类型写在每条边的 `relation` 字段里：

```json
{
  "id": "own_001",
  "source": "usr_felix_006",
  "target": "acct_felix_shadow",
  "relation": "owns",
  "properties": {}
}
```

也就是说，逻辑上应该这样理解：

```text
usr_felix_006 --owns--> acct_felix_shadow
```

而不是：

```text
usr_felix_006 --transitions--> acct_felix_shadow
```

之所以保留顶层字段名 `transitions`，是因为后端 parser/API 当前按这个字段读取边列表。如果未来要让命名更直观，可以把顶层字段迁移成 `edges`，但不建议把 JSON 改成多个顶层数组，例如：

```json
{
  "owns": [],
  "uses": [],
  "scores": []
}
```

那样会让导入、LLM 抽取、校验和前端渲染都更复杂。更推荐的结构是：

```json
{
  "transitions": [
    { "relation": "owns" },
    { "relation": "uses" },
    { "relation": "scores" }
  ]
}
```

## 固定关系类型

这个 example 只使用 6 类业务边。后端 parser 会校验 `relation`，不支持随便写一个新的自由关系名。

| relation | 含义 | 示例 |
| --- | --- | --- |
| `owns` | 主体拥有账户、钱包、商户等对象。 | `usr_felix_006 -> wallet_felix_fastloan` |
| `uses` | 主体使用设备、IP、手机号等信号。 | `usr_felix_006 -> dev_emulator_01` |
| `transfers_to` | 资金从一个节点流向另一个节点。 | `wallet_felix_fastloan -> txn_transfer_felix_hank_004` |
| `provides_to` | 数据、事件或特征向下游提供输入。 | `feat_fund_flow_cycle -> mdl_aml_graph_ring` |
| `scores` | 模型或规则对对象打分。 | `mdl_aml_graph_ring -> acct_hank_receiver` |
| `triggers` | 模型、规则或决策触发后续动作。 | `dec_manual_review -> act_account_freeze` |

如果以后要加入 `depends_on`，建议把它作为第 7 类固定关系加入 schema，而不是在数据里临时自由发挥。

## 顶层结构

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `entities` | object | 所有业务节点。key 是实体 ID，value 是实体详情。 |
| `transitions` | array | 所有显式业务边。每条边通过 `source`、`target`、`relation` 表达有向关系。 |

## 实体节点结构

每个实体大致长这样：

```json
"usr_felix_006": {
  "id": "usr_felix_006",
  "name": "Felix Gao",
  "properties": {
    "type": "person",
    "domain": "identity",
    "owner": "identity_team",
    "risk_level": "high",
    "region": "CN",
    "entity_class": "synthetic_identity",
    "tags": ["synthetic_identity", "shared_contact"]
  },
  "description": "High-risk user suspected of synthetic identity behavior and shared device usage."
}
```

| 字段 | 含义 |
| --- | --- |
| `id` | 节点唯一 ID。边里的 `source` / `target` 会引用它。 |
| `name` | 人类可读名称。 |
| `properties` | 结构化属性，用于检索、过滤、问答和 UI 展示。 |
| `description` | 自然语言解释，用于 RAG 证据和人工理解。 |
| `children` | 可选。用于表达层级归属，导入后会自动生成内部 `has` 关系。 |

### properties 字段

| 字段 | 含义 |
| --- | --- |
| `type` | 节点大类，例如 `person`、`payment_account`、`model`。 |
| `domain` | 所属业务域，例如 `identity`、`accounts`、`models`。 |
| `owner` | 负责团队或系统。 |
| `risk_level` | 风险等级：`high`、`medium`、`low`。 |
| `region` | 地域。 |
| `entity_class` | 更细的业务画像。 |
| `tags` | 补充标签，用于检索和展示。 |

## 节点分层

这个小图包含一个根节点、9 个业务域节点和 20 个具体业务节点。

| 节点 | 含义 | children |
| --- | --- | --- |
| `fr_root` | 金融风控根节点 | 9 个 domain |
| `dom_identity` | 用户和企业主体 | `usr_felix_006`、`usr_hank_008`、`biz_orion_trade` |
| `dom_accounts` | 账户、钱包、结算账户 | `acct_felix_shadow`、`wallet_felix_fastloan`、`acct_hank_receiver`、`acct_orion_settle` |
| `dom_devices` | 设备和网络信号 | `dev_emulator_01`、`ip_proxy_pool_a`、`phone_shared_138001` |
| `dom_merchants` | 商户 | `mch_nova_crypto_otc` |
| `dom_transactions` | 资金事件 | `txn_transfer_felix_hank_004`、`txn_micro_transfer_ring_012` |
| `dom_data_sources` | 数据源 | `src_transaction_stream` |
| `dom_features` | 特征 | `feat_fund_flow_cycle`、`feat_mule_cluster_score` |
| `dom_models` | 模型和规则 | `mdl_aml_graph_ring`、`rule_shared_phone_kyc` |
| `dom_decisions` | 决策和处置 | `dec_manual_review`、`act_account_freeze` |

## 业务故事

这个小图表达的是一个紧凑的可疑资金链。

Felix Gao 是高风险用户，拥有影子账户和快贷钱包。Hank Xu 是高风险收款人，拥有收款账户。两人共享同一个安卓模拟器集群和同一个 KYC 手机号，Felix 还使用过代理 IP 池。

资金流从 Felix 的快贷钱包开始：

```text
wallet_felix_fastloan
  --transfers_to--> txn_transfer_felix_hank_004
  --transfers_to--> acct_hank_receiver
  --transfers_to--> txn_micro_transfer_ring_012
  --transfers_to--> acct_orion_settle
  --transfers_to--> mch_nova_crypto_otc
```

这条链路表示：Felix 的资金先转给 Hank，Hank 再通过小额拆分转到 Orion 的结算账户，最后进入虚拟资产 OTC 商户。

## 数据源、特征、模型和规则

实时交易流 `src_transaction_stream` 生成两个核心特征：

```text
src_transaction_stream --provides_to--> feat_fund_flow_cycle
src_transaction_stream --provides_to--> feat_mule_cluster_score
```

交易事件也会进入特征：

```text
txn_transfer_felix_hank_004 --provides_to--> feat_fund_flow_cycle
txn_micro_transfer_ring_012 --provides_to--> feat_mule_cluster_score
```

两个特征进入 AML 图环模型：

```text
feat_fund_flow_cycle --provides_to--> mdl_aml_graph_ring
feat_mule_cluster_score --provides_to--> mdl_aml_graph_ring
```

共享手机号进入 KYC 规则：

```text
phone_shared_138001 --provides_to--> rule_shared_phone_kyc
```

## 模型评分和触发动作

AML 图环模型会对可疑交易、账户和企业主体打分：

```text
mdl_aml_graph_ring --scores--> txn_micro_transfer_ring_012
mdl_aml_graph_ring --scores--> acct_hank_receiver
mdl_aml_graph_ring --scores--> biz_orion_trade
```

共享手机号规则会对 Felix 和 Hank 打分：

```text
rule_shared_phone_kyc --scores--> usr_felix_006
rule_shared_phone_kyc --scores--> usr_hank_008
```

模型和规则都会触发人工审核，人工审核确认后触发账户冻结：

```text
mdl_aml_graph_ring --triggers--> dec_manual_review
rule_shared_phone_kyc --triggers--> dec_manual_review
dec_manual_review --triggers--> act_account_freeze
```

## 边属性

不同 `relation` 的 `properties` 含义不同：

| relation | 常见属性 | 含义 |
| --- | --- | --- |
| `owns` | `confidence`、`evidence`、`effective_date` | 拥有关系的置信度、证据和生效时间。 |
| `uses` | `first_seen`、`last_seen`、`evidence` | 使用关系的首次/最近观测时间和证据。 |
| `transfers_to` | `amount_band`、`currency`、`channel` | 金额区间、币种、资金渠道。 |
| `provides_to` | `freshness`、`sla`、`aggregation_window`、`feature_store`、`feature_version` | 数据或特征输入的质量、时效和版本信息。 |
| `scores` | `score_band`、`threshold_version` | 分数区间和阈值版本。 |
| `triggers` | `severity`、`trigger_condition` | 触发严重程度和触发条件。 |

## 导入后会出现的派生关系

原始 JSON 只手写业务边。系统导入后还会自动生成一些内部关系，例如：

| 内部关系 | 来源 | 用途 |
| --- | --- | --- |
| `has` | `children` | 表达父子层级。 |
| `has_attribute` | `properties` 展开 | 让属性可检索、可解释。 |
| `member_of`、`has_keyword`、`represents_*` | 社区/关键词构建 | 用于子图解释和 GraphRAG 检索。 |

所以前端子图里看到的节点数可能会比 JSON 里的 30 个业务节点更多，这是正常的。

## 推荐测试问题

导入后可以问：

1. `Felix 为什么是高风险用户？`
2. `Felix 和 Hank 之间有哪些共享设备或手机号？`
3. `从 wallet_felix_fastloan 到 mch_nova_crypto_otc 的资金路径是什么？`
4. `哪些特征进入了 AML graph ring model？`
5. `如果 phone_shared_138001 是误报，会影响哪些规则、评分和决策？`
6. `如果 txn_micro_transfer_ring_012 被标记为高风险，会影响哪些模型和处置动作？`

## 修改这个 JSON 时的注意事项

1. `entities` 的 key 必须和内部 `id` 一致。
2. `transitions[*].source` 和 `transitions[*].target` 必须引用已有实体。
3. 新增业务边时，`relation` 只使用固定枚举。
4. 新增具体实体时，尽量补齐 `type`、`domain`、`owner`、`risk_level`、`entity_class` 和 `tags`。
5. 资金流建议通过 `txn_` 事件节点表达，不要简单地账户直连账户。
6. 如果要扩展 schema，例如加入 `depends_on`，应先更新后端允许的关系枚举和测试，再更新示例数据。
