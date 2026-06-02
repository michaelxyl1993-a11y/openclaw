# Product Intel CSV Profile

## Source Detection

- source_detected: fastmoss
- source_platform_value: fastmoss
- source_platform_source: inferred
- detected_file_type: xlsx
- detected_sheet_name: FastMoss Export
- row_count: 3
- field_quality_score: 79
- mapping_confidence: high

## Input Columns

FastMoss商品ID, title, leaf_category, sale_price, sales, 近7日GMV, commission %, TikTok商品链接, seller_name, 关联视频数

## Field Mapping

| internal field | input column |
| --- | --- |
| product_id | FastMoss商品ID |
| product_name | title |
| category | leaf_category |
| price | sale_price |
| sold_count | sales |
| gmv | 近7日GMV |
| commission_rate | commission % |
| product_url | TikTok商品链接 |
| shop_name | seller_name |
| source_platform | (inferred from source_detected: fastmoss) |
| growth_7d | (missing) |
| growth_30d | (missing) |
| related_video_count | 关联视频数 |
| related_influencer_count | (missing) |
| rating | (missing) |
| review_count | (missing) |

## Missing Fields

- missing_fields: growth_7d, growth_30d, related_influencer_count, rating, review_count
- required: (none)
- optional: growth_7d, growth_30d, related_influencer_count, rating, review_count
- unmapped_columns: (none)
- duplicate_columns: (none)

## Sample Values

- product_name: FastMoss Cat Bowl, FastMoss Desk Lamp, FastMoss Cable Set
- price: 15.9, 19.9, 6.9
- sold_count: 510, 390, 920

## Warnings

- 缺少 rating/review_count：商家质量和用户反馈证据不足
- 缺少 growth_30d / related_video_count / related_influencer_count：趋势/内容热度证据不足
