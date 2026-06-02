# Product Intel v1.6 Codex Review

## 1. 本次运行结论

- 复核结论：通过。
- 四个来源已重新运行，运营汇总已重新生成。共 12 个商品，`next_action` 与 `decision` 全部一致。
- 当前版本适合提交 v1.6，也适合进入飞书真实运营测试。建议先按 P0 / P1 / P2 分层执行，不把 P1 和 P2 直接放大。
- CSV 使用 UTF-8 BOM 以兼容 Excel。通过 `utf-8-sig` 读取后列名为 `source_platform`，未出现 `\ufeffsource_platform` 业务读取问题。

## 2. 数据源识别情况

| 来源 | 商品数 | source_detected 是否正确 | mapping_confidence | field_quality_score | 主要缺失字段 |
| --- | ---: | --- | --- | ---: | --- |
| EchoTik | 3 | 正确：`echotik` | high | 76 | `product_url`, `growth_30d`, `related_video_count`, `related_influencer_count`, `rating`, `review_count` |
| FastMoss | 3 | 正确：`fastmoss` | high | 79 | `growth_7d`, `growth_30d`, `related_influencer_count`, `rating`, `review_count` |
| KaLoData | 3 | 正确：`kalodata` | high | 83 | `product_url`, `growth_7d`, `growth_30d`, `related_video_count` |
| Manual | 3 | 正确：`manual` | high | 100 | 无 |

结论：字段映射置信度已与证据完整度解耦。EchoTik 和 FastMoss 的核心字段可可靠映射，因此为 `high`；可选证据缺失仍体现在较低的质量分中。

## 3. 决策分布复核

| 决策 | 数量 | 运营含义 | 是否合理 |
| --- | ---: | --- | --- |
| `main_push` | 1 | 今天进入主推池 | 合理。只有证据最完整、利润窗口最强的手工桌面风扇达到主推条件。 |
| `small_test` | 8 | 先发 1-2 条素材验证 | 合理。真实来源商品普遍缺少趋势、商家或用户反馈证据，适合小流量验证。 |
| `hold` | 3 | 暂缓，补证后再测 | 合理。弱维度较集中，且部分商品需要人工复核。 |
| `reject` | 0 | 当前不进入运营池 | 合理。mock 数据中没有达到明确淘汰条件的商品。 |

## 4. P0 今日主推商品复核

### 手工桌面风扇

- 来源：Manual
- 分数：100
- 为什么能主推：`profit_window(96)`，佣金、7 天和 30 天增长、关联视频与达人、评分和评论证据完整；`merchant_quality(75)`。
- 需要注意的风险：需求痛点、外部趋势和季节性维度仍偏弱。主推不等于无限放量，应观察真实转化。
- 建议今天怎么发：进入德国账号分发表，优先发 3 条。使用图文和短视频测试“热天桌面降温”“小空间使用”“日常实用性”角度。

## 5. P1 小样本测试商品复核

所有 P1 商品建议在 48 小时内观察 `CTR`、`CVR`、加购率、评论异议、退款或质量反馈。

### KaLoData Travel Cup

- 来源 / 分数：KaLoData / 62
- 为什么只做小样本：`external_trend(35)`，缺少 7 天、30 天增长和视频热度证据。
- 建议测试角度：问题解决、日常实用、性价比。
- 建议素材形式：图文，先发 1-2 条。

### KaLoData Makeup Bag

- 来源 / 分数：KaLoData / 62
- 为什么只做小样本：`profit_window(40)`、`seasonality(45)` 偏弱；功效表达需要人工审核。
- 建议测试角度：收纳前后对比、日常使用、送礼场景，避免未经证实的效果承诺。
- 建议素材形式：图文，审核文案后发 1-2 条。

### 手工收纳盒

- 来源 / 分数：Manual / 62
- 为什么只做小样本：商家证据较完整，但 `external_trend(35)`、`demand_pain(47)`、`seasonality(45)` 偏弱。
- 建议测试角度：桌面整理前后对比、小空间收纳、日常实用。
- 建议素材形式：图文和短视频各 1 条。

### Echo Pet Brush

- 来源 / 分数：EchoTik / 60
- 为什么只做小样本：`merchant_quality(45)`，缺少商品链接、评分、评论和 30 天增长证据。
- 建议测试角度：宠物行为、梳毛痛点、日常护理。
- 建议素材形式：图文，先发 1-2 条。

### FastMoss Cat Bowl

- 来源 / 分数：FastMoss / 55
- 为什么只做小样本：关联视频和佣金可用，但 `merchant_quality(45)`，缺少评分和评论证据。
- 建议测试角度：宠物行为、问题解决、日常使用。
- 建议素材形式：图文，先发 1-2 条。

### FastMoss Desk Lamp

- 来源 / 分数：FastMoss / 55
- 为什么只做小样本：`profit_window(48)`、`external_trend(45)`、`merchant_quality(45)` 偏弱。
- 建议测试角度：桌面照明痛点、小空间实用、性价比。
- 建议素材形式：图文，先发 1-2 条。

### Echo Storage Bag

- 来源 / 分数：EchoTik / 45
- 为什么只做小样本：`external_trend(35)`、`merchant_quality(45)`、`demand_pain(49)` 偏弱。
- 建议测试角度：整理前后对比、日常使用、性价比。
- 建议素材形式：图文，先发 1-2 条。

### Echo Mini Fan

- 来源 / 分数：EchoTik / 45
- 为什么只做小样本：季节性和需求痛点较好，但商家质量证据不足，并被标记为需要人工复核。
- 建议测试角度：热天痛点、免安装、小空间降温。
- 建议素材形式：图文和短视频；确认链接、佣金和商家质量后各发 1 条。

## 6. P2 暂缓补证商品复核

### 手工宠物碗

- 来源：Manual
- 暂缓原因：`profit_window(48)`、`demand_pain(35)`、`external_trend(35)`、`seasonality(45)` 偏弱。
- 需要补什么证据：评论痛点、同 SKU 竞争情况、市场趋势、价格带和店铺评分。
- 补齐后如何重新判断：确认宠物喂食痛点和差异化素材角度后，重新跑规则；优先恢复为 `small_test`。

### KaLoData Phone Stand

- 来源：KaLoData
- 暂缓原因：`external_trend(35)`、`seasonality(45)`、`demand_pain(47)` 偏弱，且 AIGC 适配需要人工复核。
- 需要补什么证据：7 天和 30 天增长、关联视频、评论痛点、竞品价格带、店铺评分。
- 补齐后如何重新判断：确认使用场景差异化和素材可表达性后，重新判断是否进入 `small_test`。

### FastMoss Cable Set

- 来源：FastMoss
- 暂缓原因：`demand_pain(35)`、`external_trend(45)`、`seasonality(45)` 偏弱，并被标记为需要人工复核。
- 需要补什么证据：增长趋势、评分评论、质量和兼容性反馈、竞品价格带、店铺评分。
- 补齐后如何重新判断：人工确认产品规格和质量风险，再决定进入 `small_test` 或维持 `hold`。

## 7. 风险质量复核

- `high_review` 商品共 4 个：KaLoData Makeup Bag、Echo Mini Fan、KaLoData Phone Stand、FastMoss Cable Set。标记合理，分别对应功效表达、电子类产品风险或 AIGC 表达复核。
- `attention` 商品共 8 个。数量偏多但符合当前 mock 数据：多数真实来源缺少趋势、评分评论或商家质量证据。该状态应理解为补证提醒，不是阻断。
- v1.6.1 已统一风险文案语言，英文风险提示已转换为中文。
- v1.6.1 已合并同类趋势证据、商家质量和小样本建议提示。
- v1.6.1 已通过 `ops_risk_note` 区分“运营提醒”“必须人工复核”“暂缓补证”。

## 8. 运营执行建议

- P0：手工桌面风扇今天发 3 条，优先进入德国通用账号和功能型账号。
- P1：每个商品先发 1-2 条，48 小时后按 `CTR`、`CVR`、加购率、评论异议和退款反馈复盘。KaLoData Makeup Bag 与 Echo Mini Fan 需先人工审核。
- P2：暂不进入生产。补齐证据后重新跑分析。
- 适合德国达人矩阵号：手工桌面风扇、Echo Mini Fan、FastMoss Desk Lamp、KaLoData Travel Cup、手工收纳盒。
- 适合宠物垂类账号：Echo Pet Brush、FastMoss Cat Bowl。手工宠物碗暂缓。
- 需要人工确认链接：EchoTik 全部商品、KaLoData 全部商品。
- 需要人工确认佣金和商家质量：EchoTik 全部商品、FastMoss 全部商品；电子类 Echo Mini Fan、KaLoData Phone Stand、FastMoss Cable Set 额外检查质量和规格。

## 9. v1.6 是否可以提交

- 结论：可以提交。
- 理由：四类来源识别正确，字段映射置信度符合目标；运营汇总文件非空；12 个商品全部通过 `decision` 与 `next_action` 一致性检查；风险字段不存在结构异常；完整测试通过。
- 已知轻微问题不阻塞 v1.6.1：CSV 使用 UTF-8 BOM 以兼容 Excel。
- 建议 commit message：

```text
feat(product-intel): finalize v1.6 source profiles and ops review
```
