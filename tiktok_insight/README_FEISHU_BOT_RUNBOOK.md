# Feishu TikTok Insight Bot Runbook

用于记录 TikTok Insight 飞书 Bot 的启动、测试、排障和注意事项。

当前链路：

飞书群消息
→ Cloudflare Tunnel
→ 本地 Feishu Bot 服务（8770）
→ 本地 Insight HTTP 分析服务（8765）
→ Apify / QWEN
→ 飞书回复短版报告
→ 本地 reports 目录保存完整报告

---

## 1. 三个必须运行的服务

### Tab A：Insight HTTP 分析服务

作用：真正执行 TikTok 素材分析任务。

启动：

    cd /Users/michaelchui/Desktop/openclaw_tools/tiktok_insight
    ./start_http_server.sh

检查：

    curl -s http://127.0.0.1:8765/health | python3 -m json.tool

正常应看到：

    "status": "ok"
    "running_jobs": 0

如果 running_jobs 是 1，说明当前已有任务在跑，不要重复提交。

---

### Tab B：Feishu Bot 服务

作用：接收飞书事件、提交分析任务、等待结果并回复飞书。

启动：

    cd /Users/michaelchui/Desktop/openclaw_tools/tiktok_insight
    ./start_feishu_bot.sh

检查：

    curl -s http://127.0.0.1:8770/health | python3 -m json.tool

任务运行期间不要重启 Tab B，否则 Tab A 可能会生成报告，但飞书最终回复会丢。

---

### Tab C：Cloudflare 临时 Tunnel

作用：把本地 8770 服务暴露给飞书后台事件回调。

启动：

    cd /Users/michaelchui/Desktop/openclaw_tools/tiktok_insight
    ./start_cloudflare_tunnel.sh

启动后复制生成的 trycloudflare 地址，例如：

    https://xxxxx.trycloudflare.com

飞书后台事件请求地址必须填：

    https://xxxxx.trycloudflare.com/feishu/events

不要只填根域名，否则会出现：

    Challenge code 没有返回

---

## 2. 每次启动顺序

1. 确认 Clash 节点能访问 TikTok。推荐台湾 / 日本 / 新加坡 / 美国，不建议香港。
2. 启动 Tab A：./start_http_server.sh
3. 启动 Tab B：./start_feishu_bot.sh
4. 启动 Tab C：./start_cloudflare_tunnel.sh
5. 把 Tab C 生成的新 URL 填到飞书后台，路径必须带 /feishu/events
6. 检查 8765、8770、Cloudflare 外网 health 是否正常
7. 飞书发测试消息

---

## 3. 飞书测试模板

在飞书测试群里 @Content Analyzer，并发送：

市场：DE

商品：ALLPOWERS tragbare Energiezentrale R600, 600 W, 299 Wh, LiFePO4-Akku, mobiler Netzteil geeignet für Garten, Reise, Camping und Wohnmobil, Notstromversorgungsgerät

商品核心卖点：600W tragbare Energiezentrale, 299Wh Kapazität, LiFePO4-Akku, geeignet für Garten, Reise, Camping und Wohnmobil, mobile Stromversorgung für mehrere Geräte, Notstromversorgung für Outdoor- und Alltagssituationen, kombinierbar mit Solarpanel zum Aufladen im Freien

体裁：视频

视频链接：https://www.tiktok.com/...

分析目标：分析这条德国 TikTok 视频素材为什么能起量，重点拆解前3秒钩子、视频结构、商品露出、评论区反馈、用户购买/质疑点，并给出图文团队和视频团队可复刻的方向。

补充信息：飞书Bot正式联调测试 20260428-TEST001

注意：每次测试建议修改补充信息里的编号，避免被内容去重拦截。

---

## 4. 使用规则

### 规则 1：一次只跑一个任务

当前 HTTP 分析服务是单任务模式。提交前先检查：

    curl -s http://127.0.0.1:8765/health | python3 -m json.tool

只有 running_jobs 为 0 时再提交。

如果 running_jobs 为 1，继续提交会出现 HTTP 429 busy。

---

### 规则 2：任务运行期间不要重启服务

任务开始后，不要重启 Tab A / Tab B / Tab C。

尤其不要重启 Tab B。Tab B 负责等 Tab A 跑完后回飞书，重启后最终回复会丢。

---

### 规则 3：同一条内容 10 分钟内会被去重

Bot 已加入内容指纹去重：

同一个 chat_id + 同一段消息正文，10 分钟内只处理一次。

如果要重复测试同一条素材，在最后加不同测试编号：

    补充信息：测试编号 001
    补充信息：测试编号 002

---

## 5. 输出文件位置

完整深度报告：

    reports/*_report_qwen.md

查看最新报告：

    ls -lt reports/*_report_qwen.md | head

查看某个报告：

    cat reports/xxx_report_qwen.md

分析 prompt：

    reports/*_analysis_prompt.md

数据包：

    reports/*_data_packet.json

视频 contact sheet：

    reports/*_contact_sheet.jpg

HTTP job 文件：

    http_jobs/*.json

查看最新 job：

    LATEST_JOB=$(ls -t http_jobs/*.json | head -1)
    echo "$LATEST_JOB"
    cat "$LATEST_JOB" | python3 -m json.tool | tail -120

飞书日志：

    feishu_logs/*_event.json
    feishu_logs/*_error.json
    feishu_logs/*_duplicate_content.json

---

## 6. 常见问题

### 飞书没有回复

可能原因：

1. Tab B 没启动
2. Tab C tunnel 没启动
3. 飞书后台 URL 没更新
4. 被内容去重拦截
5. Tab B 在任务运行期间被重启过

排查：

    curl -s http://127.0.0.1:8770/health | python3 -m json.tool
    ls -lt feishu_logs | head
    ls -lt feishu_logs | grep duplicate_content | head

---

### 飞书报 502

通常是 Tab A 分析服务没启动或 8765 不通。

处理：

    curl -s http://127.0.0.1:8765/health | python3 -m json.tool
    ./start_http_server.sh

---

### Challenge code 没有返回

飞书后台 URL 填错。

错误：

    https://xxxxx.trycloudflare.com

正确：

    https://xxxxx.trycloudflare.com/feishu/events

---

### HTTP 429 busy

说明当前已有任务在运行。

检查：

    curl -s http://127.0.0.1:8765/health | python3 -m json.tool

等 running_jobs 变成 0 后再提交。

如果 running_jobs 长时间为 1，可能有任务卡死。查看最新 job：

    LATEST_JOB=$(ls -t http_jobs/*.json | head -1)
    cat "$LATEST_JOB" | python3 -m json.tool | tail -120

确认卡死后，可以重启 Tab A，并移走 running job：

    lsof -ti :8765 | xargs kill -9 2>/dev/null || true

    mkdir -p http_jobs_stuck_archive
    python3 - <<'PY'
import json, glob, shutil
from pathlib import Path

archive = Path("http_jobs_stuck_archive")
archive.mkdir(exist_ok=True)

for f in glob.glob("http_jobs/*.json"):
    p = Path(f)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    if d.get("status") == "running":
        shutil.move(str(p), str(archive / p.name))
        print("moved stuck running job:", p)
PY

    ./start_http_server.sh

---

### TikTok 视频下载失败 / SSL_ERROR_SYSCALL

典型报错：

    LibreSSL SSL_connect: SSL_ERROR_SYSCALL in connection to v19.tiktokcdn-us.com:443

通常是当前代理节点无法访问 TikTokCDN。

处理：

1. 切换到台湾 / 日本 / 新加坡 / 美国节点
2. 不建议香港节点
3. 重新跑任务

---

### 完整报告生成了，但飞书没有最终回复

如果本地能看到：

    cat reports/xxx_report_qwen.md

但飞书没有收到最终回复，通常是 Tab B 在任务运行期间被重启或中断。

处理：

本次直接从 reports 目录查看报告。下一次任务运行期间不要重启 Tab B。

---

## 7. 当前飞书短版回复格式

飞书默认返回短版报告：

【1. 结论先行】
【2. 素材爆点拆解】
【3. 商品匹配与转化问题】
【4. 主要转化阻力】
【5. 下一条图文建议】
【6. 下一条视频建议】
【7. 最终动作建议】

完整深度报告保存在本地 reports 目录。

---

## 8. 当前限制

1. Cloudflare URL 是临时地址，每次 Tab C 重启后都要更新飞书后台。
2. 当前依赖这台 Mac，电脑关机 / 休眠后 Bot 不可用。
3. 当前一次只能跑一个分析任务。
4. 任务运行期间不要重启 Tab B，否则飞书最终回复可能丢。
5. 同一条内容 10 分钟内会被内容去重拦截。

---

## 9. 后续可优化方向

1. 固定 Cloudflare URL：需要域名 + Cloudflare Named Tunnel。
2. 后台守护运行：可以用 nohup / tmux / LaunchAgent。
3. 断点续回：Tab B 重启后自动扫描已 success 但未回飞书的 job，并补发结果。
4. 队列化多任务：允许多条任务排队，而不是直接 429 busy。

---

## 10. Git 保存建议

每次稳定修改后保存：

    git status
    git diff --stat
    git add .
    git commit -m "stabilize feishu tiktok insight bot"
