"""Read KiotViet XLSX exports without Excel, macros, or external data access."""

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
DEFAULT_CATALOG_PATH = Path("data/company_catalog.json")


def read_xlsx_sheets(path):
    """Yield sheet names and sparse rows. Formulas use existing cached values only."""
    with ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist()) > 100_000_000:
            raise ValueError("Tệp Excel quá lớn để nhập danh mục.")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(node.text or "" for node in item.findall(".//m:t", NS))
                       for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", NS)]
        relations = {
            item.get("Id"): item.get("Target")
            for item in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            if item.tag == f"{{{REL_NS}}}Relationship" and item.get("TargetMode") != "External"
        }
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            target = relations.get(sheet.get(f"{{{DOC_REL_NS}}}id"))
            if not target:
                continue
            member = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "xl/" + target)
            if not member.startswith("xl/") or ".." in PurePosixPath(member).parts:
                raise ValueError("Đường dẫn worksheet không hợp lệ.")
            rows = []
            for row in ET.fromstring(archive.read(member)).findall("m:sheetData/m:row", NS):
                values = {}
                for cell in row.findall("m:c", NS):
                    reference = cell.get("r", "")
                    column = re.sub(r"\d", "", reference)
                    value = cell.find("m:v", NS)
                    text = value.text if value is not None else None
                    if cell.find("m:f", NS) is not None and text is None:
                        raise ValueError(f"Ô công thức {sheet.get('name')}!{reference} chưa có giá trị lưu sẵn.")
                    if cell.get("t") == "s" and text is not None:
                        text = strings[int(text)]
                    elif cell.get("t") == "inlineStr":
                        text = "".join(node.text or "" for node in cell.findall("m:is//m:t", NS))
                    if text is not None:
                        values[column] = text
                if values:
                    rows.append((int(row.get("r", len(rows) + 1)), values))
            yield sheet.get("name", ""), rows


def _quantity(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation()
        return int(number) if number == number.to_integral_value() else float(number)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Tồn kho không phải số hợp lệ: {value!r}") from None


def import_catalog(source, output=DEFAULT_CATALOG_PATH, archive_source=True):
    source, output = Path(source), Path(output)
    payload = source.read_bytes()
    products, sheets, seen_skus = [], [], set()
    try:
        source_sheets = list(read_xlsx_sheets(source))
    except (BadZipFile, ET.ParseError, KeyError, IndexError) as exc:
        raise ValueError("Tệp không phải workbook XLSX hợp lệ hoặc bị thiếu dữ liệu.") from exc
    for sheet_name, rows in source_sheets:
        header_index = next((index for index, (_, cells) in enumerate(rows[:20])
                             if {"Mã hàng", "Tên hàng"}.issubset({str(value).strip() for value in cells.values()})), None)
        if header_index is None:
            continue
        headers = {column: str(value).strip() for column, value in rows[header_index][1].items()}
        sheet_count = 0
        for row_number, cells in rows[header_index + 1:]:
            raw = {headers[column]: value for column, value in cells.items() if column in headers}
            sku, name = str(raw.get("Mã hàng", "")).strip(), str(raw.get("Tên hàng", "")).strip()
            if not sku and not name:
                continue
            if not sku or not name:
                raise ValueError(f"Thiếu mã hoặc tên hàng tại {sheet_name}, dòng {row_number}.")
            if sku.casefold() in seen_skus:
                raise ValueError(f"Trùng mã hàng {sku}; chưa ghi đè danh mục.")
            seen_skus.add(sku.casefold())
            products.append(dict(
                sku=sku, name=name, category=str(raw.get("Nhóm hàng(3 Cấp)", "")).strip(),
                brand=str(raw.get("Thương hiệu", "")).strip(),
                stock_snapshot=_quantity(raw.get("Tồn kho")),
                item_type=str(raw.get("Loại hàng", "")).strip(),
                source_sheet=sheet_name, source_row=row_number, source_fields=raw,
            ))
            sheet_count += 1
        sheets.append(dict(name=sheet_name, header_row=rows[header_index][0], records=sheet_count))
    if not products:
        raise ValueError("Không tìm thấy bảng có cột Mã hàng và Tên hàng.")
    date_match = re.search(r"KV(\d{2})(\d{2})(\d{4})", source.name)
    snapshot_date = None
    if date_match:
        day, month, year = date_match.groups()
        snapshot_date = datetime(int(year), int(month), int(day)).date().isoformat()
    document = dict(
        schema_version=1,
        source=dict(filename=source.name, sha256=hashlib.sha256(payload).hexdigest(),
                    snapshot_date_from_filename=snapshot_date, sheets=sheets),
        imported_at=datetime.now(timezone.utc).isoformat(),
        summary=dict(product_count=len(products), categories=dict(Counter(product["category"] for product in products)),
                     positive_stock=sum((product["stock_snapshot"] or 0) > 0 for product in products),
                     zero_stock=sum(product["stock_snapshot"] == 0 for product in products),
                     negative_stock=sum((product["stock_snapshot"] or 0) < 0 for product in products),
                     missing_stock=sum(product["stock_snapshot"] is None for product in products)),
        products=products,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if archive_source:
        archive_dir = output.parent / "catalog_sources"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived = archive_dir / source.name
        if archived.resolve() != source.resolve():
            shutil.copy2(source, archived)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    return document


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Nhập danh mục sản phẩm từ Excel KiotViet.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_CATALOG_PATH)
    args = parser.parse_args()
    result = import_catalog(args.source, args.output)
    print(json.dumps(result["summary"], ensure_ascii=True))
