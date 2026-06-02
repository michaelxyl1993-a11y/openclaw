# Product Intel v1.11 Final Ops Decision Table

| 商品 ID | 商品名 | 来源 | 规则决策 | 分数 | LLM 复核 | 置信度 | 最终动作 | 优先级 | 原因 |
| --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| echo-1 | Echo Pet Brush | echotik | small_test | 60 | agree | medium | small_test | P1_small_test | 规则建议小样本测试且 LLM Judge 同意 |
| echo-2 | Echo Storage Bag | echotik | small_test | 45 | agree | medium | small_test | P1_small_test | 规则建议小样本测试且 LLM Judge 同意 |
| echo-3 | Echo Mini Fan | echotik | small_test | 45 | agree | medium | small_test | P1_small_test | 规则建议小样本测试且 LLM Judge 同意 |
| fm-1 | FastMoss Cat Bowl | fastmoss | small_test | 55 | agree | medium | small_test | P1_small_test | 规则建议小样本测试且 LLM Judge 同意 |
| fm-2 | FastMoss Desk Lamp | fastmoss | small_test | 55 | agree | medium | small_test | P1_small_test | 规则建议小样本测试且 LLM Judge 同意 |
| fm-3 | FastMoss Cable Set | fastmoss | hold | 40 | agree | high | hold_for_evidence | P2_hold | 规则建议暂缓，保留观察并补充证据 |
| kalo-1 | KaLoData Travel Cup | kalodata | small_test | 62 | agree | medium | small_test | P1_small_test | 规则建议小样本测试且 LLM Judge 同意 |
| kalo-3 | KaLoData Makeup Bag | kalodata | small_test | 62 | agree | medium | small_test | P1_small_test | 规则建议小样本测试且 LLM Judge 同意 |
| kalo-2 | KaLoData Phone Stand | kalodata | hold | 47 | agree | high | hold_for_evidence | P2_hold | 规则建议暂缓，保留观察并补充证据 |
| manual-3 | 手工桌面风扇 | manual | main_push | 100 | challenge | high | human_review_first | P0_review | LLM Judge challenge，人工复核后再执行规则建议 |
| manual-1 | 手工收纳盒 | manual | small_test | 62 | agree | medium | small_test | P1_small_test | 规则建议小样本测试且 LLM Judge 同意 |
| manual-2 | 手工宠物碗 | manual | hold | 55 | agree | medium | hold_for_evidence | P2_hold | 规则建议暂缓，保留观察并补充证据 |
