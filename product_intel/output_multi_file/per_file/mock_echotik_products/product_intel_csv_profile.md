# Product Intel CSV Profile

## Source Detection

- source_detected: echotik
- source_platform_value: echotik
- source_platform_source: inferred
- detected_file_type: xlsx
- detected_sheet_name: EchoTik Export
- row_count: 3
- field_quality_score: 76
- mapping_confidence: high

## Input Columns

EchoTik商品ID, 商品名称, 商品类目, 当前售价, 近7天销量, 成交额, 达人佣金率, 店铺名, 近7天增长

## Field Mapping

| internal field | input column |
| --- | --- |
| product_id | EchoTik商品ID |
| product_name | 商品名称 |
| category | 商品类目 |
| price | 当前售价 |
| sold_count | 近7天销量 |
| gmv | 成交额 |
| commission_rate | 达人佣金率 |
| product_url | (missing) |
| shop_name | 店铺名 |
| source_platform | (inferred from source_detected: echotik) |
| growth_7d | 近7天增长 |
| growth_30d | (missing) |
| related_video_count | (missing) |
| related_influencer_count | (missing) |
| rating | (missing) |
| review_count | (missing) |

## Missing Fields

- missing_fields: product_url, growth_30d, related_video_count, related_influencer_count, rating, review_count
- required: (none)
- optional: product_url, growth_30d, related_video_count, related_influencer_count, rating, review_count
- unmapped_columns: (none)
- duplicate_columns: (none)

## Sample Values

- product_name: Echo Pet Brush, Echo Storage Bag, Echo Mini Fan
- price: 12.9, 8.5, 16.8
- sold_count: 820, 430, 1200

## Warnings

- 缺少 product_url：不影响初筛，但后续无法直接跳转商品链接
- 缺少 rating/review_count：商家质量和用户反馈证据不足
- 缺少 growth_30d / related_video_count / related_influencer_count：趋势/内容热度证据不足
