# Product Intel v1.23 Feishu Multi-file LLM Ops Summary

- 商品总数：8
- evidence：product_intel/output_multi_file_from_feishu/multi_file_all_evidence.json
- real_llm_requested：true
- real_llm_enabled：true
- real_llm_called_count：8
- success_count：8
- error_count：0
- LLM review 分布：{"agree": 8}
- confidence 分布：{"high": 3, "medium": 5}
- 规则决策分布：{"main_push": 0, "small_test": 5, "hold": 3, "reject": 0}
- final priority 分布：{"P1_small_test": 5, "P2_hold": 3}
- challenge_count：0
- ready_for_feishu_message：true

## 输出文件

- judge_results: product_intel/output_feishu_llm_ops/all_evidence_real_llm_judge_results.json
- prompt_samples: product_intel/output_feishu_llm_ops/all_evidence_real_llm_judge_prompt_samples.json
- run_summary_json: product_intel/output_feishu_llm_ops/real_llm_judge_run_summary.json
- run_summary_md: product_intel/output_feishu_llm_ops/real_llm_judge_run_summary.md
- merge_merged_json: product_intel/output_feishu_llm_ops/all_evidence_with_real_llm_review.json
- merge_merged_csv: product_intel/output_feishu_llm_ops/all_evidence_with_real_llm_review.csv
- merge_summary_json: product_intel/output_feishu_llm_ops/real_llm_review_ops_summary.json
- merge_summary_md: product_intel/output_feishu_llm_ops/real_llm_review_ops_summary.md
- final_table_csv: product_intel/output_feishu_llm_ops/final_ops_decision_table.csv
- final_table_md: product_intel/output_feishu_llm_ops/final_ops_decision_table.md
- action_summary_json: product_intel/output_feishu_llm_ops/final_ops_action_summary.json
- action_summary_md: product_intel/output_feishu_llm_ops/final_ops_action_summary.md
- challenge_csv: product_intel/output_feishu_llm_ops/final_challenge_products.csv
- review_note_md: product_intel/output_feishu_llm_ops/final_review_note.md
- summary_json: product_intel/output_feishu_llm_ops/feishu_multi_file_llm_ops_summary.json
- summary_md: product_intel/output_feishu_llm_ops/feishu_multi_file_llm_ops_summary.md

## 下一步

`python3 -m product_intel.feishu_clean_message_pack --handoff-message product_intel/output_next_round/feishu_ops_handoff_message.md --final-summary product_intel/output_feishu_llm_ops/final_ops_action_summary.json --final-table product_intel/output_feishu_llm_ops/final_ops_decision_table.csv --output-dir product_intel/output_feishu_llm_ops`
