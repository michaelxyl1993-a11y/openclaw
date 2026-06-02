# Product Intel CSV Profile

## Source Detection

- source_detected: kalodata
- source_platform_value: kalodata
- source_platform_source: inferred
- detected_file_type: xlsx
- detected_sheet_name: KaLoData Export
- row_count: 3
- field_quality_score: 83
- mapping_confidence: high

## Input Columns

KaLoData Product ID, product_title, category, price, 30日销量, 30日GMV, commission_rate, merchant_name, 相关达人数, score, reviews

## Field Mapping

| internal field | input column |
| --- | --- |
| product_id | KaLoData Product ID |
| product_name | product_title |
| category | category |
| price | price |
| sold_count | 30日销量 |
| gmv | 30日GMV |
| commission_rate | commission_rate |
| product_url | (missing) |
| shop_name | merchant_name |
| source_platform | (inferred from source_detected: kalodata) |
| growth_7d | (missing) |
| growth_30d | (missing) |
| related_video_count | (missing) |
| related_influencer_count | 相关达人数 |
| rating | score |
| review_count | reviews |

## Missing Fields

- missing_fields: product_url, growth_7d, growth_30d, related_video_count
- required: (none)
- optional: product_url, growth_7d, growth_30d, related_video_count
- unmapped_columns: (none)
- duplicate_columns: (none)

## Sample Values

- product_name: KaLoData Travel Cup, KaLoData Phone Stand, KaLoData Makeup Bag
- price: 10.9, 7.9, 9.9
- sold_count: 680, 760, 440

## Warnings

- 缺少 product_url：不影响初筛，但后续无法直接跳转商品链接
- 缺少 growth_30d / related_video_count / related_influencer_count：趋势/内容热度证据不足
