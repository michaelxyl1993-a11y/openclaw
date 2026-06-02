# Product Intel CSV Profile

## Source Detection

- source_detected: manual
- source_platform_value: manual
- source_platform_source: explicit
- detected_file_type: xlsx
- detected_sheet_name: 手工合并表
- row_count: 3
- field_quality_score: 100
- mapping_confidence: high

## Input Columns

商品编号, 商品名, 叶子类目, 售价, 销量, 销售额, 佣金率, 商品链接, 商家名称, 数据来源, 近7日增长, 近30日增长, 带货视频数, 带货达人数, 商品评分, 评论数

## Field Mapping

| internal field | input column |
| --- | --- |
| product_id | 商品编号 |
| product_name | 商品名 |
| category | 叶子类目 |
| price | 售价 |
| sold_count | 销量 |
| gmv | 销售额 |
| commission_rate | 佣金率 |
| product_url | 商品链接 |
| shop_name | 商家名称 |
| source_platform | 数据来源 |
| growth_7d | 近7日增长 |
| growth_30d | 近30日增长 |
| related_video_count | 带货视频数 |
| related_influencer_count | 带货达人数 |
| rating | 商品评分 |
| review_count | 评论数 |

## Missing Fields

- missing_fields: (none)
- required: (none)
- optional: (none)
- unmapped_columns: (none)
- duplicate_columns: (none)

## Sample Values

- product_name: 手工收纳盒, 手工宠物碗, 手工桌面风扇
- price: 11.9, 14.9, 17.9
- sold_count: 350, 280, 620

## Warnings

(none)
