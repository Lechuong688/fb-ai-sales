"""Create offline review cases for every sale item in the imported catalog."""

from collections import Counter
import csv
import json
from pathlib import Path

from backend.services.comment_rules import suggest_comment
from backend.services.product_catalog import load_company_catalog, model_aliases, model_key
from backend.utils.text_matching import normalize_text


def review_cases(catalog):
    for product in catalog.products:
        if normalize_text(product["category"]) == "dich vu":
            continue
        questions = [
            f"Có bác nào có {product['name']} không?",
            f"Cho em xin giá {product['name']}.",
            f"Cần mua {product['name']}, bác nào bán ib giúp em.",
        ]
        if model_key(product["sku"]) in model_aliases(product):
            questions.append(f"Ai có {product['sku']} không?")
        for question in questions:
            yield product, question


def build_review(output_dir=Path("reports")):
    catalog = load_company_catalog()
    if catalog is None:
        raise ValueError("Chưa có danh mục công ty.")
    output_dir.mkdir(parents=True, exist_ok=True)
    counts, groups, failures = Counter(), {}, []
    rows = []
    for product, question in review_cases(catalog):
        result = suggest_comment(question, catalog=catalog)
        matched = [item["sku"] for item in result.get("catalog_match", {}).get("candidates", [])]
        passed = result["status"] in {"draft", "manual_review"} and product["sku"] in matched
        passed = passed and "ib" in normalize_text(result["comment"]).split()
        passed = passed and "ben em co" not in normalize_text(result["comment"])
        if not passed:
            failures.append(dict(sku=product["sku"], question=question, result=result))
        counts[result["status"]] += 1
        row = [product["sku"], product["name"], product["category"], question, result["status"],
               result["rule_name"], ", ".join(matched), result["comment"], result["reason"], "Đạt" if passed else "Cần kiểm tra"]
        rows.append(row)
        groups.setdefault(product["category"], []).append(row)
    with (output_dir / "company-product-scenarios.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Mã gốc", "Tên hàng", "Nhóm", "Câu hỏi thử", "Trạng thái", "Quy tắc", "Mã khớp", "Bình luận dự kiến", "Lý do duyệt", "Kiểm thử"])
        for row in rows:
            writer.writerow(["'" + str(value) if str(value).lstrip().startswith(("=", "+", "-", "@")) else value for value in row])
    document = catalog.document
    lines = ["# Danh mục công ty và các câu bình luận chờ duyệt", "",
             f"Nguồn: {catalog.source['filename']}", "",
             f"Đã lưu {len(catalog.products):,} mặt hàng, {len(catalog.categories)} nhóm. "
             "Hai dòng thuộc nhóm Dịch vụ được giữ trong dữ liệu nhưng không dùng để nhận diện hàng bán.", "",
             f"Đã thử {len(rows):,} câu hỏi từ toàn bộ hàng bán: {counts['draft']:,} bản nháp, "
             f"{counts['manual_review']:,} cần duyệt thủ công, {len(failures)} trường hợp chưa đạt.", "",
             "Chỉ chạy offline. Không truy cập Facebook, không gọi AI và không gửi bình luận.", "",
             "## Dữ liệu đã lưu", "",
             "Danh mục giữ mã, tên, nhóm, thương hiệu, tồn theo tệp, các trường gốc và vị trí dòng/worksheet. "
             "Có bản sao Excel nguồn và SHA-256 để đối chiếu. Nội dung mô tả và ghi chú chỉ được lưu như dữ liệu, không dùng làm chỉ dẫn cho ứng dụng.", "",
             f"Tồn theo tệp: {document['summary']['positive_stock']} mã dương, {document['summary']['zero_stock']} mã bằng 0, "
             f"{document['summary']['negative_stock']} mã âm. Ngày trong tên tệp: {catalog.source.get('snapshot_date_from_filename')}.", "",
             "Tệp không có cột giá bán. Các bản nháp mời inbox để kiểm tra hàng và báo giá, không tự nêu giá hoặc cam kết hàng sẵn. "
             "Mã mẫu/trưng bày, tồn không dương, nhiều biến thể hoặc mã chưa biết được đánh dấu cần duyệt.", "",
             "## Cách dùng", "",
             "1. Khởi động lại ứng dụng, vào Comment. Ô Dùng danh mục công ty được bật sẵn.",
             "2. Mở Danh mục công ty để xem, tìm kiếm hoặc Nạp Excel cho lần cập nhật sau.",
             "3. Bấm Thử sản phẩm công ty để xem câu hỏi và bình luận mẫu, không cần đăng nhập Facebook.",
             "4. Quét bài từ nguồn đã chọn sẽ dùng danh mục này để nhận diện tên hàng, mã/model và thương hiệu.",
             "5. Sửa bản nháp hoặc xuất CSV để duyệt. Gửi bình luận thật vẫn khóa.", "",
             "## Nhóm hàng trong nguồn", "", "| Nhóm | Số mặt hàng |", "|---|---:|"]
    for category, count in document["summary"]["categories"].items():
        lines.append(f"| {category} | {count} |")
    lines += ["", "## Ví dụ theo từng nhóm hàng", "", "Bảng CSV đi kèm chứa toàn bộ câu hỏi thử và kết quả đối chiếu mã.", "",
              "| Nhóm | Câu hỏi | Bình luận dự kiến | Trạng thái |", "|---|---|---|---|"]
    for category, cases in groups.items():
        for row in cases[:2]:
            values = [category, row[3], row[7], row[4]]
            lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in values) + " |")
    (output_dir / "company-catalog-review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "company-catalog-checks.json").write_text(json.dumps(
        dict(case_count=len(rows), products=len(catalog.products), statuses=dict(counts), failures=failures),
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(cases=len(rows), statuses=dict(counts), failures=len(failures)), ensure_ascii=True))
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if build_review() else 0)
