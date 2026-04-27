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

    input_info = data_packet.get("input", payload)
    metadata = data_packet.get("metadata", {})
    stats = metadata.get("stats", {})
    comments = data_packet.get("comments", {})
    top_comments = comments.get("top_comments_by_likes", [])[:30]
    availability = data_packet.get("data_availability", {})
    visual_packet = data_packet.get("visual_packet", {})
    slideshow_images = data_packet.get("slideshow_images", {})
    known_performance = input_info.get("known_performance", {})

    hashtags = metadata.get("hashtags", [])
    hashtag_text = ", ".join([f"#{h.get('name')}" for h in hashtags if h.get("name")])

    comment_lines = []
    for idx, c in enumerate(top_comments, start=1):
        text = safe_text(c.get("text"))
        like_count = c.get("like_count")
        reply_count = c.get("reply_count")
        liked_by_author = c.get("liked_by_author")
        comment_lines.append(
            f"{idx}. {text} | likes={like_count}, replies={reply_count}, liked_by_author={liked_by_author}"
        )

    prompt = f"""# TikTok 图文 / Slideshow 单条素材商业洞察分析任务

你是 TikTok Shop 图文素材洞察分析师。请基于下面的信息，分析这条 TikTok 图文爆款素材。

你的任务不是泛泛总结，而是综合判断：

1. 这条图文为什么能获得高播放/高互动
2. 首图钩子是否强
3. 图文序列是否能制造停留、滑动和购买兴趣
4. 评论区是否有真实购买意图或用户顾虑
5. 商品卖点和素材表达是否匹配
6. 我们图文团队应该如何复刻或优化

重要要求：
- 不要只做情绪分析。
- 不要把评论区少量极端评论当成主流。
- 不要编造评论区没有出现的观点。
- 必须区分“素材爆点”和“商品购买理由”。
- 必须判断这条图文是否存在“高播放但低转化”的风险。
- 图文页数不一定是3页，请根据实际 slideshow 图片数量分析。

【事实边界规则】
1. 只能把用户输入的商品名称、商品核心卖点、metadata、评论、视觉图片中明确出现的信息当作事实。
2. 不得自行编造商品参数、价格、折扣、物流、质保、材质认证、尺寸以外的新规格、适合所有用户/人群/场景、100%有效等绝对化承诺。
3. 如果需要这些信息，必须写成“需商品团队确认”，不能写成确定事实。
4. FAQ 回复里不能承诺未确认信息。
5. 如果评论区问到无法确认的问题，应输出谨慎回复模板，而不是直接给出具体数值或承诺。

【更严格的素材输出边界】
- 在“下一条图文建议”“FAQ回复建议”“最终动作建议”中，也必须遵守事实边界规则。
- 不得输出未经确认的履约承诺，包括但不限于：德国仓发货、库存有限、质保年限、退换货政策、包邮、快速配送。
- 不得补充商品未输入的材质认证、安全认证、防滑、耐用、耐咬、适合所有用户/人群/场景等强承诺。
- 

【通用品类额外事实边界】
- 不得把上一条素材/上一品类的专属规则套用到当前商品；所有判断必须围绕当前商品名称、当前商品核心卖点、当前图文画面、当前评论区与当前 metadata。
- 不得自行补充材质、尺寸、认证、授权、物流、质保、价格、折扣、库存、适用人群、适用场景等未确认信息。
- 如果评论区出现材质、尺寸、授权、品牌/IP、真假、物流、洗护、安装、兼容性、适配性、安全性等问题，只能写成“需商品团队确认 / 以商品页为准 / 建议咨询客服”，不得直接给确定答案。
- 如果素材涉及品牌、IP、联名、饮料、影视、动漫、球队、学校、明星等元素，不得默认存在官方授权；必须把“品牌/IP授权或合规风险”作为待确认项或风险点。
- 不得把用户评论中的质疑直接当作事实；评论只能作为“用户顾虑/潜在转化阻力”。
- 对高播放素材，必须判断它是“情绪/话题型爆款”“商品卖点型爆款”还是“转化型爆款”，并说明可能的高播放低转化风险。


---

## 0. 用户输入信息

- 市场：{input_info.get("market")}
- 商品名称：{input_info.get("product")}
- 商品核心卖点：{input_info.get("product_core_selling_points")}
- 体裁：{input_info.get("format")}
- 素材链接：{input_info.get("material_url")}
- 分析目标：{input_info.get("analysis_goal")}
- 已知表现/补充数据：{json.dumps(known_performance, ensure_ascii=False)}

---

## 1. 本次可用数据

- comments_available：{availability.get("comments_available")}
- comments_count_scraped：{availability.get("comments_count_scraped")}
- metadata_available：{availability.get("metadata_available")}
- slideshow_images_available：{availability.get("slideshow_images_available")}
- slideshow_visual_packet_available：{availability.get("slideshow_visual_packet_available")}

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

## 3. 图文视觉信息

请结合随附 contact sheet 图片进行分析。

- contact_sheet_path：{visual_packet.get("contact_sheet_path")}
- image_count：{slideshow_images.get("image_count")}
- visual_packet_type：{visual_packet.get("type")}

你需要重点分析：
- Slide 01 的首图钩子是什么
- 前 2 张图是否足够让人继续滑
- 商品是否清楚露出
- 每一页承担什么功能：钩子 / 证明 / 使用场景 / 情绪 / 购买理由 / CTA
- 是否有图文停留力
- 哪些页面值得复刻
- 哪些页面可能导致跳出
- 是否更像情绪/话题内容，还是商品内容
- 评论区关注点是否和图文表达一致

---

## 4. 评论区数据

- 抓取评论数：{comments.get("count")}

### 高赞评论 / 代表评论

{chr(10).join(comment_lines)}

---

# 请按下面格式输出报告

# TikTok 图文爆款商业洞察报告

## 0. 本次可用数据
- 评论：
- metadata：
- 图文图片：
- 已知表现：
- 分析限制：

## 1. 结论先行
- 是否值得复刻：
- 爆款核心原因：
- 最大机会点：
- 最大风险点：
- 适合部门：
- 推荐优先级：

## 2. 图文结构拆解
- 体裁：
- 首图钩子：
- 图文页数：
- 每页功能拆解：
- 商品露出方式：
- 核心卖点表达：
- 停留力来源：
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
- 素材是否解释了当前商品的购买理由：
- 是否存在“情绪/话题内容强，但商品购买理由弱”的风险：
- 是否有高播放低转化风险：
- 主要转化断点：

## 5. 转化阻力
- 价格阻力：
- 材质/耐用性阻力：
- 用户是否会真正使用/接受的阻力：
- 尺寸/空间阻力：
- 家居美观阻力：
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

## 8. 评论回复 / FAQ 建议

| 用户问题 | 推荐回复 |
|---|---|

FAQ 回复必须保守，不得编造未确认参数。如信息不足，回复应引导用户查看商品页规格或咨询客服。

## 9. 最终动作建议
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
        "contact_sheet_path": visual_packet.get("contact_sheet_path"),
        "comments_count": comments.get("count"),
        "image_count": slideshow_images.get("image_count"),
        "product": input_info.get("product"),
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
