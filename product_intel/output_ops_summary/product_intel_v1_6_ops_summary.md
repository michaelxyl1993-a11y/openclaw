# Product Intel v1.6 运营分发表

## 总览

- 商品总数：12
- 决策分布：main_push 1 / small_test 8 / hold 3 / reject 0
- next_action 一致性：全部通过

## 来源汇总

| 来源 | 商品总数 | main_push | small_test | hold | reject |
| --- | --- | --- | --- | --- | --- |
| echotik | 3 | 0 | 3 | 0 | 0 |
| fastmoss | 3 | 0 | 2 | 1 | 0 |
| kalodata | 3 | 0 | 2 | 1 | 0 |
| manual | 3 | 1 | 1 | 1 | 0 |

## 各来源 Top 5

### echotik

| 排名 | 商品 | 分数 | 决策 | 核心依据 | next_action |
| --- | --- | --- | --- | --- | --- |
| 1 | Echo Pet Brush | 60 | small_test | 判断依据：profit_window: medium (74)；demand_pain: medium (57)；seasonality: medium (65) | 小样本测试，先发1-2条验证CTR/转化 |
| 2 | Echo Storage Bag | 45 | small_test | 判断依据：profit_window: medium (56)；demand_pain: weak (49)；seasonality: medium (59) | 小样本测试，先发1-2条验证CTR/转化 |
| 3 | Echo Mini Fan | 45 | small_test | 判断依据：profit_window: medium (58)；demand_pain: medium (72)；seasonality: strong (77) | 小样本测试，先发1-2条验证CTR/转化 |

### fastmoss

| 排名 | 商品 | 分数 | 决策 | 核心依据 | next_action |
| --- | --- | --- | --- | --- | --- |
| 1 | FastMoss Cat Bowl | 55 | small_test | 判断依据：profit_window: medium (64)；demand_pain: medium (57)；seasonality: medium (65) | 小样本测试，先发1-2条验证CTR/转化 |
| 2 | FastMoss Desk Lamp | 55 | small_test | 判断依据：profit_window: weak (48)；demand_pain: weak (49)；seasonality: medium (59) | 小样本测试，先发1-2条验证CTR/转化 |
| 3 | FastMoss Cable Set | 40 | hold | 判断依据：profit_window: medium (64)；demand_pain: weak (35)；seasonality: weak (45) | 暂缓，不进今日主推池，补齐证据后再测 |

### kalodata

| 排名 | 商品 | 分数 | 决策 | 核心依据 | next_action |
| --- | --- | --- | --- | --- | --- |
| 1 | KaLoData Travel Cup | 62 | small_test | 判断依据：profit_window: medium (56)；demand_pain: medium (61)；seasonality: medium (59) | 小样本测试，先发1-2条验证CTR/转化 |
| 2 | KaLoData Makeup Bag | 62 | small_test | 判断依据：profit_window: weak (40)；demand_pain: medium (57)；seasonality: weak (45) | 小样本测试，先发1-2条验证CTR/转化 |
| 3 | KaLoData Phone Stand | 47 | hold | 判断依据：profit_window: medium (56)；demand_pain: weak (47)；seasonality: weak (45) | 暂缓，不进今日主推池，补齐证据后再测 |

### manual

| 排名 | 商品 | 分数 | 决策 | 核心依据 | next_action |
| --- | --- | --- | --- | --- | --- |
| 1 | 手工桌面风扇 | 100 | main_push | 主推依据：profit_window: strong (96)；demand_pain: weak (47)；seasonality: weak (45) | 今天可主推，进入账号分发表 |
| 2 | 手工收纳盒 | 62 | small_test | 判断依据：profit_window: medium (64)；demand_pain: weak (47)；seasonality: weak (45) | 小样本测试，先发1-2条验证CTR/转化 |
| 3 | 手工宠物碗 | 55 | hold | 判断依据：profit_window: weak (48)；demand_pain: weak (35)；seasonality: weak (45) | 暂缓，不进今日主推池，补齐证据后再测 |

## 风险商品

| 来源 | 商品 | 决策 | 风险等级 | 风险标记 | 强维度 | 弱维度 |
| --- | --- | --- | --- | --- | --- | --- |
| manual | 手工桌面风扇 | main_push | attention | 需求痛点证据偏弱（weak）；外部趋势证据不足（weak）；季节性支撑偏弱（weak） | profit_window(96), merchant_quality(75), aigc_fit(74) | external_trend(45), seasonality(45), demand_pain(47) |
| kalodata | KaLoData Travel Cup | small_test | attention | 外部趋势证据不足（weak）；建议先小样本验证 | aigc_fit(96), merchant_quality(75), competition(67) | external_trend(35), profit_window(56), seasonality(59) |
| kalodata | KaLoData Makeup Bag | small_test | high_review | 利润窗口偏弱（weak）；外部趋势证据不足（weak）；季节性支撑偏弱（weak）；功效表达需谨慎，避免缺少证据的效果承诺；缺少外部趋势证据，建议先小样本测试；建议先小样本验证 | aigc_fit(86), merchant_quality(75), competition(61) | profit_window(40), seasonality(45), external_trend(47) |
| manual | 手工收纳盒 | small_test | attention | 需求痛点证据偏弱（weak）；外部趋势证据不足（weak）；季节性支撑偏弱（weak）；建议先小样本验证 | merchant_quality(75), aigc_fit(74), profit_window(64) | external_trend(35), seasonality(45), demand_pain(47) |
| echotik | Echo Pet Brush | small_test | attention | 外部趋势证据不足（weak）；商家质量证据不足（weak）；建议先小样本验证 | aigc_fit(96), profit_window(74), seasonality(65) | merchant_quality(45), external_trend(51), demand_pain(57) |
| fastmoss | FastMoss Cat Bowl | small_test | attention | 商家质量证据不足（weak）；建议先小样本验证 | aigc_fit(96), competition(69), seasonality(65) | merchant_quality(45), demand_pain(57), external_trend(61) |
| fastmoss | FastMoss Desk Lamp | small_test | attention | 利润窗口偏弱（weak）；需求痛点证据偏弱（weak）；外部趋势证据不足（weak）；商家质量证据不足（weak）；建议先小样本验证 | aigc_fit(74), competition(63), seasonality(59) | external_trend(45), merchant_quality(45), profit_window(48) |
| echotik | Echo Storage Bag | small_test | attention | 需求痛点证据偏弱（weak）；外部趋势证据不足（weak）；商家质量证据不足（weak）；建议先小样本验证 | aigc_fit(90), competition(61), seasonality(59) | external_trend(35), merchant_quality(45), demand_pain(49) |
| echotik | Echo Mini Fan | small_test | high_review | Medium product risk level.；Human review is required.；商家质量证据不足（weak）；建议先小样本验证 | seasonality(77), demand_pain(72), aigc_fit(72) | merchant_quality(45), external_trend(57), profit_window(58) |
| manual | 手工宠物碗 | hold | attention | 利润窗口偏弱（weak）；需求痛点证据偏弱（weak）；外部趋势证据不足（weak）；季节性支撑偏弱（weak） | aigc_fit(74), merchant_quality(63), competition(55) | demand_pain(35), external_trend(35), seasonality(45) |
| kalodata | KaLoData Phone Stand | hold | high_review | Medium product risk level.；Human review is required.；需求痛点证据偏弱（weak）；外部趋势证据不足（weak）；季节性支撑偏弱（weak）；AIGC 适配需人工复核（weak） | merchant_quality(75), competition(61), profit_window(56) | external_trend(35), seasonality(45), demand_pain(47) |
| fastmoss | FastMoss Cable Set | hold | high_review | Medium product risk level.；Human review is required.；需求痛点证据偏弱（weak）；外部趋势证据不足（weak）；季节性支撑偏弱（weak）；商家质量证据不足（weak） | profit_window(64), competition(63), aigc_fit(56) | demand_pain(35), external_trend(45), seasonality(45) |

## 运营分发表

| 优先级 | 来源 | 商品 | 类目 | 分数 | 决策 | 风险 | 建议日更 | 账号类型 | 核心依据 | next_action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P0_今日主推 | manual | 手工桌面风扇 | 电子 | 100 | main_push | attention | 3 | general | 主推依据：profit_window: strong (96)；demand_pain: weak (47)；seasonality: weak (45) | 今天可主推，进入账号分发表 |
| P1_小样本测试 | kalodata | KaLoData Travel Cup | Kitchen | 62 | small_test | attention | 2 | mature_female_home | 判断依据：profit_window: medium (56)；demand_pain: medium (61)；seasonality: medium (59) | 小样本测试，先发1-2条验证CTR/转化 |
| P1_小样本测试 | kalodata | KaLoData Makeup Bag | Beauty | 62 | small_test | high_review | 2 | young_female_lifestyle | 判断依据：profit_window: weak (40)；demand_pain: medium (57)；seasonality: weak (45) | 小样本测试，先发1-2条验证CTR/转化 |
| P1_小样本测试 | manual | 手工收纳盒 | 家居 | 62 | small_test | attention | 2 | general | 判断依据：profit_window: medium (64)；demand_pain: weak (47)；seasonality: weak (45) | 小样本测试，先发1-2条验证CTR/转化 |
| P1_小样本测试 | echotik | Echo Pet Brush | Pet Supplies | 60 | small_test | attention | 2 | pet/home/lifestyle | 判断依据：profit_window: medium (74)；demand_pain: medium (57)；seasonality: medium (65) | 小样本测试，先发1-2条验证CTR/转化 |
| P1_小样本测试 | fastmoss | FastMoss Cat Bowl | Pet Supplies | 55 | small_test | attention | 2 | pet/home/lifestyle | 判断依据：profit_window: medium (64)；demand_pain: medium (57)；seasonality: medium (65) | 小样本测试，先发1-2条验证CTR/转化 |
| P1_小样本测试 | fastmoss | FastMoss Desk Lamp | Home | 55 | small_test | attention | 2 | mature_female_home | 判断依据：profit_window: weak (48)；demand_pain: weak (49)；seasonality: medium (59) | 小样本测试，先发1-2条验证CTR/转化 |
| P1_小样本测试 | echotik | Echo Storage Bag | Home | 45 | small_test | attention | 2 | mature_female_home | 判断依据：profit_window: medium (56)；demand_pain: weak (49)；seasonality: medium (59) | 小样本测试，先发1-2条验证CTR/转化 |
| P1_小样本测试 | echotik | Echo Mini Fan | Electronics | 45 | small_test | high_review | 2 | male_functional | 判断依据：profit_window: medium (58)；demand_pain: medium (72)；seasonality: strong (77) | 小样本测试，先发1-2条验证CTR/转化 |
| P2_暂缓补证 | manual | 手工宠物碗 | 宠物 | 55 | hold | attention | 1 | general | 判断依据：profit_window: weak (48)；demand_pain: weak (35)；seasonality: weak (45) | 暂缓，不进今日主推池，补齐证据后再测 |
| P2_暂缓补证 | kalodata | KaLoData Phone Stand | Electronics | 47 | hold | high_review | 1 | male_functional | 判断依据：profit_window: medium (56)；demand_pain: weak (47)；seasonality: weak (45) | 暂缓，不进今日主推池，补齐证据后再测 |
| P2_暂缓补证 | fastmoss | FastMoss Cable Set | Electronics | 40 | hold | high_review | 1 | male_functional | 判断依据：profit_window: medium (64)；demand_pain: weak (35)；seasonality: weak (45) | 暂缓，不进今日主推池，补齐证据后再测 |
