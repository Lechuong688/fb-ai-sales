# Facebook AI Sales

Ứng dụng desktop PySide6 hỗ trợ quản lý profile Facebook, nhóm, bài đăng và tìm bài có nhu cầu mua hàng theo danh mục công ty.

## Khởi động

Từ thư mục dự án, trong môi trường đã cài các dependency:

```powershell
uv run python -m frontend.main
```

## Luồng sử dụng

1. **Accounts**: mở profile và đăng nhập. Mở profile không tự quét nhóm hoặc đăng bài.
2. **Groups**: bấm **Quét nhóm nick đang mở** để đồng bộ nhóm theo từng nick.
3. **Comment**: chọn nick, một nhóm hoặc tất cả nhóm, rồi tìm bài. Chỉ nhận bài xác định nằm trong 15 ngày gần nhất. Có tiến độ, số bài tối đa và nút dừng riêng.
4. Kết quả thật phù hợp được tự lưu vào **Customers** sau từng nhóm. Quét lại cùng bài sẽ cập nhật hồ sơ cũ, không tạo bản trùng theo nick.
5. Sửa bình luận dự kiến trong Comment rồi bấm **Lưu bản nháp đã chọn** để giữ nội dung sang Customers. Tình huống mẫu offline không tạo khách hàng.
6. **Customers**: tìm kiếm có/không dấu, lọc trạng thái, ghi chú, sửa bản nháp, duyệt hoặc không dùng bản nháp. Có phân trang và xuất CSV theo bộ lọc.
7. **Posts**: soạn bài, chọn đích, lưu bản nháp hoặc đăng bài sau bước xác nhận riêng.

### Theo dõi khách hàng

Mỗi hồ sơ tương ứng với một bài có nhu cầu, không phải danh tính khách hàng đã xác minh. Hồ sơ giữ bài gốc, nhóm, ngày đăng, sản phẩm/mã hàng khớp và các nick phát hiện. Trạng thái theo dõi gồm Mới, Đang tư vấn, Cần theo dõi, Đã chốt và Bỏ qua.

Quét lại không ghi đè nội dung sửa tay, ghi chú hoặc trạng thái theo dõi. Khi bài hoặc gợi ý thay đổi, phê duyệt cũ được đưa về chờ duyệt. Thay đổi chưa lưu được giữ trên màn hình khi có kết quả mới; ứng dụng kiểm tra phiên bản trước khi ghi để tránh ghi đè thay đổi mới hơn.

Giới hạn 15 ngày áp dụng cho việc thu thập bài mới. Customers giữ hồ sơ đã lưu để tiếp tục chăm sóc, kể cả khi bài đã cũ.

**Duyệt bản nháp chỉ lưu trạng thái trên máy. Chức năng gửi bình luận thật vẫn khóa ở worker.** Messenger và một số mục hệ thống vẫn đang phát triển.

## Danh mục hàng hóa

Vào Comment → **Danh mục công ty** để xem hoặc nạp Excel cập nhật. **Thử sản phẩm công ty** chạy ví dụ offline. Tồn kho là số từ tệp nhập; bình luận mời inbox để kiểm tra hàng và báo giá, không tự cam kết hàng sẵn.

## Bộ sưu tập nhóm, kho nội dung và gợi ý AI theo từng bài

- **Posts → Chọn nhóm Facebook**: chọn nhóm, đặt tên và lưu bộ sưu tập. Có thể áp dụng, cập nhật hoặc xóa bộ sưu tập; mỗi bộ thuộc riêng một nick. Nhóm không còn trong danh sách đã đồng bộ sẽ không được tự chọn.
- **Comment → Nhóm Facebook cần tìm**: chọn tất cả nhóm, một nhóm hoặc bộ sưu tập của nick. Bấm **Làm mới nguồn** sau khi tạo bộ sưu tập trong Posts.
- **Comment → AI cho các bài đã chọn**: chọn từ 1 đến 10 bài để tạo gợi ý riêng qua OpenAI. Cần cấu hình `OPENAI_API_KEY` và `OPENAI_MODEL` trong `.env`. Nội dung bài đã chọn và thông tin cửa hàng được gửi tới OpenAI. Có bảng duyệt và sửa từng bình luận trước khi áp dụng. Lỗi một bài không làm mất gợi ý các bài khác. **Dừng gợi ý AI** dừng các bài tiếp theo sau khi yêu cầu hiện tại kết thúc.
- Sau khi áp dụng gợi ý, bấm **Lưu bản nháp đã chọn** để lưu vào Customers. Bài đã sửa trong lúc AI chạy không bị ghi đè. Gửi bình luận thật vẫn đang khóa.
- **Posts → Lưu thành mẫu / Mở kho nội dung**: lưu nội dung và đường dẫn ảnh/video để dùng lại, tìm mẫu theo tên hoặc nội dung, xóa mẫu không dùng. Cần giữ các tệp media tại đường dẫn đã lưu.
- **Posts** hỗ trợ lần lượt từng nick hoặc song song giữa các nick; trong mỗi nick, các đích luôn chạy lần lượt. Có khoảng nghỉ 0–3600 giây, nút dừng và tự bỏ qua các đích còn lại của nick khi gặp lỗi. Giữ giới hạn 5 nhóm và 5 nick mỗi lượt, xác nhận trước khi đăng. Nội dung đã duyệt được tự lưu thành bản nháp trước khi chạy.
- **Reports**: lịch sử từng đích với trạng thái Đã gửi, Lỗi hoặc Bỏ qua/đã dừng; lọc ngày, trạng thái, tìm kiếm không dấu và xuất CSV theo bộ lọc. Đã gửi không đồng nghĩa bài trong nhóm đã được quản trị viên phê duyệt.

Các bảng `publishing_collections`, `publishing_templates` và `publishing_receipts` được tạo bổ sung trong `data/app.db` khi mở chức năng. Đây là các chức năng tích hợp theo luồng sử dụng tham khảo FBtool; chưa bao gồm toàn bộ tính năng FBtool như tương tác bạn bè, tìm từ quảng cáo, quản trị nhóm và nhắn tin tự động.

## Hộp chào mừng của nhóm

Khi vào nhóm để tìm khách hoặc đăng bài, ứng dụng tự đóng hộp **chào mừng thành viên** bằng nút Đóng/Close của chính hộp đó. Có kiểm tra lại trong quá trình quét để xử lý hộp xuất hiện muộn. Ứng dụng không tự bấm Tiếp tục, không đóng hộp soạn bài, hộp có trường nhập liệu hoặc hộp xác minh tài khoản.

## Tạm dừng và tiếp tục tác vụ

- Khi **tìm khách**, **quét nhóm** hoặc **gợi ý AI** đang chạy, các nút **Tạm dừng** và **Dừng** xuất hiện ngay trên trang. Trong **Posts**, các nút điều khiển đăng bài nằm cạnh nút Đăng ngay; quét lại nhóm có nút riêng trên thanh công cụ và trong hộp chọn nhóm.
- **Tạm dừng** đổi thành **Tiếp tục**: giữ vị trí, hàng đợi và kết quả hiện tại. Thời gian tạm dừng không tính vào giới hạn thời gian quét và khoảng nghỉ đăng bài.
- **Dừng** hoạt động cả khi đang tạm dừng, kết thúc phần việc còn lại và giữ profile mở. Kết quả đã lưu và bài đã gửi vẫn được giữ nguyên. Để chạy một lượt mới, bấm nút bắt đầu tác vụ tương ứng.
- Các tác vụ dừng tại điểm kiểm tra kế tiếp. Thao tác Facebook hoặc yêu cầu AI đã gửi đang xử lý cần hoàn tất hoặc hết thời gian chờ trước khi tác vụ có thể nghỉ; ứng dụng không gửi tiếp bài hoặc yêu cầu mới khi đang tạm dừng.

## Dữ liệu cục bộ

- `data/app.db`: tài khoản, nhóm, bản nháp và bảng `leads` lưu khách hàng tiềm năng.
- `data/company_catalog.json`: danh mục công ty và dữ liệu nguồn.
- `data/catalog_sources/`: bản sao Excel đã nhập.
- `data/comment_rules.json`: quy tắc trả lời tùy chỉnh, được tạo khi lưu quy tắc.
- `data/profiles/`: phiên trình duyệt theo profile.
- `logs/app.log` và `logs/faults.log`: log ứng dụng và chẩn đoán crash.

## Kiểm thử

```powershell
uv run python -m unittest discover -s tests -v
```

Các kiểm thử nghiệp vụ và giao diện dùng database tạm và dữ liệu mẫu. Kiểm thử Playwright dùng trang fixture được chặn bằng route cục bộ, không đăng nhập tài khoản hoặc gửi bình luận Facebook. Một số kiểm thử trình duyệt được bỏ qua nếu Chromium chưa được cài.
