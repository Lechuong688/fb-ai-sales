import unittest

from backend.services.group_relevance import group_search_terms, group_name_matches
from tests.test_product_catalog import fixture_catalog


class GroupRelevanceTests(unittest.TestCase):
    def test_kitchen_groups_match_products_shorthand_and_related_topics(self):
        terms = group_search_terms()
        for name in ('Hội bếp từ Bosch', 'MÁY RỬA CHÉN - REVIEW', 'Hoi MRB',
                     'Máy lọc nước ion Kiềm', 'TỦ BẾP & THIẾT BỊ', 'Yêu Bếp Nghiện Nhà', 'Đồ gia dụng'):
            with self.subTest(name=name):
                self.assertTrue(group_name_matches(name, terms))
        for name in ('RƠI GIẤY TỜ HÀ NỘI', 'Tuyển dụng nhân sự fitness', 'Mua bán căn hộ đường Láng',
                     'Chứng khoán', 'Nội thất ô tô', '', None):
            with self.subTest(name=name):
                self.assertFalse(group_name_matches(name, terms))

    def test_only_selected_products_define_scope(self):
        terms = group_search_terms(['máy lọc nước'])
        self.assertTrue(group_name_matches('Hội lọc nước ion kiềm', terms))
        self.assertFalse(group_name_matches('Hội máy rửa bát', terms))
        self.assertFalse(group_name_matches('Hội bếp từ', terms))
        self.assertFalse(group_name_matches('Hội máy lọc nước', group_search_terms([])))
        self.assertTrue(group_name_matches('Bếp gia đình - Gia dụng', group_search_terms(['nồi cơm'])))

    def test_catalog_supplies_categories_brands_and_aliases(self):
        terms = group_search_terms(products=['giày'], catalog=fixture_catalog())
        for name in ('Hội Bosch Việt Nam', 'Review bosh', 'EURUSUN Việt Nam', 'Máy rửa chén',
                     'Tủ lạnh', 'Gia dụng Cuckoo', 'Chậu rửa bát'):
            with self.subTest(name=name):
                self.assertTrue(group_name_matches(name, terms))
        for name in ('Mua bán giày', 'Rơi giấy tờ', 'Vật tư phát sinh', 'Khác', 'Dịch vụ'):
            self.assertFalse(group_name_matches(name, terms))

    def test_phrase_boundaries_prevent_substring_matches(self):
        terms = group_search_terms(['bếp từ'])
        self.assertFalse(group_name_matches('Hội bếp tương lai', terms))
        self.assertTrue(group_name_matches('BẾP-TỪ - kinh nghiệm', terms))


if __name__ == '__main__':
    unittest.main()
