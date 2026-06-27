# Lineage JSON schema

这个 schema 用来描述支付风控调查中的 lineage 图：谁拥有或使用哪些账户、钱包、设备和手机号，资金如何流动，交易和数据源如何形成特征，模型和规则如何评分，最后如何触发人工审核、账户冻结和 SAR 可疑交易报告。

## 顶层字段

- `entities`: 实体字典，key 是实体 id，value 是实体详情。实体 id 使用稳定的 ASCII snake_case，便于接口、检索和图数据库写入。
- `transitions`: 方向关系列表，表示实体之间的业务、资金、数据或处置流向。
- `has_relations`: 可选的包含关系列表。当前示例主要通过实体的 `children` 表达层级；如果输入里显式给出父子关系，也可以把它们放在这里。

## entity 字段

- `id`: 实体唯一 id，必须和 `entities` 字典里的 key 一致。
- `name`: 前端展示名。中文输入应保留中文展示名，不应把可见名称翻译成英文。
- `description`: 对实体业务含义的简短说明。
- `children`: 子实体 id 列表，用于表达分组或层级。例如根节点可以包含“主体与账户”“资金流”“风险信号”“模型规则与处置”等领域节点。
- `properties`: 实体属性。常用字段包括：
  - `type`: 实体类型，例如 `user`、`business`、`wallet`、`account`、`settlement_account`、`device`、`phone`、`merchant`、`transaction`、`data_source`、`feature`、`model`、`rule`、`decision`、`action`、`report`、`domain`。
  - `risk_level`: 风险等级，例如 `high`、`medium`、`low`、`unknown`。
  - `domain`: 所属业务域，例如主体账户、资金流、风险信号、模型规则与处置。
  - `tags`: 额外标签，用于保留业务线索，如共享设备、KYC、mule cluster、SAR 等。

## transition 字段

- `id`: 方向关系唯一 id。
- `source`: 起点实体 id，必须存在于 `entities`。
- `target`: 终点实体 id，必须存在于 `entities`。
- `relation`: 关系类型。当前支持：
  - `owns`: 主体拥有账户、钱包或结算账户。
  - `uses`: 主体使用设备、手机号或其他工具。
  - `transfers_to`: 资金或交易路径从一个节点流向另一个节点。
  - `provides_to`: 数据、交易、设备或手机号信号被提供给特征、模型或规则。
  - `scores`: 模型或规则对主体、账户或企业进行风险评分。
  - `triggers`: 模型、规则、决策触发后续处置。
- `properties`: 关系属性，通常包含 `description`，用于说明这条边的业务依据。

## 与当前示例的对应关系

- 主体与账户：用户 Felix Gao 及其钱包、用户 Hank Xu 及其收款账户、企业 Orion Trading Ltd 及其结算账户，以及资金流向末端的 Nova Crypto OTC。
- 风险信号：Android 模拟器设备、共享手机号 138001、实时交易流。
- 特征与规则：资金循环特征、Mule 集群特征、共享手机号 KYC 规则。
- 模型与处置：AML 资金环模型、人工审核队列、账户冻结动作、SAR 可疑交易报告。

这个 schema 的约束重点是：id 稳定、可见文本保留输入语言、关系类型有限且语义清晰、所有边必须引用已存在实体。
