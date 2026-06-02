# Product Intel v1.1

Product Intel is the middle layer between EchoTik product intelligence and OpenClaw internal workflows.

It converts raw product data into a shared **Product Fact Sheet** that can later be consumed by:

- Product selection bots
- Manager image workflows
- Video Director video workflows
- Product mismatch / claims QA

## Current Scope

This is mock v1.1. It does not call the real EchoTik or FastMoss API yet.

Current flow:

1. Read `mock_echotik_product.json`
2. Convert it into a normalized Product Fact Sheet
3. Recommend reusable hooks from the Hook Core Library
4. Generate a lightweight Opportunity Score
5. Read multiple mock product candidates from `mock_echotik_products.json`
6. Batch-generate Fact Sheets and Opportunity Scores
7. Save outputs as JSON or JSONL for downstream bots and workflows
8. Read local CSV candidate tables and normalize common EchoTik / FastMoss / manual field names
9. Export team-readable decision tables as CSV / Markdown
10. Export machine-readable manager / bot payload JSON
11. Run the full local pipeline from a single CLI command
12. Diagnose real CSV schema and field mappings before running the pipeline
13. Validate required fields with local smoke tests
14. Expose a framework-neutral service handler for Feishu Bot / HTTP / manager integration
15. Receive CSV / Excel file messages from Feishu, run Product Intel, and reply with summary text
16. Read `.xlsx` / OOXML `.xls` files through `excel_loader.py` and include file type / sheet metadata in profiles

## v0.2 Additions

### Hook Library

`hook_library.py` defines a first-pass Hook Core Library with 20 reusable hook types, including:

- price shock
- hot weather pain point
- messy home pain point
- before / after
- problem / solution
- pet behavior
- daily usefulness
- shelf value deal

The Product Fact Sheet now recommends 3-5 hooks based on product category and product name.

### Opportunity Score

`opportunity_score.py` adds a lightweight product selection decision layer:

- `opportunity_score`: 0-100
- `decision`: `main_push`, `small_test`, `observe`, or `reject`
- reasons and risk flags
- suggested photo/video formats
- suggested daily volume
- content angle summary

## v0.3 Additions

### Batch Product Input

`mock_echotik_products.json` contains multiple EchoTik / FastMoss-style product candidates across:

- pet cat bowl
- portable fan
- storage bag
- beauty product
- snack / food
- electronics gadget
- fashion item

`batch_fact_sheet.py` converts each product into:

```json
{
  "items": [
    {
      "fact_sheet": {},
      "opportunity": {}
    }
  ]
}
```

### Export Utilities

`export_utils.py` supports:

- `save_json(...)`
- `save_jsonl(...)`

These outputs are intended for later selection bots, Manager image workflows, Video Director workflows, and product QA.

## v0.4 Additions

### CSV Input Adapter

`input_adapter.py` normalizes candidate rows from EchoTik, FastMoss, or manual selection sheets into one internal product dict:

```json
{
  "product_id": "...",
  "product_name": "...",
  "category": "...",
  "price": "...",
  "commission_rate": "...",
  "sold_count": "...",
  "gmv": "...",
  "source_platform": "...",
  "raw": {}
}
```

Supported aliases include English and Chinese field names such as:

- `product_id`, `item_id`, `goods_id`, `商品ID`
- `product_name`, `title`, `商品名称`, `商品标题`, `name`
- `category`, `leaf_category`, `category_name`, `类目`, `商品类目`
- `price`, `sale_price`, `min_price`, `价格`, `售价`
- `commission_rate`, `commission`, `佣金率`, `达人佣金率`
- `sold_count`, `sales`, `sold`, `销量`, `已售`
- `gmv`, `GMV`, `sales_amount`, `销售额`
- `source_platform`, `candidate_source`, `来源`, `数据来源`

`csv_loader.py` reads local CSV files and applies this normalization automatically.

Current input types:

- JSON mock products: `mock_echotik_products.json`
- CSV candidate table: `mock_products.csv`

## v0.5 Additions

### Decision Table Output

`decision_table.py` converts batch Product Intel results into one row per product for team review.

Each row includes:

- rank
- product ID and name
- category and source platform
- price, commission, sold count, GMV
- opportunity score and decision
- suggested format and daily posting volume
- recommended hooks
- reasons, risk flags, and next action

`export_decision_table.py` exports:

- UTF-8-SIG CSV for Excel: `product_intel/output/mock_decision_table.csv`
- Markdown table: `product_intel/output/mock_decision_table.md`

The Markdown table keeps the review columns compact:

`rank | 商品 | 类目 | 分数 | 决策 | 建议形式 | 日投放 | hooks | 风险 | 下一步动作`

## v0.6 Additions

### Manager / Bot JSON Payload

v0.5 outputs CSV / Markdown for people.

v0.6 adds a stable JSON payload for manager, bot, and workflow consumers:

- OpenClaw manager
- DS Bot
- Feishu Bot
- Video Director

`manager_payload.py` converts batch results into:

```json
{
  "version": "product_intel_v0.6",
  "meta": {},
  "summary": {},
  "products": []
}
```

Each product contains normalized decision, routing, recommended formats, hooks, manager instruction, and next action.

`export_manager_payload.py` writes:

- `product_intel/output/mock_manager_payload.json`

## v0.7 Additions

### Unified CLI Runner

v0.5 outputs CSV / Markdown for people.

v0.6 outputs JSON payload for manager / bot / workflow consumers.

v0.7 adds one stable CLI runner that takes a real CSV path and runs the whole local chain:

```bash
python3 -m product_intel.run_product_intel \
  --input product_intel/mock_products.csv \
  --source mock \
  --market de \
  --output-dir product_intel/output
```

It writes:

- `product_intel/output/product_intel_decision_table.csv`
- `product_intel/output/product_intel_decision_table.md`
- `product_intel/output/product_intel_manager_payload.json`

Useful options:

- `--limit 10`
- `--format all`
- `--format decision_csv`
- `--format decision_md`
- `--format manager_json`

## v0.8 Additions

### CSV Profile / Schema Diagnosis

v0.7 is the unified CLI runner.

v0.8 adds real CSV input diagnosis and field mapping reports before Product Intel runs the full pipeline.

New outputs:

- `product_intel/output/product_intel_csv_profile.json`
- `product_intel/output/product_intel_csv_profile.md`

Profile-only mode:

```bash
python3 -m product_intel.run_product_intel \
  --input product_intel/mock_products.csv \
  --source auto \
  --profile-only
```

Full run with profiling:

```bash
python3 -m product_intel.run_product_intel \
  --input product_intel/mock_products.csv \
  --source auto \
  --market de \
  --output-dir product_intel/output
```

## v0.9 Additions

### Service Handler

v0.7 is the unified CLI runner.

v0.8 adds CSV profile / field mapping diagnosis.

v0.9 adds a framework-neutral service handler for Feishu Bot, HTTP services, and OpenClaw manager integration.

It accepts a CSV file path and returns a structured result with:

- Chinese `summary_text` suitable for a short Feishu reply
- CSV profile data and output paths
- decision summary and Top 5 products
- decision table CSV / Markdown paths
- manager payload JSON path
- warnings and errors without raising into the caller

Example service call:

```python
from product_intel.service_handler import run_product_intel_job

result = run_product_intel_job(
    input_path="/tmp/uploaded.csv",
    source="auto",
    market="de",
    output_dir="product_intel/output",
)

print(result["summary_text"])
```

Smoke test:

```bash
python3 -m product_intel.test_service_handler
python3 -m product_intel.test_excel_loader
python3 -m product_intel.test_feishu_product_intel_bot
```



## v1.1 Additions

### Excel Input Support

v1.1 keeps CSV compatibility and adds Excel upload support for Product Intel.

Supported inputs:

- `.csv`
- `.xlsx`
- `.xls` files that contain an OOXML workbook

`excel_loader.py` reads the first non-empty sheet, removes empty rows / columns, strips header whitespace, and returns the same `list[dict]` row structure as `csv_loader.py`.

Input profiles now include:

- `detected_file_type`
- `detected_sheet_name`
- `row_count`
- `mapped_fields`
- `missing_fields`
- `warnings`

The Feishu Bot now accepts CSV or Excel files and replies with:

```text
请上传 CSV 或 Excel 文件进行商品分析。
```

Smoke test:

```bash
python3 -m product_intel.test_excel_loader
```

## 线上运维固化

当前线上配置：

- 飞书回调域名：`https://productbot.packytech.com/feishu/events`
- Product Bot 服务端口：`8788`
- 独立 Cloudflare Tunnel 配置文件：`~/.cloudflared/product-bot.yml`
- PM2 进程名：`product-intel-feishu-bot`、`product-bot-tunnel`

启动 bot：

```bash
pm2 start "python3 -m product_intel.feishu_product_intel_bot" --name product-intel-feishu-bot
```

重启 bot：

```bash
pm2 restart product-intel-feishu-bot --update-env
```

查看日志：

```bash
pm2 logs product-intel-feishu-bot --lines 100
pm2 logs product-bot-tunnel --lines 100
```

保存 PM2：

```bash
pm2 save
```

查看进程：

```bash
pm2 list
```

健康检查：

```bash
curl http://127.0.0.1:8788/health
curl https://productbot.packytech.com/health
```

更详细的 health check：

```bash
curl -v --max-time 5 http://127.0.0.1:8788/health
curl -v --noproxy "*" --max-time 15 https://productbot.packytech.com/health
```

飞书回调 challenge 检查：

```bash
curl -i --noproxy "*" -X POST https://productbot.packytech.com/feishu/events \
  -H "Content-Type: application/json" \
  -d '{"type":"url_verification","challenge":"product-bot-check"}'
```

运行 ops_check：

```bash
python3 -m product_intel.ops_check
```

`ops_check.py` 会输出：

- `local_health`: `ok` / `fail`
- `public_health`: `ok` / `fail`
- `service_name`
- `status_code`
- `response_text`
- 网络失败错误原因

### 线上排障 SOP

按以下顺序检查：

1. `curl http://127.0.0.1:8788/health` 返回 HTTP 200，代表 Product Bot 本地服务正常。
2. `curl https://productbot.packytech.com/health` 返回 HTTP 200，代表公网入口和 tunnel 基本正常。
3. `/feishu/events` challenge 请求返回 HTTP 200 且包含原始 challenge，代表飞书回调路由正常。
4. HTTP 530 或 Cloudflare `error 1033`，代表 tunnel 没有活跃 connector。检查 `product-bot-tunnel` 进程和 `~/.cloudflared/product-bot.yml`。
5. HTTP 404 且响应头包含 `server: cloudflare`，代表 hostname、tunnel 或 ingress 路由异常。

如果本地 health OK，外网 health 404：

- 检查 `~/.cloudflared/product-bot.yml` 是否包含 `productbot.packytech.com -> 127.0.0.1:8788`
- 检查 `product-bot-tunnel` 是否在线或已重启

如果本地 health 不通：

- 检查 `product-intel-feishu-bot` 是否在线：

```bash
pm2 list
```

如果飞书不回复但 health OK：

- 查看日志：

```bash
pm2 logs product-intel-feishu-bot --lines 100
```

- 检查飞书事件订阅和回调 URL

如果文件能分析但文本不回复：

- 检查 text fallback handler
- 日志中应出现 `text fallback replied`

如果飞书上传文件可以正常处理，但外网 `curl` timeout：

- 优先怀疑本机代理或 Cloudflare Tunnel 偶发连接问题
- 这不一定代表 bot 功能失败
- 先用本地直连 health check 确认 bot 是否在线
- 再用 `--noproxy "*"` 排除本机代理影响

## v1.2 Additions

### 8 维度选品决策引擎

v1.2 adds a rule-based dimension scoring layer on top of the existing `opportunity_score`.

The old fields remain compatible:

- `opportunity_score`
- `decision`
- `reasons`
- `risk_flags`
- `suggested_content_formats`
- `suggested_daily_volume`

Each batch item now also includes `dimension_scores`:

1. `profit_window` / 利润窗口期判断
2. `demand_pain` / 平台评论与需求痛点分析
3. `external_trend` / 外部趋势、舆论、热点
4. `seasonality` / 季节判断
5. `competition` / 跟卖与竞争判断
6. `merchant_quality` / 商家维度判断
7. `aigc_fit` / AIGC 适配判断
8. `final_test_decision` / 最终测试决策

The first seven dimensions output:

- `score`
- `level`: `strong` / `medium` / `weak` / `unknown`
- `reasons`
- `missing_evidence`
- `suggested_action`

`final_test_decision` outputs:

- `decision`
- `score`
- `reasons`
- `next_action`
- `suggested_daily_posts`
- `suggested_accounts`
- `suggested_formats`
- `review_after_48h_metrics`

Current v1.2 logic is rules-only. It uses available local fields such as category, product name, price, commission rate, sales, growth, related video count, related influencer count, rating, review count, and recommended hooks.

Dimensions that still need future external data or LLM enrichment:

- `demand_pain`: real review clustering and buyer language
- `external_trend`: Google Trends, TikTok hashtags, Instagram/Reels, YouTube Shorts
- `competition`: same-SKU count, competitor price range, top creative monopoly
- `merchant_quality`: richer shop score, fulfillment risk, return/refund signal

Decision table outputs now include:

- `dimension_summary`
- `strongest_dimensions`
- `weakest_dimensions`
- `missing_evidence_count`

Manager payload outputs now include per-product `dimension_scores` plus summary-level:

- `dimension_distribution`
- `main_push_reasons_summary`
- `common_missing_evidence`

Smoke test:

```bash
python3 -m product_intel.test_dimension_score
```

## v1.3 Additions

### LLM Summary Layer

v1.3 adds an optional natural-language summary layer for operations teams.

Current behavior is still local and deterministic:

- No OpenAI / Qwen / Gemini API call
- No external network request
- No score changes
- No decision changes
- No `dimension_scores` changes

`llm_summary.py` provides:

- `build_llm_summary_prompt(manager_payload, market="de")`
- `build_rule_based_summary(manager_payload, market="de")`
- `attach_summary_to_payload(manager_payload, market="de", use_llm=False)`

The manager payload now includes:

```json
{
  "llm_summary": {
    "mode": "rule_based",
    "summary_text": "...",
    "llm_prompt": "..."
  }
}
```

The prompt explicitly tells future LLMs:

- Do not modify existing `score`, `decision`, or `dimension_scores`
- Do not invent external data
- If evidence is missing, write `缺失证据`
- Output Chinese only
- Make the result suitable for operations teams

Feishu Bot replies now include an `运营摘要` preview, capped to the first 800 characters, while attachments remain the primary detailed delivery.

Future v1.4 / v1.5 can connect a real LLM API using the generated prompt.

Smoke test:

```bash
python3 -m product_intel.test_llm_summary
```

## v1.4 Additions

### Fast ACK + Background Queue

v1.4 moves Feishu file processing out of the Flask request thread.

`job_queue.py` provides an in-process `queue.Queue` and daemon worker. The webhook flow is now:

1. Parse the Feishu event
2. Build the dedupe key from `message_id`, falling back to `event_id`
3. Reserve the key while the job is queued or running
4. Enqueue the background job
5. Return HTTP 200 immediately
6. Download files, run Product Intel, upload result attachments, and send replies in the worker

Text fallback replies also use the same queue, so webhook ACK does not wait for Feishu message delivery.

Useful logs:

- `event_received`
- `event_ack`
- `job_enqueued`
- `job_started`
- `job_finished`
- `job_failed`
- `duplicate_skipped`

## v1.5 Additions

### Structured 8-Dimension Delivery

v1.5 keeps the Feishu callback, PM2 process, Cloudflare Tunnel, and legacy opportunity fields unchanged. It strengthens the machine-readable selection output for OpenClaw Manager and human operations review.

Each product keeps the existing fields:

- `opportunity_score`
- `decision`
- `recommended_format`
- `recommended_hooks`
- `risk_flags`
- `next_action`

Each `dimension_scores` entry now exposes a consistent local-rule contract:

- `score`
- `level`
- `reason`
- `reasons`
- `missing_evidence`

The final decision also keeps its execution fields, including suggested formats, suggested accounts, daily posts, and 48-hour review metrics.

Decision table Markdown now presents:

- product name
- final decision and total score
- 8-dimension summary
- strongest dimensions
- weakest dimensions
- main push / decision reason
- risk flags
- next action

Manager payload products now include:

- `dimension_scores`
- `dimension_summary`
- `strongest_dimensions`
- `weakest_dimensions`
- `missing_evidence_count`
- `main_push_reason`
- `risk_flags`
- `next_action`

This version does not call external APIs. Missing review clusters, trend signals, competitor pricing, and merchant fulfillment evidence remain explicit in `missing_evidence`.

The public delivery decision has one source of truth: `dimension_scores.final_test_decision.decision`. Legacy `opportunity_score` remains available for ranking and backward compatibility, but its preliminary decision no longer overrides the 8-dimension final decision in CSV, Markdown, manager payload, or Feishu summaries.

Risk flags are derived from relevant `weak` / `unknown` dimensions and category-specific review needs. Main-push products are not mechanically filled with warnings when no material risk signal exists.

## v1.0 Additions

### Feishu CSV Upload Trigger

v1.0 adds an independent Feishu bot entrypoint for Product Intel. It does not modify PublishKit or Video Director.

Minimum flow:

1. Feishu receives a CSV file message
2. Bot downloads the CSV to `/tmp/product_intel_uploads`
3. Bot calls `product_intel.service_handler.run_product_intel_job(...)`
4. Bot replies with `summary_text` and local `output_files` paths

Run locally:

```bash
cd /Users/michaelchui/Desktop/openclaw_tools

export FEISHU_APP_ID=xxx
export FEISHU_APP_SECRET=xxx

python3 -m product_intel.feishu_product_intel_bot
```

Run with PM2:

```bash
pm2 start "python3 -m product_intel.feishu_product_intel_bot" --name product-intel-feishu-bot
```

Production / PM2 runtime requires:

```bash
export FEISHU_APP_ID=xxx
export FEISHU_APP_SECRET=xxx
```

Local unit tests mock Feishu OpenAPI calls and do not require real `FEISHU_APP_ID` or `FEISHU_APP_SECRET`.

Health check:

```bash
curl http://127.0.0.1:8788/health
```

Port configuration:

```bash
export PRODUCT_INTEL_BOT_PORT=8788
```

Smoke test:

```bash
python3 -m product_intel.test_feishu_product_intel_bot
```

## v1.7 Evidence Pack

v1.7 adds a local-only Evidence Pack layer before a future LLM Judge integration.

- Each manager payload product now includes `evidence_pack` and `evidence_coverage_summary`.
- Evidence Packs expose the available fields, coverage level, and missing evidence for 8 dimensions: `profit_window`, `demand_pain`, `external_trend`, `seasonality`, `competition`, `merchant_quality`, `aigc_fit`, and `final`.
- Evidence Pack generation is read-only. It does not change scoring, `decision`, `next_action`, `risk_flags`, or `ops_risk_note`.
- v1.7 does not call external APIs.
- v1.7 does not call OpenAI or GPT-5.5.
- A future Judge integration can pass this evidence layer to GPT-5.5 for evidence-bounded review without allowing unsupported assumptions.

Run the Evidence Pack regression test:

```bash
python3 -m product_intel.test_evidence_pack
```

## v1.8 LLM Judge Contract

v1.8 adds a local-only LLM Judge contract layer for future GPT-5.5 review.

- `llm_judge_contract.py` builds and validates strict Judge input and output JSON contracts.
- `llm_judge_prompt.py` builds an evidence-bounded prompt that requires strict JSON output.
- `mock_llm_judge.py` provides a deterministic local mock for contract tests.
- Manager payload products expose `llm_judge_ready` and a lightweight `llm_judge_input_ref`. Full prompts are not embedded in each product.
- The Judge can only review and challenge a rule result. It cannot override rule scoring, `decision`, or `next_action`.
- v1.8 does not call external APIs.
- v1.8 does not call OpenAI or GPT-5.5.
- GPT-5.5 can be integrated in v1.9 or v1.8.1 after the contract is approved.

Run the Judge contract regression tests:

```bash
python3 -m product_intel.test_llm_judge_contract
python3 -m product_intel.test_llm_judge_prompt
```

## v1.8.1 OpenAI LLM Judge Adapter

v1.8.1 adds an opt-in OpenAI Responses API adapter for GPT-5.5 review.

- Local workflows continue to use the mock Judge by default.
- The real GPT-5.5 Judge is disabled unless `PRODUCT_INTEL_REAL_LLM_ENABLED=true`.
- The adapter accepts one product evidence item at a time and sends the existing evidence-bounded Judge prompt.
- The adapter uses Structured Outputs JSON schema validation and validates the response against the v1.8 Judge contract.
- A Judge result is review advice only. It cannot override rule scoring, `decision`, `opportunity_score`, or `next_action`.
- Aggregate `all_evidence.json` remains an export artifact. Do not pass it to `run_product_intel`.

Enable the real Judge explicitly:

```bash
export OPENAI_API_KEY="..."
export OPENAI_MODEL="gpt-5.5"
export PRODUCT_INTEL_REAL_LLM_ENABLED=true
```

Run the adapter regression test:

```bash
python3 -m product_intel.test_openai_llm_judge
```

## v1.9 LLM Judge Result Merger

v1.9 adds an operations-facing merger for rule results and optional LLM Judge reviews.

- The merger preserves rule `decision`, `opportunity_score`, and `next_action`.
- Judge results only add review fields and human-review priorities.
- Current mock Judge exports and future real adapter results are both supported.
- The merger is a separate CLI. Its `--judge-results` option does not belong to `run_product_intel`.

```bash
python3 -m product_intel.llm_judge_merger \
  --evidence product_intel/output_next_round/all_evidence.json \
  --judge-results product_intel/output_next_round/all_evidence_mock_llm_judge_results.json \
  --output-dir product_intel/output_next_round
```

Run the merger regression test:

```bash
python3 -m product_intel.test_llm_judge_merger
```

## v1.10 Real LLM Judge Batch Runner

v1.10 adds a batch runner for opt-in real GPT-5.5 Judge reviews.

- The runner defaults to dry-run mode and does not call the OpenAI API.
- Real calls require `--real-llm`, `PRODUCT_INTEL_REAL_LLM_ENABLED=true`, and `OPENAI_API_KEY`.
- Use `--limit 1` for the first real call.
- The runner only generates review results. It does not modify rule scoring, `decision`, `opportunity_score`, or `next_action`.
- Pass `--merge` to generate separate operations outputs through the v1.9 merger without overwriting mock merger files.

Dry-run:

```bash
python3 -m product_intel.real_llm_judge_runner \
  --evidence product_intel/output_next_round/all_evidence.json \
  --output-dir product_intel/output_next_round \
  --limit 2
```

First real single-product review:

```bash
export OPENAI_API_KEY="..."
export OPENAI_MODEL="gpt-5.5"
export PRODUCT_INTEL_REAL_LLM_ENABLED=true

python3 -m product_intel.real_llm_judge_runner \
  --evidence product_intel/output_next_round/all_evidence.json \
  --output-dir product_intel/output_next_round \
  --real-llm \
  --limit 1 \
  --merge
```

Run the batch runner regression test:

```bash
python3 -m product_intel.test_real_llm_judge_runner
```

## v1.10.1 Append and Resume

v1.10.1 adds cumulative result handling for incremental real Judge runs.

- Use `--append` to load existing results and upsert newly processed products by `product_id`.
- Use `--resume` to skip products that already have `runner_status=success` and `real_llm_called=true`.
- With `--resume`, `--limit` means the maximum number of not-yet-successful products to process in the current run.
- Use `--existing-results` to load a non-default cumulative results file.
- When `--merge` is combined with `--append` or `--resume`, operations outputs use cumulative results.

Recommended incremental real review flow:

```bash
python3 -m product_intel.real_llm_judge_runner \
  --evidence product_intel/output_next_round/all_evidence.json \
  --output-dir product_intel/output_next_round \
  --real-llm \
  --limit 1 \
  --merge \
  --append

python3 -m product_intel.real_llm_judge_runner \
  --evidence product_intel/output_next_round/all_evidence.json \
  --output-dir product_intel/output_next_round \
  --real-llm \
  --limit 1 \
  --merge \
  --resume
```

## v1.10.2 Real Success Protection

v1.10.2 protects completed real Judge reviews during cumulative runs.

- Dry-run `--append` and `--resume` runs do not overwrite an existing result with `runner_status=success` and `real_llm_called=true`.
- `--resume` skips existing real successes before applying `--limit`, so incremental runs continue with the next product requiring review.
- Use `--force-overwrite-success` only when an existing real success must be rerun or deliberately replaced.
- Cumulative `--merge` outputs use the protected result set.

Recommended command for reviewing one additional product:

```bash
python3 -m product_intel.real_llm_judge_runner \
  --evidence product_intel/output_next_round/all_evidence.json \
  --output-dir product_intel/output_next_round \
  --real-llm \
  --limit 1 \
  --resume \
  --merge
```

## v1.11 Final Ops Decision Exporter

v1.11 adds the final operations decision export layer.

- The exporter does not call an LLM or any external API.
- It reads the v1.10.2 real Judge merged CSV and preserves rule `decision`, `opportunity_score`, and `next_action`.
- LLM challenges become `human_review_first`; agreed rule results become direct operations actions.
- The exported final decision table is ready for operations distribution.

```bash
python3 -m product_intel.final_ops_decision_exporter \
  --input product_intel/output_next_round/all_evidence_with_real_llm_review.csv \
  --output-dir product_intel/output_next_round
```

Run the exporter regression test:

```bash
python3 -m product_intel.test_final_ops_decision_exporter
```

## v1.12 Feishu Ops Handoff Pack

v1.12 adds a local-only Feishu operations handoff pack.

- It does not send messages or files to Feishu.
- It does not modify the Feishu callback, PM2, Cloudflare Tunnel, or `job_queue`.
- It reads v1.11 final operations outputs and generates files that can be copied, uploaded, and checked by the operations team.

```bash
python3 -m product_intel.feishu_ops_handoff_pack \
  --final-table product_intel/output_next_round/final_ops_decision_table.csv \
  --summary product_intel/output_next_round/final_ops_action_summary.json \
  --output-dir product_intel/output_next_round
```

Run the handoff pack regression test:

```bash
python3 -m product_intel.test_feishu_ops_handoff_pack
```

## v1.13 Feishu Upload Dry Run

v1.13 adds a local-only upload readiness check for the Feishu operations handoff.

- It does not upload attachments.
- It does not send Feishu messages.
- It validates handoff files and generates an upload plan, report, and attachment manifest CSV.

```bash
python3 -m product_intel.feishu_upload_dry_run \
  --manifest product_intel/output_next_round/feishu_ops_handoff_manifest.json \
  --message product_intel/output_next_round/feishu_ops_handoff_message.md \
  --output-dir product_intel/output_next_round
```

Run the upload dry-run regression test:

```bash
python3 -m product_intel.test_feishu_upload_dry_run
```

## v1.14 Feishu Upload Adapter Mock / Sandbox

v1.14 adds a local-only mock adapter for the Feishu upload flow.

- It does not upload real attachments.
- It does not send Feishu messages.
- It generates stable mock file tokens, a sandbox receipt, and a message preview.
- A future v1.15 can design a real upload adapter, but real upload must remain disabled by default.

```bash
python3 -m product_intel.feishu_upload_adapter_mock \
  --dry-run-plan product_intel/output_next_round/feishu_upload_dry_run_plan.json \
  --message product_intel/output_next_round/feishu_ops_handoff_message.md \
  --output-dir product_intel/output_next_round
```

Run the mock adapter regression test:

```bash
python3 -m product_intel.test_feishu_upload_adapter_mock
```

## v1.15 Real Feishu Upload Adapter

v1.15 adds an opt-in real Feishu upload adapter for a single-file trial.

- Real upload is disabled by default.
- Only one attachment can be uploaded per command.
- The adapter uploads the file only. It does not send a Feishu message.
- Real upload requires `PRODUCT_INTEL_REAL_FEISHU_UPLOAD_ENABLED=true`, `FEISHU_APP_ID`, and `FEISHU_APP_SECRET`.
- A future v1.16 can consider real message sending, but it must also remain disabled by default.

Disabled-by-default check:

```bash
python3 -m product_intel.feishu_upload_adapter_real \
  --dry-run-plan product_intel/output_next_round/feishu_upload_dry_run_plan.json \
  --attachment-index 0 \
  --output-dir product_intel/output_next_round
```

Run the real adapter regression test:

```bash
python3 -m product_intel.test_feishu_upload_adapter_real
```

## v1.16 Feishu Message Send Adapter Mock / Disabled Real Send

v1.16 adds a local-only message send preview adapter.

- It does not send real Feishu messages.
- It does not call the real Feishu message API.
- It can use a real upload receipt token when available or fall back to v1.14 mock tokens for preview.
- A future v1.17 can trial real message sending, but it must remain disabled by default and require an explicit test `chat_id`.

```bash
python3 -m product_intel.feishu_message_send_adapter_mock \
  --handoff-message product_intel/output_next_round/feishu_ops_handoff_message.md \
  --upload-receipt product_intel/output_next_round/feishu_real_upload_single_receipt.json \
  --mock-token-csv product_intel/output_next_round/feishu_upload_mock_attachment_tokens.csv \
  --output-dir product_intel/output_next_round
```

Run the message send mock regression test:

```bash
python3 -m product_intel.test_feishu_message_send_adapter_mock
```

## Run

From `/Users/michaelchui/Desktop/openclaw_tools`:

```bash
python3 -m product_intel.test_product_fact_sheet
python3 -m product_intel.test_batch_fact_sheet
python3 -m product_intel.test_input_adapter
python3 -m product_intel.test_decision_table
python3 -m product_intel.test_manager_payload
python3 -m product_intel.test_run_product_intel
python3 -m product_intel.test_csv_profile
python3 -m product_intel.test_service_handler
python3 -m product_intel.run_product_intel --input product_intel/mock_products.csv --source mock --market de --output-dir product_intel/output
python3 -m product_intel.run_product_intel --input product_intel/mock_products.csv --source auto --profile-only
python3 -m product_intel.run_product_intel --input product_intel/mock_products.csv --source auto --market de --output-dir product_intel/output
python3 -m py_compile product_intel/product_fact_sheet.py product_intel/qa_schema.py product_intel/hook_library.py product_intel/opportunity_score.py product_intel/test_product_fact_sheet.py
python3 -m py_compile product_intel/product_fact_sheet.py product_intel/hook_library.py product_intel/opportunity_score.py product_intel/batch_fact_sheet.py product_intel/export_utils.py product_intel/test_batch_fact_sheet.py
python3 -m py_compile product_intel/product_fact_sheet.py product_intel/hook_library.py product_intel/opportunity_score.py product_intel/batch_fact_sheet.py product_intel/export_utils.py product_intel/input_adapter.py product_intel/csv_loader.py product_intel/test_input_adapter.py
python3 -m py_compile product_intel/product_fact_sheet.py product_intel/hook_library.py product_intel/opportunity_score.py product_intel/batch_fact_sheet.py product_intel/export_utils.py product_intel/input_adapter.py product_intel/csv_loader.py product_intel/decision_table.py product_intel/export_decision_table.py product_intel/test_decision_table.py
python3 -m py_compile product_intel/product_fact_sheet.py product_intel/hook_library.py product_intel/opportunity_score.py product_intel/batch_fact_sheet.py product_intel/export_utils.py product_intel/input_adapter.py product_intel/csv_loader.py product_intel/decision_table.py product_intel/export_decision_table.py product_intel/manager_payload.py product_intel/export_manager_payload.py product_intel/test_manager_payload.py
python3 -m py_compile product_intel/product_fact_sheet.py product_intel/hook_library.py product_intel/opportunity_score.py product_intel/batch_fact_sheet.py product_intel/export_utils.py product_intel/input_adapter.py product_intel/csv_loader.py product_intel/decision_table.py product_intel/export_decision_table.py product_intel/manager_payload.py product_intel/export_manager_payload.py product_intel/run_product_intel.py product_intel/test_run_product_intel.py
python3 -m py_compile product_intel/product_fact_sheet.py product_intel/hook_library.py product_intel/opportunity_score.py product_intel/batch_fact_sheet.py product_intel/export_utils.py product_intel/input_adapter.py product_intel/csv_loader.py product_intel/excel_loader.py product_intel/csv_profile.py product_intel/export_csv_profile.py product_intel/decision_table.py product_intel/export_decision_table.py product_intel/manager_payload.py product_intel/export_manager_payload.py product_intel/run_product_intel.py product_intel/service_handler.py product_intel/feishu_product_intel_bot.py product_intel/test_csv_profile.py product_intel/test_excel_loader.py product_intel/test_run_product_intel.py product_intel/test_service_handler.py product_intel/test_feishu_product_intel_bot.py
```

## Next

Future versions can replace the mock JSON loader with a real EchoTik client while keeping the Product Fact Sheet contract stable for product selection bots, Manager, Video Director, and QA workflows.
