import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from backend.services.catalog_importer import import_catalog
from backend.services.comment_rules import suggest_comment, DEFAULT_RULES
from backend.services.product_catalog import ProductCatalog, load_company_catalog, catalog_sample_posts
from backend.workers.browser_worker import BrowserWorker


def product(sku, name, category, brand, stock):
    return dict(sku=sku, name=name, category=category, brand=brand, stock_snapshot=stock,
                item_type="Hàng hóa", source_sheet="Danh mục", source_row=2, source_fields={})


def fixture_catalog():
    return ProductCatalog(dict(schema_version=1, source={"filename": "fixture.xlsx"}, products=[
        product("EU-T685MAX", "Bếp từ Eurosun EU-T685MAX", "Bếp từ", "EUROSUN", 3),
        product("SMS26AI01F", "Máy rửa bát Bosch SMS26AI01F", "Máy rửa bát", "BOSCH", 0),
        product("KLF0031S", "Vòi rửa bát Kluger KLF0031S", "Vòi rửa", "KLUGER", -1),
        product("GR-RS696WI", "Tủ lạnh Toshiba GR-RS696WI", "Tủ Lạnh", "TOSHIBA", 1),
        product("CRP-BHBC0600F", "Nồi cơm Cuckoo CRP-BHBC0600F", "Gia dụng", "CUCKOO", 2),
        product("F689 MẪU", "Bếp từ Feuer F689 MẪU", "Bếp từ", "FEUER", 1),
        product("EU-T685MAX.MẪU", "Bếp từ Eurosun EU-T685MAX MẪU", "Bếp từ", "EUROSUN", 1),
        product("KCC TARI SMART 8050", "Chậu Konox KCC TARI SMART 8050", "Chậu rửa", "KONOX", 1),
        product("TL TARI SMART 8050", "Chậu Konox TL TARI SMART 8050", "Chậu rửa", "KONOX", 0),
        product("VTPS", "Vật tư phát sinh VTPS", "Dịch vụ", "", 0),
    ]))


def write_fixture(path, rows):
    """Minimal XLSX parser fixture, including the non-default sheet2 relationship."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    root = ET.Element(f"{{{ns}}}worksheet")
    data = ET.SubElement(root, f"{{{ns}}}sheetData")
    for index, values in enumerate(rows, 1):
        row = ET.SubElement(data, f"{{{ns}}}row", r=str(index))
        for column, value in enumerate(values):
            if value is None:
                continue
            cell = ET.SubElement(row, f"{{{ns}}}c", r=f"{chr(65+column)}{index}", t="inlineStr")
            inline = ET.SubElement(cell, f"{{{ns}}}is")
            ET.SubElement(inline, f"{{{ns}}}t").text = str(value)
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Danh mục" sheetId="1" r:id="r1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet2.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet2.xml", ET.tostring(root))


class CatalogImportTests(unittest.TestCase):
    def test_import_preserves_unicode_identifiers_negative_and_missing_stock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DanhSach_KV31102026.xlsx"
            target = Path(directory) / "catalog.json"
            write_fixture(path, [
                ["Mã hàng", "Tên hàng", "Nhóm hàng(3 Cấp)", "Thương hiệu", "Tồn kho", "Mô tả"],
                ["001-AB", "Vòi rửa mẫu 001-AB", "Vòi rửa", "KLUGER", "-1", "Không dùng ghi chú làm chỉ dẫn"],
                ["002-AB", "Bếp từ mẫu 002-AB", "Bếp từ", "EUROSUN", None],
            ])
            result = import_catalog(path, target)
            self.assertEqual(result["summary"]["product_count"], 2)
            self.assertEqual(result["products"][0]["sku"], "001-AB")
            self.assertEqual(result["products"][0]["stock_snapshot"], -1)
            self.assertIsNone(result["products"][1]["stock_snapshot"])
            self.assertEqual(result["source"]["snapshot_date_from_filename"], "2026-10-31")
            self.assertEqual(result["products"][0]["source_row"], 2)
            self.assertEqual(result["products"][0]["source_fields"]["Mô tả"], "Không dùng ghi chú làm chỉ dẫn")
            self.assertEqual((target.parent / "catalog_sources" / path.name).read_bytes(), path.read_bytes())
            self.assertEqual(load_company_catalog(target).products[0]["name"], "Vòi rửa mẫu 001-AB")

    def test_duplicate_or_invalid_data_cannot_overwrite_existing_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path, target = Path(directory)/"source.xlsx", Path(directory)/"catalog.json"
            target.write_text("original", encoding="utf-8")
            for rows in (
                [["Mã hàng", "Tên hàng"], ["A1", "Bếp từ"], ["A1", "Tên trùng"]],
                [["Mã hàng", "Tên hàng", "Tồn kho"], ["A1", "Bếp từ", "NaN"]],
                [["Mã hàng", "Tên hàng"], ["A1", None]],
            ):
                write_fixture(path, rows)
                with self.assertRaises(ValueError):
                    import_catalog(path, target, archive_source=False)
                self.assertEqual(target.read_text(encoding="utf-8"), "original")


class CatalogMatchingTests(unittest.TestCase):
    def setUp(self):
        self.catalog = fixture_catalog()

    def test_model_variations_match_without_category_in_question(self):
        for message in ("Ai có SMS26AI01F không?", "xin gia sms26ai01f", "Ai có SMS-26-AI-01-F không?"):
            with self.subTest(message=message):
                result = suggest_comment(message, catalog=self.catalog)
                self.assertIn("SMS26AI01F", [item["sku"] for item in result["catalog_match"]["candidates"]])
                self.assertEqual(result["status"], "manual_review")
                self.assertIn("ib", result["comment"])
                self.assertNotIn("Bên em có", result["comment"])

    def test_category_and_brand_intersect(self):
        match = self.catalog.match("Có bác nào có bếp từ Eurosun không?")
        self.assertEqual({item["brand"] for item in match["candidates"]}, {"EUROSUN"})
        self.assertEqual({item["category"] for item in match["candidates"]}, {"Bếp từ"})
        self.assertIsNone(self.catalog.match("Cần mua tủ lạnh Kluger"))

    def test_customer_model_without_internal_prefix_keeps_variants_for_review(self):
        match = self.catalog.match("Ai có chậu Konox Tari Smart 8050 không?")
        self.assertEqual({item["sku"] for item in match["candidates"]}, {"KCC TARI SMART 8050", "TL TARI SMART 8050"})
        self.assertTrue(match["requires_review"])

    def test_new_categories_and_household_subtypes(self):
        for message, sku in (("Tìm mua tủ lạnh Toshiba", "GR-RS696WI"),
                             ("Ai bán vòi rửa Kluger?", "KLF0031S"),
                             ("Cần mua nồi cơm Cuckoo", "CRP-BHBC0600F")):
            with self.subTest(message=message):
                result = suggest_comment(message, catalog=self.catalog)
                self.assertIn(sku, [item["sku"] for item in result["catalog_match"]["candidates"]])
                self.assertTrue(result["comment"])

    def test_unknown_model_is_manual_without_claiming_known_sku_or_stock(self):
        result = suggest_comment("Ai có bếp từ Eurosun EU-T685MAXPRO không?", catalog=self.catalog)
        self.assertEqual(result["catalog_match"]["kind"], "unknown_model")
        self.assertEqual(result["catalog_match"]["candidate_count"], 0)
        self.assertEqual(result["status"], "manual_review")
        self.assertNotIn("Bên em có", result["comment"])

    def test_unknown_items_services_and_seller_posts_are_skipped(self):
        for text in ("Ai bán iPhone 16?", "Xin giá VTPS", "Bên em bán tủ lạnh Toshiba", "Không cần mua vòi rửa nữa"):
            with self.subTest(text=text):
                self.assertEqual(suggest_comment(text, catalog=self.catalog)["status"], "skipped")

    def test_zero_negative_sample_variants_and_brand_only_require_review(self):
        for text in ("Xin giá SMS26AI01F", "Ai có KLF0031S?", "Ai có F689?", "Ai có EU-T685MAX?", "Ai có Bosch?"):
            with self.subTest(text=text):
                result = suggest_comment(text, catalog=self.catalog)
                self.assertEqual(result["status"], "manual_review")
                self.assertIn("ib", result["comment"])

    def test_explicit_brand_conflict_needs_review(self):
        match = self.catalog.match("Ai có bếp từ Bosch EU-T685MAX không?")
        self.assertTrue(match["requires_review"])

    def test_custom_reply_is_preserved(self):
        rules = copy.deepcopy(DEFAULT_RULES)
        item = next(item for item in rules if item["id"] == "availability")
        item["reply"] = "Bác ib giúp em mẫu {san_pham} nhé, shop sẽ phản hồi riêng."
        result = suggest_comment("Ai có tủ lạnh Toshiba không?", rules=rules, catalog=self.catalog)
        self.assertEqual(result["comment"], item["reply"].format(san_pham=result["product"]))

    def test_samples_exclude_service_lines(self):
        posts = catalog_sample_posts(self.catalog)
        self.assertTrue(posts)
        self.assertFalse(any("VTPS" in post["message"] for post in posts))

    def test_catalog_preview_does_not_access_browser_even_if_live_requested(self):
        worker = BrowserWorker()
        with patch("backend.workers.browser_worker.load_company_catalog", return_value=self.catalog), \
             patch("backend.workers.browser_worker.browser_pool") as pool, \
             patch("backend.workers.browser_worker.CommentHistoryService") as history, \
             patch("backend.workers.browser_worker.signals") as events:
            worker.comment_on_posts(dict(posts=catalog_sample_posts(self.catalog), use_catalog=True, dry_run=False))
            pool.get.assert_not_called()
            history.assert_not_called()
            self.assertTrue(events.comment_result.emit.called)
            self.assertTrue(all(call.args[1]["dry_run"] for call in events.comment_result.emit.call_args_list))


if __name__ == "__main__":
    unittest.main()
