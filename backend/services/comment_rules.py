"""Local keyword matching and comment drafts. This module never sends messages."""

import copy
import json
from pathlib import Path
import re
import string
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from backend.utils.text_matching import normalize_text, contains_phrase


LIVE_COMMENTS_ENABLED = False
DEFAULT_BUYER_PHRASES = [
    "có bác nào có", "cần mua", "muốn mua", "tìm mua", "ai bán", "mua ở đâu", "xin giá",
    "đang cần mua", "đang muốn mua", "định mua", "dự định mua", "dự tính mua",
    "có nhu cầu mua", "cần tìm mua", "tìm chỗ mua", "tìm nơi bán", "tìm cửa hàng",
    "nhờ tìm giúp", "nhờ tư vấn mua", "xin tư vấn mua", "tư vấn giúp mình",
    "tư vấn giúp em", "các bác tư vấn", "mọi người tư vấn", "nên chọn mẫu nào",
    "nên chọn hãng nào", "loại nào phù hợp", "mẫu nào phù hợp", "xin địa chỉ mua",
    "địa chỉ bán uy tín", "chỗ nào uy tín", "shop nào uy tín", "bên nào cung cấp",
    "có bên nào bán", "có shop nào bán", "bác nào có sẵn", "có hàng sẵn không",
    "còn mẫu này không", "còn mã này không", "cho xin giá", "cho mình xin giá",
    "cho em xin giá", "xin báo giá", "giá tốt nhất", "giá khoảng bao nhiêu",
    "bao nhiêu một chiếc", "mua tặng", "sắm mới", "nâng cấp lên", "cần gấp",
    "muốn đặt mua", "cần đặt hàng", "đặt mua ở đâu", "mua ở chỗ nào",
]
DEFAULT_PRODUCTS = [
    "bếp từ", "bếp điện từ", "bếp hồng ngoại", "máy hút mùi", "hút mùi",
    "máy rửa bát", "máy rửa chén", "máy lọc nước", "lò nướng", "lò vi sóng",
]


def rule(key, name, keywords, reply, *, manual=False, needs_intent=False):
    return dict(id=key, name=name, keywords=keywords, reply=reply,
                manual=manual, needs_intent=needs_intent)


# The first matching rule wins. More specific needs precede general buying.
DEFAULT_RULES = [
    rule("replacement", "Đổi hoặc thay bếp", ["thay bếp", "đổi bếp", "đổi sang bếp", "thay mới"],
         "Bác cho em xin mã bếp cũ và kích thước khoét đá nhé. Em kiểm tra mẫu {san_pham} phù hợp rồi báo bác ạ."),
    rule("repair", "Hỏng hoặc cần sửa — duyệt thủ công", ["bị lỗi", "báo lỗi", "lỗi e0", "lỗi e1", "lỗi e2", "không lên nguồn", "không nhận nồi", "cần sửa", "sửa bếp", "bị hỏng"],
         "Bác cho em xin mã máy và tình trạng lỗi của {san_pham} nhé, em kiểm tra hướng hỗ trợ phù hợp ạ.", manual=True),
    rule("accessory", "Phụ kiện hoặc linh kiện — duyệt thủ công", ["mua nồi", "mua chảo", "mua mặt kính", "thay mặt kính", "mua bo mạch", "mua linh kiện", "tìm linh kiện", "cần phụ kiện"],
         "Bác ib em tên phụ kiện cần tìm và mã {san_pham} đang dùng nhé, em kiểm tra độ tương thích và khả năng cung cấp rồi báo lại ạ.", manual=True),
    rule("wholesale", "Mua sỉ hoặc tìm nguồn", ["lấy sỉ", "giá sỉ", "nguồn hàng", "nhập sỉ", "tìm nhà phân phối", "tìm đại lý", "cần nguồn"],
         "Bác ib em dòng {san_pham} và số lượng dự kiến nhé, em kiểm tra chính sách và báo lại bác ạ."),
    rule("installation", "Lắp đặt hoặc khoét đá", ["cần lắp", "thợ lắp", "lắp đặt", "khoét đá"],
         "Bác ở khu vực nào và đang dùng mã {san_pham} nào ạ? Bác ib thông tin để em kiểm tra khả năng hỗ trợ lắp đặt nhé.", manual=True),
    rule("used", "Tìm hàng cũ hoặc thanh lý", ["cũ", "đã qua sử dụng", "second hand", "thanh lý"],
         "Bác ib em mẫu {san_pham} và mức giá mong muốn nhé, em kiểm tra xem có lựa chọn phù hợp rồi báo lại ạ.", needs_intent=True),
    rule("budget", "Tìm theo ngân sách", ["ngân sách", "tài chính", "tầm giá", "dưới", "tầm", "trong khoảng"],
         "Bác ib em ngân sách và nhu cầu dùng {san_pham} nhé, em tư vấn mẫu phù hợp rồi báo giá cụ thể ạ.", needs_intent=True),
    rule("delivery", "Hỏi giao hàng", ["ship về", "giao về", "giao đến", "ship tỉnh", "giao tỉnh", "giao hàng"],
         "Bác ib em mã {san_pham} và khu vực nhận hàng nhé, em kiểm tra giá cùng phương án giao hàng rồi báo bác ạ.", needs_intent=True),
    rule("price", "Hỏi giá", ["xin giá", "báo giá", "giá bao nhiêu", "bao nhiêu tiền", "giá thế nào", "giá sao", "giá với"],
         "Bác ib em mã {san_pham} hoặc gửi ảnh mẫu đang quan tâm nhé, em kiểm tra và báo giá cụ thể ạ."),
    rule("advice", "Tư vấn hoặc so sánh", ["tư vấn", "nên mua", "chọn loại nào", "loại nào tốt", "hãng nào tốt", "mua loại nào", "xin review", "xin đánh giá", "review giúp", "có tốt không"],
         "Bác cho em xin ngân sách và nhu cầu dùng {san_pham} nhé, em tư vấn vài mẫu để bác tham khảo ạ."),
    rule("availability", "Hỏi ai có hàng", ["có bác nào có", "bác nào có", "các bác có", "có ai có", "ai có", "bên nào có", "còn hàng", "có hàng không", "có sẵn không", "có bán không", "ở đâu có", "ai bán", "có ai bán", "bác nào bán", "shop nào bán", "shop nào có", "chỗ nào bán", "ở đâu bán", "bên nào bán"],
         "Bên em có ạ, bác ib em mã {san_pham} hoặc ảnh mẫu để em kiểm tra đúng hàng và báo giá nhé."),
    rule("buy", "Tìm mua chung", ["cần mua", "tìm mua", "muốn mua", "đang tìm", "mua ở đâu", "cần tìm", "cần một", "cần 1", "cần chiếc", "cần cái", "muốn sắm"],
         "Bác ib em mẫu {san_pham} đang cần và ngân sách nhé, em kiểm tra hàng rồi tư vấn, báo giá cho bác ạ."),
]

# Expand the general buying rule as well as acquisition keywords so matching posts
# survive the relevance filter. Existing user-saved rule files remain untouched.
DEFAULT_RULES[-1]["keywords"] = list(dict.fromkeys(DEFAULT_RULES[-1]["keywords"] + DEFAULT_BUYER_PHRASES))

EXCLUSIONS = [
    "không có nhu cầu", "không cần mua", "không mua nữa", "đã mua được", "đã tìm được",
    "đã mua rồi", "đã chốt", "đừng inbox", "không inbox", "không quảng cáo", "không nhận quảng cáo",
    "cần bán", "em bán", "mình bán", "tôi bán", "bên em bán", "em thanh lý", "mình thanh lý",
    "cần thanh lý", "xả kho", "tuyển dụng", "tuyển nhân viên",
]

CATALOG_REPLIES = {
    "availability": "Bác ib em sản phẩm {san_pham} đang hỏi nhé, em kiểm tra hàng và báo giá cụ thể ạ.",
    "price": "Bác ib em mẫu {san_pham} đang quan tâm nhé, em kiểm tra và báo giá riêng cho bác ạ.",
    "buy": "Bác ib em nhu cầu và ngân sách cho {san_pham} nhé, em kiểm tra hàng rồi tư vấn mẫu phù hợp ạ.",
    "advice": "Bác ib em nhu cầu sử dụng và ngân sách cho {san_pham} nhé, em tư vấn các mẫu phù hợp ạ.",
    "budget": "Bác ib em ngân sách và nhu cầu dùng {san_pham} nhé, em kiểm tra mẫu phù hợp rồi báo giá riêng ạ.",
    "used": "Bác ib em mẫu {san_pham} và mức giá mong muốn nhé, em kiểm tra khả năng cung cấp rồi báo lại ạ.",
    "delivery": "Bác ib em mẫu {san_pham} và khu vực nhận hàng nhé, em kiểm tra giá và phương án giao hàng ạ.",
    "wholesale": "Bác ib em mẫu {san_pham} và số lượng dự kiến nhé, em kiểm tra chính sách rồi báo lại ạ.",
    "replacement": "Bác ib em mã sản phẩm cũ và nhu cầu thay {san_pham} nhé, em kiểm tra lựa chọn phù hợp ạ.",
    "repair": "Bác ib em mã và tình trạng lỗi của {san_pham} nhé, em kiểm tra khả năng hỗ trợ rồi báo lại ạ.",
    "installation": "Bác ib em mã {san_pham} và khu vực lắp đặt nhé, em kiểm tra khả năng hỗ trợ rồi báo lại ạ.",
    "accessory": "Bác ib em phụ kiện cần tìm và mã {san_pham} đang dùng nhé, em kiểm tra độ tương thích rồi báo lại ạ.",
}


def validate_rules(rules):
    if not isinstance(rules, list) or not rules:
        raise ValueError("Cần ít nhất một quy tắc.")
    ids = set()
    for item in rules:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].strip() for key in ("id", "name", "reply")):
            raise ValueError("Mỗi quy tắc cần mã, tên và nội dung trả lời.")
        if item["id"] in ids:
            raise ValueError("Mã quy tắc bị trùng.")
        ids.add(item["id"])
        if any(field in item and not isinstance(item[field], bool) for field in ("manual", "needs_intent")):
            raise ValueError("Các cờ duyệt thủ công và cần ý định mua phải là true hoặc false.")
        if not isinstance(item.get("keywords"), list) or not item["keywords"] or not all(isinstance(word, str) and normalize_text(word) for word in item["keywords"]):
            raise ValueError(f"Quy tắc {item['name']} cần danh sách từ khóa hợp lệ.")
        try:
            fields = list(string.Formatter().parse(item["reply"]))
            if any(name is not None and (name != "san_pham" or spec or conversion) for _, name, spec, conversion in fields):
                raise ValueError()
        except ValueError:
            raise ValueError("Mẫu trả lời chỉ hỗ trợ biến {san_pham}.") from None
    return rules


def scan_keywords(rules=None):
    return list(dict.fromkeys(word for item in (rules or DEFAULT_RULES) for word in item["keywords"]))


def suggest_comment(message, rules=None, products=None, catalog=None):
    rules = DEFAULT_RULES if rules is None else validate_rules(rules)
    products = DEFAULT_PRODUCTS if products is None else products
    result = dict(status="skipped", rule_id="", rule_name="", matched_keywords=[], product="", comment="", reason="")
    if not normalize_text(message):
        return dict(result, reason="Bài viết không có nội dung.")
    excluded = next((word for word in EXCLUSIONS if contains_phrase(message, word)), None)
    if excluded or normalize_text(message).startswith("thanh ly "):
        return dict(result, reason=f"Loại trừ: {excluded or 'bài thanh lý/bán hàng'}.")
    normalized = normalize_text(message)
    catalog_match = catalog.match(message) if catalog is not None else None
    product = catalog_match["label"] if catalog_match else None
    if catalog is None:
        product = next((word for word in sorted(products, key=lambda value: len(normalize_text(value)), reverse=True)
                    if contains_phrase(message, word)
                    and not re.search(r"\b(?:khong (?:mua|lay|chon|dung|can)|khong phai|ngoai tru) "
                                      + re.escape(normalize_text(word)) + r"\b", normalized)), None)
    if not product:
        return dict(result, reason="Không có sản phẩm trong danh sách quan tâm.")
    result["product"] = product
    if catalog_match:
        result["catalog_match"] = catalog_match
        result["catalog_source"] = catalog.source.get("filename", "")
    # Broad words such as 'cũ', 'tầm', 'dưới' need a separate buying/question cue.
    intent = any(contains_phrase(message, word) for item in rules if not item.get("needs_intent") for word in item["keywords"])
    for item in rules:
        matched = [word for word in item["keywords"] if contains_phrase(message, word)]
        if matched and (intent or not item.get("needs_intent")):
            template = item["reply"]
            if catalog_match and any(default["id"] == item["id"] and default["reply"] == template for default in DEFAULT_RULES):
                template = CATALOG_REPLIES.get(item["id"], template)
            review = item.get("manual") or (catalog_match and catalog_match["requires_review"])
            reason = catalog_match["reason"] if catalog_match and catalog_match["reason"] else "Chỉ là bản nháp, chưa gửi Facebook."
            return dict(result, status="manual_review" if review else "draft",
                        rule_id=item["id"], rule_name=item["name"], matched_keywords=matched,
                        comment=template.format(san_pham=product), reason=reason)
    return dict(result, reason="Không có từ khóa phù hợp để tạo bình luận.")


def post_identity(url):
    parsed = urlparse(str(url or ""))
    if (parsed.hostname or "").lower() not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        return str(url or "")
    query = parse_qs(parsed.query)
    identity = {key: query[key][0] for key in ("story_fbid", "id") if query.get(key)}
    path = parsed.path.rstrip("/")
    if not path.endswith(".php"):
        path += "/"
    return urlunparse(("https", "www.facebook.com", path, "", urlencode(identity), ""))


def preview_comments(posts, rules=None, products=None, catalog=None):
    results, seen = [], set()
    for post in posts:
        suggestion = suggest_comment(post.get("message", ""), rules, products, catalog)
        key = post_identity(post.get("url", ""))
        if key and key in seen:
            suggestion.update(status="duplicate", comment="", reason="Trùng bài viết trong lượt xem trước.")
        elif key:
            seen.add(key)
        results.append(dict(post, **suggestion))
    return results


class CommentRuleStore:
    def __init__(self, path=Path("data/comment_rules.json")):
        self.path = path

    def load(self):
        if not self.path.exists():
            return copy.deepcopy(DEFAULT_RULES)
        return validate_rules(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, rules):
        validate_rules(rules)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
