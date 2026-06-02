"""Build small realistic Excel fixtures for adapter regression tests."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


PACKAGE_DIR = Path(__file__).resolve().parent

FIXTURES = {
    "mock_echotik_products.xlsx": {
        "sheet": "EchoTik Export",
        "headers": ["EchoTik商品ID", "商品名称", "商品类目", "当前售价", "近7天销量", "成交额", "达人佣金率", "店铺名", "近7天增长"],
        "rows": [
            ["echo-1", "Echo Pet Brush", "Pet Supplies", 12.9, 820, 10578, "12%", "Echo Store", "24%"],
            ["echo-2", "Echo Storage Bag", "Home", 8.5, 430, 3655, "10%", "Echo Home", "16%"],
            ["echo-3", "Echo Mini Fan", "Electronics", 16.8, 1200, 20160, "9%", "Echo Tech", "31%"],
        ],
    },
    "mock_fastmoss_products.xlsx": {
        "sheet": "FastMoss Export",
        "headers": ["FastMoss商品ID", "title", "leaf_category", "sale_price", "sales", "近7日GMV", "commission %", "TikTok商品链接", "seller_name", "关联视频数"],
        "rows": [
            ["fm-1", "FastMoss Cat Bowl", "Pet Supplies", 15.9, 510, 8109, "11%", "https://example.com/fm-1", "FM Pet", 42],
            ["fm-2", "FastMoss Desk Lamp", "Home", 19.9, 390, 7761, "8%", "https://example.com/fm-2", "FM Home", 27],
            ["fm-3", "FastMoss Cable Set", "Electronics", 6.9, 920, 6348, "13%", "https://example.com/fm-3", "FM Tech", 65],
        ],
    },
    "mock_kalodata_products.xlsx": {
        "sheet": "KaLoData Export",
        "headers": ["KaLoData Product ID", "product_title", "category", "price", "30日销量", "30日GMV", "commission_rate", "merchant_name", "相关达人数", "score", "reviews"],
        "rows": [
            ["kalo-1", "KaLoData Travel Cup", "Kitchen", 10.9, 680, 7412, "10%", "Kalo Kitchen", 18, 4.7, 320],
            ["kalo-2", "KaLoData Phone Stand", "Electronics", 7.9, 760, 6004, "12%", "Kalo Tech", 23, 4.6, 255],
            ["kalo-3", "KaLoData Makeup Bag", "Beauty", 9.9, 440, 4356, "9%", "Kalo Beauty", 14, 4.8, 188],
        ],
    },
    "mock_manual_products.xlsx": {
        "sheet": "手工合并表",
        "headers": ["商品编号", "商品名", "叶子类目", "售价", "销量", "销售额", "佣金率", "商品链接", "商家名称", "数据来源", "近7日增长", "近30日增长", "带货视频数", "带货达人数", "商品评分", "评论数"],
        "rows": [
            ["manual-1", "手工收纳盒", "家居", 11.9, 350, 4165, "10%", "https://example.com/manual-1", "手工店铺", "manual", "12%", "25%", 16, 8, 4.7, 120],
            ["manual-2", "手工宠物碗", "宠物", 14.9, 280, 4172, "8%", "https://example.com/manual-2", "合并店铺", "manual", "9%", "18%", 11, 5, 4.6, 86],
            ["manual-3", "手工桌面风扇", "电子", 17.9, 620, 11098, "12%", "https://example.com/manual-3", "人工筛选店", "manual", "22%", "41%", 31, 12, 4.8, 205],
        ],
    },
}


def build_fixture(filename: str, fixture: dict) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = fixture["sheet"]
    sheet.append(fixture["headers"])
    for row in fixture["rows"]:
        sheet.append(row)
    path = PACKAGE_DIR / filename
    workbook.save(path)
    return path


def main() -> None:
    for filename, fixture in FIXTURES.items():
        print(build_fixture(filename, fixture))


if __name__ == "__main__":
    main()
