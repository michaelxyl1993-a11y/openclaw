# Product Intel v1.19 多文件批处理汇总

## 输入文件

| 文件 | 识别来源 | 映射置信度 | 字段质量分 | 商品数 | main_push | small_test | hold | reject |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mock_echotik_products.xlsx | echotik | high | 76 | 3 | 0 | 3 | 0 | 0 |
| mock_fastmoss_products.xlsx | fastmoss | high | 79 | 3 | 0 | 2 | 1 | 0 |
| mock_kalodata_products.xlsx | kalodata | high | 83 | 3 | 0 | 2 | 1 | 0 |
| mock_manual_products.xlsx | manual | high | 100 | 3 | 1 | 1 | 1 | 0 |

## 合计

- 输入文件数：4
- 商品总数：12
- 决策分布：main_push 1 / small_test 8 / hold 3 / reject 0
- 重复 product_id 数量：0
- next_action 冲突数量：0
- 错误数量：0

## 下游建议

- 合并后的 `multi_file_all_evidence.json` 可进入 LLM Judge 复核层。
- 合并后的决策表可进入 final ops exporter。
