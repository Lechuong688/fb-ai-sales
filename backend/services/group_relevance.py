"""Filter saved group names before opening their Facebook feeds."""
from backend.services.comment_rules import DEFAULT_PRODUCTS
from backend.services.product_catalog import CATEGORY_ALIASES, BROAD_CATEGORIES, SUBTYPES
from backend.utils.text_matching import normalize_product_text, normalize_text, contains_phrase


KITCHEN_CATEGORIES = {'bep tu', 'bep gas', 'gas', 'hut mui', 'may rua bat', 'chau rua', 'voi rua', 'lo nuong', 'lo vi song'}
KITCHEN_TOPICS = ['thiết bị bếp', 'nhà bếp', 'tủ bếp', 'yêu bếp', 'nghiện bếp', 'đồ dùng bếp', 'phụ kiện bếp']
KITCHEN_SMALL_PRODUCTS = ['nồi cơm', 'nồi chiên', 'nồi áp suất', 'bộ nồi', 'chảo', 'ấm siêu tốc', 'máy ép', 'máy xay']


def group_search_terms(products=None, catalog=None):
    terms, categories, names = set(), set(), []
    if catalog is not None:
        for product in catalog.products:
            category = normalize_text(product.get('category'))
            if category == 'dich vu':
                continue
            categories.add(category)
            names.append(product.get('name', ''))
            if category in BROAD_CATEGORIES:
                if category == 'gia dung':
                    terms.add('gia dụng')
                terms.update(alias for alias in SUBTYPES if contains_phrase(product.get('name'), alias))
            else:
                terms.update(CATEGORY_ALIASES.get(category, [product.get('category', '')]))
            brand = product.get('brand', '')
            if normalize_text(brand) not in {'', 'khac', 'unknown', 'no brand'}:
                terms.add(brand)
    else:
        selected = DEFAULT_PRODUCTS if products is None else products
        names = selected
        terms.update(selected)
        for category, aliases in CATEGORY_ALIASES.items():
            if any(contains_phrase(normalize_product_text(product), alias) for product in selected for alias in aliases):
                categories.add(category)
                terms.update(aliases)
    if categories & KITCHEN_CATEGORIES or any(contains_phrase(name, alias) for name in names for alias in KITCHEN_SMALL_PRODUCTS):
        terms.update(KITCHEN_TOPICS)
        terms.add('gia dụng')
    if 'loc nuoc' in categories:
        terms.update(['nước ion kiềm', 'ion kiềm'])
    return {normalize_product_text(term) for term in terms if normalize_product_text(term)}


def group_name_matches(name, terms):
    text = ' ' + normalize_product_text(name) + ' '
    return any(' ' + term + ' ' in text for term in terms)
