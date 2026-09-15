import re

# Từ điển viết tắt và tiếng lóng tiếng Việt phổ biến
VIETNAMESE_ABBREVIATIONS = {
    r"\bko\b": "không",
    r"\bk\b": "không",
    r"\bkhg\b": "không",
    r"\bkh\b": "không",
    r"\bkhong\b": "không",
    r"\bđc\b": "được",
    r"\bdc\b": "được",
    r"\bduoc\b": "được",
    r"\bmn\b": "mọi người",
    r"\bng\b": "người",
    r"\bvs\b": "với",
    r"\bj\b": "gì",
    r"\bgi\b": "gì",
    r"\bbt\b": "biết",
    r"\bbiet\b": "biết",
    r"\bib\b": "nhắn tin",
    r"\binbox\b": "nhắn tin",
    r"\bstt\b": "trạng thái",
    r"\bntn\b": "như thế nào",
    r"\bthui\b": "thôi",
    r"\boke\b": "đồng ý",
    r"\bok\b": "đồng ý",
    r"\btks\b": "cảm ơn",
    r"\bthanks\b": "cảm ơn",
    r"\bcam on\b": "cảm ơn",
    r"\bns\b": "nói",
    r"\btl\b": "trả lời",
    r"\bh\b": "giờ",
    r"\bgio\b": "giờ",
    r"\bnhìu\b": "nhiều",
    r"\bnhiu\b": "nhiều",
    r"\bch\b": "chưa",
    r"\bthuii\b": "thôi",
    r"\bnta\b": "người ta",
    r"\bchug\b": "chung",
    r"\btrc\b": "trước",
    r"\bsauu\b": "sau",
    r"\bya\b": "dạ",
    r"\buh\b": "ừ",
    r"\buhm\b": "ừm"
}

def normalize_vietnamese_text(text: str) -> str:
    """
    Chuẩn hóa văn bản tiếng Việt để phát âm tự nhiên:
    1. Chuyển đổi từ viết tắt và teen-code sang tiếng Việt chuẩn
    2. Chuyển đổi đơn vị tiền tệ: 100k -> 100 nghìn, 2tr -> 2 triệu, 5ty -> 5 tỷ
    3. Chuyển đổi ký hiệu: % -> phần trăm, $ -> đô la
    """
    if not text:
        return ""

    processed = text

    # 1. Chuyển đổi đơn vị tiền tệ và số lượng
    # 100k, 50k -> 100 nghìn, 50 nghìn
    processed = re.sub(r'(\d+)\s*(?:k|K)\b', r'\1 nghìn', processed)
    # 2tr, 10tr, 1.5tr -> 2 triệu
    processed = re.sub(r'(\d+(?:[.,]\d+)?)\s*(?:tr|Tr|triệu)\b', r'\1 triệu', processed)
    # 5ty -> 5 tỷ
    processed = re.sub(r'(\d+(?:[.,]\d+)?)\s*(?:ty|tỷ|Ty)\b', r'\1 tỷ', processed)

    # 2. Ký hiệu phổ biến
    processed = re.sub(r'(\d+)\s*%', r'\1 phần trăm', processed)
    processed = re.sub(r'\$\s*(\d+(?:[.,]\d+)?)', r'\1 đô la', processed)
    processed = re.sub(r'(\d+(?:[.,]\d+)?)\s*\$', r'\1 đô la', processed)

    # 3. Chuẩn hóa từ viết tắt
    for pattern, replacement in VIETNAMESE_ABBREVIATIONS.items():
        processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)

    # 4. Chuẩn hóa khoảng trắng
    processed = re.sub(r'[ \t]+', ' ', processed)
    return processed.strip()
