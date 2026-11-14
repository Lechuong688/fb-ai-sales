import re
import unicodedata


def normalize_text(value):
    value = unicodedata.normalize("NFKD", str(value or "").casefold().replace("đ", "d"))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def contains_phrase(text, phrase):
    text, phrase = normalize_text(text), normalize_text(phrase)
    return bool(phrase) and f" {phrase} " in f" {text} "


def normalize_product_text(value):
    """Recognize common kitchen shorthand without fuzzy matching model codes."""
    text = normalize_text(value)
    for alias, canonical in {
        "mrb": "may rua bat", "mrc": "may rua chen",
        "bosh": "bosch", "boch": "bosch", "eurusun": "eurosun",
    }.items():
        text = re.sub(r"\b" + alias + r"\b", canonical, text)
    return text
