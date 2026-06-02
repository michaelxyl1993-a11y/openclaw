# Product Intel 选品虾｜最终运营交付

## 1. 本轮总览

- 商品总数：12
- main_push：0
- small_test：8
- hold：3
- human_review_first：1
- LLM agree：11
- LLM challenge：1
- high priority review：1

## 2. 今日可执行

- echo-1｜Echo Pet Brush｜small_test｜P1_small_test
- echo-2｜Echo Storage Bag｜small_test｜P1_small_test
- echo-3｜Echo Mini Fan｜small_test｜P1_small_test
- fm-1｜FastMoss Cat Bowl｜small_test｜P1_small_test
- fm-2｜FastMoss Desk Lamp｜small_test｜P1_small_test
- kalo-1｜KaLoData Travel Cup｜small_test｜P1_small_test
- kalo-3｜KaLoData Makeup Bag｜small_test｜P1_small_test
- manual-1｜手工收纳盒｜small_test｜P1_small_test

## 3. 必须人工复核

- manual-3｜手工桌面风扇｜human_review_first｜P0_review
- manual-3：规则建议 main_push，但 LLM Judge challenge，需人工复核后再放大

## 4. 暂缓补证

- fm-3｜FastMoss Cable Set｜hold_for_evidence｜P2_hold
- kalo-2｜KaLoData Phone Stand｜hold_for_evidence｜P2_hold
- manual-2｜手工宠物碗｜hold_for_evidence｜P2_hold

## 5. 附件清单

- product_intel/output_next_round/final_ops_decision_table.csv
- product_intel/output_next_round/final_ops_decision_table.md
- product_intel/output_next_round/final_ops_action_summary.json
- product_intel/output_next_round/final_ops_action_summary.md
- product_intel/output_next_round/final_challenge_products.csv
- product_intel/output_next_round/final_review_note.md

## Feishu Message Send Mock Preview

- 本次为 mock，不会发送真实飞书消息。
- 不会调用真实飞书消息 API。
- real_file_token_available：false
- using_mock_tokens_for_preview：true

### 附件 Tokens

- final_ops_decision_table.csv：mock_file_token_e5feb3f55d4c169c7eee（mock_token_fallback）
- final_ops_action_summary.json：mock_file_token_9a46991eeeeec170c6a2（mock_token_fallback）
- feishu_ops_handoff_message.md：mock_file_token_d62b6ae3132239bd3e95（mock_token_fallback）
- feishu_ops_handoff_manifest.json：mock_file_token_db554dbcd97cd3a9ec0c（mock_token_fallback）
- feishu_ops_handoff_brief.json：mock_file_token_79566b4f945840876b94（mock_token_fallback）
- feishu_ops_handoff_checklist.md：mock_file_token_97d14ff421b86f3a0ac8（mock_token_fallback）
