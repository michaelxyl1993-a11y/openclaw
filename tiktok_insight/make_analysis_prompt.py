import json
import hashlib
from pathlib import Path

BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "reports"

def cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def safe_text(value, fallback=""):
    if value is None:
        return fallback
    return str(value)

def main():
    input_path = BASE_DIR / "input_test.json"
    payload = read_json(input_path)

    material_url = payload["material_url"].strip()
    key = cache_key(material_url)

    data_packet_path = REPORT_DIR / f"{key}_data_packet.json"
    if not data_packet_path.exists():
        raise FileNotFoundError(f"Missing data packet: {data_packet_path}")

    data_packet = read_json(data_packet_path)

    # 重要：以 data_packet 里的 input 为准，因为你刚刚已经 refresh 过
    input_info = data_packet.get("input", payload)

    metadata = data_packet.get("metadata", {})
    stats = metadata.get("stats", {})
    comments = data_packet.get("comments", {})
    top_comments = comments.get("top_comments_by_likes", [])[:20]
    transcript = data_packet.get("transcripts", {}).get("best_transcript_text", "")
    transcript_lang = data_packet.get("transcripts", {}).get("best_transcript_language", "")
    contact_sheet_path = data_packet.get("visual_packet", {}).get("contact_sheet_path", "")
    frames = data_packet.get("video_frames", {})
    media = data_packet.get("media", {})
    availability = data_packet.get("data_availability", {})

    comment_lines = []
    for idx, c in enumerate(top_comments, start=1):
        text = safe_text(c.get("text"))
        like_count = c.get("like_count")
        reply_count = c.get("reply_count")
        liked_by_author = c.get("liked_by_author")
        comment_lines.append(
            f"{idx}. {text} | likes={like_count}, replies={reply_count}, liked_by_author={liked_by_author}"
        )

    hashtags = metadata.get("hashtags", [])
    hashtag_text = ", ".join([f"#{h.get('name')}" for h in hashtags if h.get("name")])

    prompt = f"""# TikTok 单条素材商业洞察分析任务

你是 TikTok Shop 素材洞察分析师。请基于下面的信息，分析这条 TikTok 单条素材。

你的任务不是泛泛总结，而是综合判断：

1. 素材本身为什么能获得反馈
2. 评论区是否有真实购买意图
3. 商品卖点和素材表达是否匹配
4. 用户为什么想买 / 为什么不买
5. 图文团队和视频团队应该如何复刻或优化
6. 这条素材是否值得团队继续学习

重要要求：
- 不要只做情绪分析。
- 不要把评论区少量极端评论当成主流。
- 不要编造评论区没有出现的观点。
- 必须区分“素材爆点”和“商品购买理由”。
- 必须判断这条视频是否存在“播放不错但转化弱”的风险。
- 如果素材画面主要展示配件、道具、场景元素、模特或情绪画面，但实际带货商品是另一个主商品，必须明确判断两者是否匹配，不能把配件/道具/场景元素误当成主商品。


【事实边界规则】
1. 只能把用户输入的商品名称、商品核心卖点、metadata、字幕、评论、视觉帧中明确出现的信息当作事实。
2. 不得自行编造或补充商品参数、材质、尺码、认证、授权、物流、质保、退换货、德国仓、价格、折扣、库存、套装内容、适用人群、适用场景。
3. 如果需要这些信息，必须写成“需商品团队确认”，不能写成确定事实。
4. FAQ 回复里不能承诺未确认信息。
5. 对商品关键规格、尺码、材质、认证、授权、适配对象、使用场景等内容，必须区分：
   - 已知事实
   - 基于商品名/评论的合理推断
   - 需要确认的信息

【更严格的素材输出边界】
- 在“下一条图文建议”“下一条视频建议”“FAQ回复建议”“最终动作建议”中，也必须遵守事实边界规则。
- 不得输出未经确认的具体数值或确定结论，包括但不限于：尺码对应关系、适合杯型、适合体型、材质成分、认证标准、洗护方式、库存、发货时效、退换政策、测试结果、使用效果。
- 不得输出未经确认的履约承诺，包括但不限于：德国仓发货、库存有限、质保年限、退换货政策、包装清单、认证标准、客服承诺。
- 如果为了表达结构需要举例，必须使用占位表达：
  “具体尺码/规格需商品团队确认”
  “具体效果因使用场景和个人情况而异”
  “如商品页确认支持德国仓/质保/退换/认证，可加入CTA”
- FAQ回复必须保守，不得把“需确认”的内容写成事实。
- 对“适合什么人/什么场景/什么尺码/什么搭配”的表达，只能给方向，不得给绝对承诺，除非商品输入或商品页信息中明确提供。
- 不得断言“无法通过TikTok广告审核”等平台审核结果；只能写“可能存在审核或信任风险”。
- 不得写未经确认的包装内容、配件清单、认证、材质、洗护、尺码对应、德国仓、退换政策。相关问题只能回复“以商品页为准 / 需商品团队确认 / 建议咨询客服”。
- 不得把商品输入中的卖点自行升级为更强承诺，例如把“舒适”写成“医学级健康”、把“透气”写成“夏天不闷汗”、把“露背”写成“完全隐形”、把“无线”写成“改善淋巴/健康”。


【FAQ/CTA 安全边界】
- FAQ 回复不得写“符合欧盟安全标准”“经过严格测试”“医学/健康改善”“无忧退换”“德国仓现货”“官方授权”“质检报告”等未确认表述。
- FAQ 回复不得给确定尺码换算，例如“75B=某码”，除非商品输入或商品页明确提供。只能写“建议查看商品页尺码表 / 咨询客服 / 根据下围和杯型选择”。
- CTA 里不得写未经确认的德国仓、限时折扣、库存、退换、质保、认证、尺码助手等承诺。
- 对用户质疑，只能基于评论和已知商品信息做保守回应；不能用未确认的认证、测试、履约政策来反驳。

---

## 0. 用户输入信息

- 市场：{input_info.get("market")}
- 商品名称：{input_info.get("product")}
- 商品核心卖点：{input_info.get("product_core_selling_points")}
- 体裁：{input_info.get("format")}
- 素材链接：{input_info.get("material_url")}
- 分析目标：{input_info.get("analysis_goal")}

---

## 1. 本次可用数据

- comments_available：{availability.get("comments_available")}
- comments_count_scraped：{availability.get("comments_count_scraped")}
- metadata_available：{availability.get("metadata_available")}
- media_file_available：{availability.get("media_file_available")}
- transcript_available：{availability.get("transcript_available")}
- video_frames_available：{availability.get("video_frames_available")}
- slideshow_images_available：{availability.get("slideshow_images_available")}

---

## 2. 素材 metadata

- post_id：{metadata.get("post_id")}
- submitted_url：{metadata.get("submitted_url")}
- canonical_url：{metadata.get("canonical_url")}
- caption：{metadata.get("caption")}
- hashtags：{hashtag_text}
- text_language：{metadata.get("text_language")}
- is_slideshow：{metadata.get("is_slideshow")}
- is_ad：{metadata.get("is_ad")}
- is_sponsored：{metadata.get("is_sponsored")}
- created_at：{metadata.get("created_at")}

### 作者信息

- author_name：{metadata.get("author", {}).get("name")}
- author_nickname：{metadata.get("author", {}).get("nickname")}
- followers：{metadata.get("author", {}).get("followers")}
- heart_count：{metadata.get("author", {}).get("heart_count")}
- video_count：{metadata.get("author", {}).get("video_count")}

### 互动数据

- play_count：{stats.get("play_count")}
- like_count：{stats.get("like_count")}
- comment_count：{stats.get("comment_count")}
- share_count：{stats.get("share_count")}
- collect_count：{stats.get("collect_count")}
- repost_count：{stats.get("repost_count")}

---

## 3. 视频素材信息

- media_path：{media.get("local_path")}
- file_size_bytes：{media.get("file_size_bytes")}
- download_method：{media.get("download_method")}
- width：{media.get("width")}
- height：{media.get("height")}
- duration：{media.get("duration")}
- cover_url：{media.get("cover_url")}

---

## 4. 视频视觉信息

请结合随附 contact sheet 图片进行分析。

- contact_sheet_path：{contact_sheet_path}
- frame_count：{frames.get("frame_count")}
- sampling_rule：{frames.get("sampling_rule")}

你需要重点分析：
- 前 3 秒钩子是什么
- 商品出现得早不早
- 视频是否清楚展示了商品用途
- 视频是否主要在卖当前商品，还是主要在卖配件、道具、场景元素、模特表现或情绪噱头
- 视觉证据是否足够
- 是否像真实生活素材，还是像硬广
- 哪些画面值得复刻
- 哪些画面不值得复刻

---

## 5. 视频字幕 / 口播文本

- transcript_language：{transcript_lang}

{transcript}

---

## 6. 评论区数据

- 抓取评论数：{comments.get("count")}

### 高赞评论 / 代表评论

{chr(10).join(comment_lines)}

---

# 请按下面格式输出报告

# TikTok 单条素材商业洞察报告

## 0. 本次可用数据
- 评论：
- metadata：
- 字幕/口播：
- 视频关键帧：
- 分析限制：

## 1. 结论先行
- 是否值得复刻：
- 推荐复刻方向：
- 最大机会点：
- 最大风险点：
- 适合部门：
- 推荐优先级：

## 2. 素材本身拆解
- 体裁：
- 前 3 秒钩子：
- 视频结构：
- 商品露出方式：
- 核心卖点表达：
- 视觉证据：
- CTA：
- 最大问题：

## 3. 评论区反馈分析
- 评论区主要在讨论什么：
- 购买意图等级：
- 高频问题：
- 高频质疑：
- 高频情绪：
- 代表性用户原话：

## 4. 商品匹配度分析
- 评论关注点是否匹配商品卖点：
- 素材是否解释了【当前商品】的购买理由：
- 素材是否过度依赖非主商品元素/单一视觉噱头：
- 是否有高播放低转化风险：
- 主要转化断点：

## 5. 转化阻力
- 价格阻力：
- 关键规格/适配阻力：
- 信任阻力：
- 使用场景阻力：
- 季节/场景阻力：
- 购买路径阻力：

## 6. 可复刻资产

### 可复刻 Hook
1.
2.
3.

### 可复刻画面/结构
1.
2.
3.

### 可复刻用户原话
1.
2.
3.

## 7. 下一条图文建议
不要强制 3 页，根据原素材和商品情况建议最佳页数。
- 建议页数：
- 每页结构：
- 首图方向：
- 商品展示方式：
- CTA：

注意：以下图文/视频建议只能使用已确认参数；如需使用具体数值，请标注“需商品团队确认”。

## 8. 下一条视频建议
- 0–3 秒：
- 3–8 秒：
- 8–15 秒：
- 15 秒后：
- 结尾 CTA：
- 是否适合 AI 视频：

## 9. FAQ 评论回复建议

| 用户问题 | 推荐回复 |
|---|---|

FAQ 回复必须保守，不得编造未确认参数。如信息不足，回复应引导用户查看商品页规格或咨询客服。

## 10. 最终动作建议
- 立即复刻 / 换角度测试 / 暂不投入：
- 给图文团队：
- 给视频团队：
- 给选品/商品同事：
"""

    output_path = REPORT_DIR / f"{key}_analysis_prompt.md"
    output_path.write_text(prompt, encoding="utf-8")

    print(json.dumps({
        "status": "success",
        "analysis_prompt_path": str(output_path),
        "contact_sheet_path": contact_sheet_path,
        "comments_count": comments.get("count"),
        "transcript_length": len(transcript or ""),
        "product": input_info.get("product"),
        "core_selling_points": input_info.get("product_core_selling_points")
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
