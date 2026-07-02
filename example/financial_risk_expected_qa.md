# 支付风控示例问答与期望回答

本文档配合 `financial_risk_graph.json` 和 `financial_risk_input.txt` 使用。JSON 是正式构图输入，文本是同一业务事实的自然语言表达；本文件只存放示例问题、影响分析场景和期望回答，不参与构图。

## 普通问答

### 问题 1：Felix Gao 为什么会被判定为高风险？

期望回答：

Felix Gao 的高风险原因来自三类证据。第一，他持有 `wallet_felix`，该钱包是可疑资金路径的起点。第二，他和 Hank Xu 都使用过 `dev_emulator`，也都绑定或使用过 `phone_shared`，存在共享设备和共享手机号风险。第三，`rule_shared_phone_kyc` 会基于共享手机号对 Felix 提高身份风险分，并触发 `dec_manual_review`。

关键证据节点：

- `usr_felix`
- `wallet_felix`
- `dev_emulator`
- `phone_shared`
- `rule_shared_phone_kyc`
- `dec_manual_review`

### 问题 2：Felix 的钱包到 Nova Crypto OTC 的资金路径是什么？

期望回答：

资金路径是：

`wallet_felix -> txn_felix_hank -> acct_hank -> txn_hank_orion -> acct_orion -> mch_nova`

含义是 Felix 快贷钱包先通过 `txn_felix_hank` 把资金转入 Hank 收款账户，随后 Hank 收款账户通过 `txn_hank_orion` 把资金转入 Orion 结算账户，最后资金流向 Nova Crypto OTC。

关键关系：

- `wallet_felix transfers_to txn_felix_hank`
- `txn_felix_hank transfers_to acct_hank`
- `acct_hank transfers_to txn_hank_orion`
- `txn_hank_orion transfers_to acct_orion`
- `acct_orion transfers_to mch_nova`

### 问题 3：AML 资金环模型使用了哪些特征，又影响哪些对象？

期望回答：

`feat_fund_flow_cycle` 和 `feat_mule_cluster_score` 会为 `mdl_aml_ring` 提供输入，因此 AML 资金环模型依赖这两个特征。模型会对 `acct_hank` 和 `biz_orion` 提高风险分，并触发 `dec_manual_review`。

关键关系：

- `feat_fund_flow_cycle provides_to mdl_aml_ring`
- `feat_mule_cluster_score provides_to mdl_aml_ring`
- `mdl_aml_ring scores acct_hank`
- `mdl_aml_ring scores biz_orion`
- `mdl_aml_ring triggers dec_manual_review`

## 影响分析

### 场景 1：如果共享手机号 138001 被判定为误报，会影响什么？

期望回答：

如果 `phone_shared` 被判定为误报，首先会影响 `rule_shared_phone_kyc`，因为共享手机号是该规则的输入。随后会影响规则对 `usr_felix` 和 `usr_hank` 的风险评分，并可能降低由该规则触发的 `dec_manual_review` 数量。若相关审核不再成立，后续的 `act_account_freeze` 和 `report_sar` 也可能减少。

主要影响链路：

- `phone_shared -> rule_shared_phone_kyc`
- `rule_shared_phone_kyc -> usr_felix`
- `rule_shared_phone_kyc -> usr_hank`
- `rule_shared_phone_kyc -> dec_manual_review`
- `dec_manual_review -> act_account_freeze`
- `dec_manual_review -> report_sar`

### 场景 2：如果实时交易流延迟，会影响哪些特征、模型和处置？

期望回答：

如果 `src_transaction_stream` 延迟，直接受影响的是 `feat_fund_flow_cycle` 和 `feat_mule_cluster_score`。这两个特征被 `mdl_aml_ring` 使用，因此模型评分会延迟或不完整，进而影响对 `acct_hank` 和 `biz_orion` 的风险评分。模型触发的 `dec_manual_review` 也会延迟，最终可能影响 `act_account_freeze` 和 `report_sar` 的时效性。

主要影响链路：

- `src_transaction_stream -> feat_fund_flow_cycle`
- `src_transaction_stream -> feat_mule_cluster_score`
- `mdl_aml_ring -> feat_fund_flow_cycle`
- `mdl_aml_ring -> feat_mule_cluster_score`
- `mdl_aml_ring -> acct_hank`
- `mdl_aml_ring -> biz_orion`
- `mdl_aml_ring -> dec_manual_review`
- `dec_manual_review -> act_account_freeze`
- `dec_manual_review -> report_sar`

### 场景 3：如果 Mule 集群特征下线，会影响哪些模型、评分和处置？

期望回答：

如果 `feat_mule_cluster_score` 下线，直接受影响的是 `mdl_aml_ring`，因为该特征为 AML 资金环模型提供输入。模型结果受影响后，会进一步影响对 `acct_hank` 和 `biz_orion` 的评分，也会影响 `dec_manual_review` 的触发。人工审核减少或延迟后，`act_account_freeze` 和 `report_sar` 也可能受到影响。

主要影响链路：

- `feat_mule_cluster_score -> mdl_aml_ring`
- `mdl_aml_ring -> acct_hank`
- `mdl_aml_ring -> biz_orion`
- `mdl_aml_ring -> dec_manual_review`
- `dec_manual_review -> act_account_freeze`
- `dec_manual_review -> report_sar`
