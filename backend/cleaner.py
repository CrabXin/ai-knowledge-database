"""数据清洗模块（实训模块二）。

核心功能：把带单位的数量字符串统一为整数。
例如 B 站常见展示："1.1万" -> 11000，"2.3亿" -> 230000000，"-" -> 0。
即便接口已返回整数，本模块仍对所有数值字段做归一化，保证 CSV 中是纯数字。
"""
import re

import pandas as pd

# 单位换算表
_UNIT = {"万": 10000, "亿": 100000000}


def parse_count(value) -> int:
    """将单个数量值解析为整数。

    支持以下输入：
    - 整数/浮点数：直接取整
    - "1.1万" / "2.3亿"：按单位换算
    - "1,234" / "1234次播放"：去除非数字字符
    - "-" / "" / None：返回 0
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        # NaN 判定
        if isinstance(value, float) and value != value:
            return 0
        return int(value)
    text = str(value).strip()
    if text in ("", "-", "—"):
        return 0
    # 处理带单位的情况，如 "1.1万"
    for unit, factor in _UNIT.items():
        if unit in text:
            num = re.findall(r"[\d.]+", text)
            if num:
                return int(float(num[0]) * factor)
            return 0
    # 普通数字：去除逗号、"次播放"等非数字字符
    digits = re.findall(r"[\d.]+", text)
    if not digits:
        return 0
    return int(float(digits[0]))


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """对整个采集结果做清洗。

    - 数值字段统一转为整数（"万""亿"换单位）
    - 去除标题中的多余空白与 HTML 高亮标签 <em>...</em>
    """
    numeric_cols = ["play", "danmaku", "reply", "favorite", "coin", "share", "like", "duration"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_count)

    if "title" in df.columns:
        # B站搜索接口标题含 <em class="keyword">关键词</em> 高亮标签，去掉
        df["title"] = (
            df["title"].astype(str)
            .str.replace(r"<[^>]+>", "", regex=True)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )
    return df
