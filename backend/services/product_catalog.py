"""Search the company's saved product list, without treating it as live stock."""

from collections import Counter, defaultdict
from functools import lru_cache
import json
from pathlib import Path
import re

from backend.services.catalog_importer import DEFAULT_CATALOG_PATH
from backend.utils.text_matching import normalize_text, contains_phrase


CATEGORY_ALIASES = {
    "bep tu": ["bếp từ", "bếp điện từ", "bếp cảm ứng"],
    "bep gas": ["bếp gas", "bếp ga"], "gas": ["bếp gas", "bếp ga"],
    "hut mui": ["máy hút mùi", "hút mùi"],
    "may rua bat": ["máy rửa bát", "máy rửa chén"],
    "chau rua": ["chậu rửa", "chậu rửa bát", "chậu rửa chén", "chậu bếp"],
    "voi rua": ["vòi rửa", "vòi rửa bát", "vòi rửa chén", "vòi bếp", "vòi nóng lạnh"],
    "tu lanh": ["tủ lạnh"], "may giat": ["máy giặt", "tủ chăm sóc quần áo"],
    "may say": ["máy sấy", "máy sấy quần áo"],
    "lo nuong": ["lò nướng"], "lo vi song": ["lò vi sóng"],
    "loc nuoc": ["máy lọc nước", "lọc nước", "lọc nước ion kiềm"],
    "tivi": ["tivi", "ti vi", "tv"], "dieu hoa": ["điều hòa", "điều hoà", "máy lạnh"],
    "tu ruou": ["tủ rượu", "tủ rượu vang"], "quat": ["quạt", "quạt trần"],
    "cay nuoc": ["cây nước", "cây nước nóng lạnh"],
    "binh nong lanh": ["bình nóng lạnh", "máy nước nóng"],
    "ket sat": ["két sắt"], "hut am": ["máy hút ẩm", "hút ẩm"],
    "loc khong khi": ["máy lọc không khí", "lọc không khí"],
    "robot hut bui": ["robot hút bụi", "robot lau nhà"],
    "hut bui": ["robot hút bụi", "máy hút bụi"],
    "gio inox": ["giỏ inox", "giá inox để đồ rửa bát"],
}
SUBTYPES = [
    "nồi chiên", "nồi cơm", "nồi áp suất", "bộ nồi", "chảo", "ấm siêu tốc", "ấm đun",
    "máy ép", "máy xay", "bộ dao", "mài dao", "dao", "thớt", "giá bát", "giá dao thớt",
    "giá gia vị", "giá xoong nồi", "kệ bát", "kệ gia vị", "tay nâng", "ray trượt",
    "viên rửa", "muối rửa bát", "muối rửa chén", "nước làm bóng", "nước trợ xả",
    "tẩy cặn", "chất tẩy rửa", "lưới chống côn trùng", "lưới carekit",
]
BROAD_CATEGORIES = {"gia dung", "phu kien", "dao", "chat tay rua", "luoi"}


def model_key(value):
    return normalize_text(value).replace(" ", "")


def model_aliases(product):
    sku = product["sku"]
    base = re.sub(r"[\s._-]*mẫu(?:\s.*)?$", "", sku, flags=re.I).strip()
    values = {sku, base}
    # Keep inventory variants separate, but also recognize their shared model
    # when customers omit internal prefixes such as KCC, TL or TIẾN.
    words = normalize_text(base).split()
    while words and words[0] in {"kcc", "tl", "tien", "km"}:
        words.pop(0)
    if words:
        values.add(" ".join(words))
    values.update(re.findall(r"\b[A-Za-z0-9]+(?:[./_-][A-Za-z0-9]+)*\b", product["name"]))
    aliases = set()
    for value in values:
        key = model_key(value)
        if (len(key) >= 4 and re.search(r"[a-z]", key) and re.search(r"\d", key)
                and not re.fullmatch(r"\d+(?:kg|lit|l|w|kw|cm|mm|btu|v|inch|k|hz|tr)", key)):
            aliases.add(key)
    return aliases


class ProductCatalog:
    def __init__(self, document):
        if document.get("schema_version") != 1 or not isinstance(document.get("products"), list):
            raise ValueError("Danh mục sản phẩm không đúng định dạng.")
        self.document = document
        self.products = document["products"]
        self.source = document.get("source", {})
        self._names = [normalize_text(product["name"]) for product in self.products]
        self._name_index = defaultdict(set)
        self._models = defaultdict(set)
        self._categories = defaultdict(set)
        self._brands = defaultdict(set)
        self._alias_labels = {}
        self._brand_labels = {}
        counts = Counter(word for name in self._names for word in set(name.split()))
        self._sale_ids = set()
        for index, product in enumerate(self.products):
            category = normalize_text(product["category"])
            if category == "dich vu":
                continue
            self._sale_ids.add(index)
            words = self._names[index].split()
            if words:
                self._name_index[min(words, key=lambda word: counts[word])].add(index)
            for alias in model_aliases(product):
                self._models[alias].add(index)
            aliases = CATEGORY_ALIASES.get(category, [product["category"]])
            if category in BROAD_CATEGORIES:
                aliases = aliases + [alias for alias in SUBTYPES if contains_phrase(product["name"], alias)]
            for alias in aliases:
                if normalize_text(alias):
                    self._categories[normalize_text(alias)].add(index)
                    self._alias_labels.setdefault(normalize_text(alias), alias)
            brand = product.get("brand", "")
            if normalize_text(brand) not in {"", "khac"}:
                self._brands[normalize_text(brand)].add(index)
                self._brands[normalize_text(brand.replace("'", ""))].add(index)
                self._brand_labels[normalize_text(brand)] = brand
                self._brand_labels[normalize_text(brand.replace("'", ""))] = brand

    @property
    def categories(self):
        return sorted({product["category"] for product in self.products})

    def _phrase_ids(self, text, index):
        hits = [(alias, ids) for alias, ids in index.items() if f" {alias} " in f" {text} "
                and not re.search(r"\b(?:khong (?:mua|lay|chon|dung|can)|khong phai|ngoai tru) " + re.escape(alias) + r"\b", text)]
        # Prefer 'máy rửa bát' to a shorter overlapping alias, keeping distinct products.
        hits = [(alias, ids) for alias, ids in hits if not any(alias != other and f" {alias} " in f" {other} " for other, _ in hits)]
        return hits, set().union(*(ids for _, ids in hits)) if hits else set()

    def match(self, message):
        normalized = normalize_text(message)
        words = normalized.split()
        category_hits, category_ids = self._phrase_ids(normalized, self._categories)
        brand_hits, brand_ids = self._phrase_ids(normalized, self._brands)
        name_candidates = set().union(*(self._name_index.get(word, set()) for word in words)) if words else set()
        names = [index for index in name_candidates if f" {self._names[index]} " in f" {normalized} "]
        found_models = set()
        for start in range(len(words)):
            if re.search(r"(?:khong (?:mua|lay|chon|dung|can)|khong phai|ngoai tru) $", " ".join(words[:start]) + " "):
                continue
            for length in range(1, min(8, len(words) - start) + 1):
                key = "".join(words[start:start + length])
                if key in self._models:
                    found_models.add(key)
        # A full code wins over its shorter component aliases from the same model.
        found_models = {key for key in found_models if not any(key != other and key in other for other in found_models)}
        reason, review = "", False
        if names:
            longest = max(len(self._names[index]) for index in names)
            ids = {index for index in names if len(self._names[index]) == longest}
            kind = "name"
        elif found_models:
            ids = set().union(*(self._models[key] for key in found_models))
            kind = "model"
        else:
            ids = category_ids & brand_ids if category_ids and brand_ids else category_ids or brand_ids
            kind = "category" if category_ids else "brand"
            codes = re.findall(r"\b[A-Za-z][A-Za-z0-9._/-]*\d[A-Za-z0-9._/-]*\b", str(message))
            unknown = [code for code in codes if len(model_key(code)) >= 5
                       and not re.fullmatch(r"\d+(?:kg|lit|l|w|kw|cm|mm|btu|v|inch|k|hz|tr)", model_key(code))]
            if unknown and (category_ids or brand_ids):
                kind, review = "unknown_model", True
                reason = "Mã/model hỏi chưa khớp danh mục; cần kiểm tra thủ công."
                ids = set()
                label = ", ".join(unknown)
            elif not ids:
                return None
        ids &= self._sale_ids
        ordered = [self.products[index] for index in sorted(ids)]
        if kind in {"model", "name"}:
            if (brand_ids and not ids & brand_ids) or (category_ids and not ids & category_ids):
                review = True
                reason = "Mã khớp nhưng thương hiệu/nhóm hàng trong câu hỏi khác danh mục."
            if len(ordered) > 1:
                review = True
                reason = "Khớp nhiều mã hoặc biến thể; cần xác nhận đúng mẫu."
            label = ordered[0]["name"] if ordered else "sản phẩm đang hỏi"
            if ordered and all((item.get("stock_snapshot") or 0) <= 0 for item in ordered):
                review = True
                reason = "Tồn kho trong tệp không dương; cần kiểm tra lại trước khi tư vấn."
            if any(contains_phrase(item["sku"], "mẫu") for item in ordered):
                review = True
                reason = "Có mã hàng mẫu/trưng bày; cần xác nhận đúng hàng bán."
        elif kind != "unknown_model":
            label = ", ".join(self._alias_labels[alias] for alias, _ in category_hits) or "sản phẩm " + ", ".join(self._brand_labels[alias] for alias, _ in brand_hits)
            if kind == "brand":
                review = True
                reason = "Chỉ có thương hiệu; cần hỏi rõ sản phẩm hoặc model."
        return dict(label=label, kind=kind, requires_review=review, reason=reason,
                    candidate_count=len(ordered), candidates=[{
                        key: item.get(key) for key in ("sku", "name", "category", "brand", "stock_snapshot")
                    } for item in ordered[:10]])


@lru_cache(maxsize=4)
def _load_cached(path, modified, size):
    return ProductCatalog(json.loads(Path(path).read_text(encoding="utf-8")))


def load_company_catalog(path=DEFAULT_CATALOG_PATH):
    path = Path(path)
    if not path.exists():
        return None
    stat = path.stat()
    return _load_cached(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def catalog_sample_posts(catalog, per_category=2):
    """A manageable offline sample; the review generator tests every product."""
    counts, posts = Counter(), []
    for product in catalog.products:
        if normalize_text(product["category"]) == "dich vu" or counts[product["category"]] >= per_category:
            continue
        counts[product["category"]] += 1
        for question in (f"Có bác nào có {product['name']} không?", f"Cho mình xin giá {product['sku']}"):
            posts.append(dict(id=f"catalog-{len(posts)+1}", url=f"sample://company/{len(posts)+1}",
                              author="Mẫu công ty · " + product["category"], message=question))
    return posts
