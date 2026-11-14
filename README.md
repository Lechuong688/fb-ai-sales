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
3. **Comment**: chọn nick, một nhóm hoặc tất cả nhóm, rồi tìm khách. Ứng dụng yêu cầu sắp xếp theo thời gian và chọn **Bài viết mới / New posts** trên menu nhóm khi có menu; không chọn **Hoạt động mới đây**. Cuộn tìm bài người dùng hỏi mua, xin tư vấn, hỏi giá hoặc đánh giá sản phẩm; loại bài chào bán, quảng cáo và mời inbox mua hàng. Chỉ nhận kết quả xác định nằm trong 15 ngày gần nhất. Có tiến độ, số kết quả tối đa và nút dừng riêng.
4. Kết quả thật phù hợp được tự lưu vào **Customers** sau từng nhóm. Quét lại cùng bài sẽ cập nhật hồ sơ cũ, không tạo bản trùng theo nick.
5. Sửa bình luận dự kiến trong Comment rồi bấm **Lưu bản nháp đã chọn** để giữ nội dung sang Customers. Tình huống mẫu offline không tạo khách hàng.
6. **Customers**: tìm kiếm có/không dấu, lọc trạng thái, ghi chú, sửa bản nháp, duyệt hoặc không dùng bản nháp. Có phân trang và xuất CSV theo bộ lọc.
7. **Posts**: soạn bài, chọn đích, lưu bản nháp hoặc đăng bài sau bước xác nhận riêng.

### Theo dõi khách hàng

Mỗi hồ sơ tương ứng với một bài có nhu cầu, không phải danh tính khách hàng đã xác minh. Hồ sơ giữ bài gốc, nhóm, ngày đăng, sản phẩm/mã hàng khớp và các nick phát hiện. Trạng thái theo dõi gồm Mới, Đang tư vấn, Cần theo dõi, Đã chốt và Bỏ qua.

Quét lại không ghi đè nội dung sửa tay, ghi chú hoặc trạng thái theo dõi. Khi bài hoặc gợi ý thay đổi, phê duyệt cũ được đưa về chờ duyệt. Thay đổi chưa lưu được giữ trên màn hình khi có kết quả mới; ứng dụng kiểm tra phiên bản trước khi ghi để tránh ghi đè thay đổi mới hơn.

Giới hạn 15 ngày áp dụng cho việc thu thập bài mới. Customers giữ hồ sơ đã lưu để tiếp tục chăm sóc, kể cả khi bài đã cũ.

**Duyệt hoặc lưu bản nháp trong Customers chỉ lưu trên máy.** Để trả lời khách trong phần bình luận, chọn từ 1 đến 10 kết quả có trạng thái **Trả lời bình luận**, bấm **Trả lời bình luận đã chọn**, xem/sửa từng nội dung rồi bấm **Gửi trả lời**. Để bình luận vào bài hỏi mua, chọn từ 1 đến 10 bài rồi bấm **Bình luận vào bài đã chọn**. Dùng bản nháp theo quy tắc hoặc nhập **Nội dung thay thế** trong phần thông tin cửa hàng; hộp duyệt hiển thị nội dung và link từng bài để sửa trước khi gửi. Các chức năng này gửi thật bằng profile đã quét, ghi lịch sử theo từng link và bỏ qua đích đã gửi. Không tìm thấy đúng ô bình luận thì báo lỗi. Luồng gửi cũ qua `comment_requested` vẫn chỉ xem trước. Nhắn tin theo danh sách đã chọn nằm trong **Kết nối & chăm sóc**; AI Engine và Settings trên sidebar vẫn đang phát triển.

Nhận diện thêm các câu xin review, hỏi loại/hãng nào, chuẩn bị mua thiết bị bếp; hiểu `mrb`/`mrc` là máy rửa bát/chén và các cách viết `bosh`, `boch`, `eurusun` khi khớp danh mục. Không đổi mã hàng hoặc tệp quy tắc đã lưu. Trạng thái quét hiển thị cả số bài không khớp nhu cầu/sản phẩm, chưa đọc được nội dung và lỗi đọc bài để phân biệt nguyên nhân không có kết quả.

Bộ đọc nhóm chờ phần bài viết tải sau `domcontentloaded`, hỗ trợ cả khối bài không có `role="article"`, nội dung `story_message`, nút **Xem thêm** và link `/permalink/`, `multi_permalinks`, `story_fbid`. Khi không có thuộc tính đánh dấu nội dung, chỉ đọc phần nằm giữa tiêu đề bài và hàng nút Thích/Bình luận; không lấy toàn bộ khối chứa cả bình luận. Nếu không đọc được link bài nào, nhóm được báo lỗi đọc trang thay vì kết luận không có khách. `logs/app.log` ghi số link bài đọc được, khối hiển thị, bài thiếu nội dung và lỗi trích xuất theo từng nhóm. Sau khi cập nhật mã, khởi động lại ứng dụng để tác vụ mới dùng bộ đọc mới.

Trước khi mở Facebook, ứng dụng lọc **tên nhóm đã đồng bộ** theo **Sản phẩm quan tâm**, hoặc nhóm hàng và thương hiệu trong **Danh mục công ty** khi bật danh mục. Có nhận dạng tên viết tắt, không dấu và các chủ đề liên quan: bán thiết bị bếp có thể quét nhóm Tủ bếp, Nhà bếp, Yêu Bếp, Gia dụng. Nhóm không khớp hoặc thiếu tên bị bỏ qua, kể cả khi chọn riêng nhóm đó hoặc qua bộ sưu tập. Nếu không có nhóm phù hợp thì không mở trang nào. Tiến độ và tổng kết báo số nhóm giữ/bỏ; log ghi tên và link nhóm bị bỏ qua. Tên nhóm chỉ là tiêu chí chọn nguồn, mỗi bài/bình luận vẫn được lọc tiếp theo nhu cầu và sản phẩm.

Chỉ giữ bài người dùng có nhu cầu về sản phẩm; bài quảng cáo luôn bị loại khỏi kết quả. Nếu bật tìm trong bình luận, bài quảng cáo đúng sản phẩm chỉ được đọc khi có ít nhất **10 bình luận** (có thể chỉnh ngưỡng trên màn hình); ít hơn thì bỏ qua ngay, số lượt thích không được tính thay bình luận. Ưu tiên luồng người dùng hỏi trước, sau đó mới đến quảng cáo đủ ngưỡng. Mỗi nhóm đọc tối đa 10 luồng: bài hỏi mở rộng tối đa 6 lượt, quảng cáo chỉ lướt tối đa 2 lượt; chỉ giữ bình luận có nhu cầu mua/tư vấn, bỏ bình luận bán hàng. Nếu chỉ có quảng cáo đủ ngưỡng thì dành khoảng 80% thời gian để tiếp tục tìm bài người dùng, phần còn lại đọc bình luận; khi đã thấy luồng hỏi mua thì dành khoảng 55% để tìm bài. Bộ nhận diện nhu cầu và sản phẩm quyết định giữ bài, không bắt buộc trùng thêm danh sách từ khóa quét. Câu hỏi ngắn như “xin giá” dùng sản phẩm từ bài gốc; bài gốc có nhiều sản phẩm thì cần duyệt thủ công. Mỗi bình luận được lưu riêng theo link `comment_id`, giữ tên, nội dung và ngày của chính bình luận. Có thể tắt tìm trong bình luận để chỉ tìm bài. Việc quét không tự gửi trả lời.

## Danh mục hàng hóa

Vào Comment → **Danh mục công ty** để xem hoặc nạp Excel cập nhật. **Thử sản phẩm công ty** chạy ví dụ offline. Tồn kho là số từ tệp nhập; bình luận mời inbox để kiểm tra hàng và báo giá, không tự cam kết hàng sẵn.

## Kết nối & chăm sóc theo ngành, khu vực

Mục **Kết nối & chăm sóc** trên sidebar gồm bốn tab: **Đối tượng**, **Nội dung và lịch**, **Hàng đợi**, **Lịch sử hàng ngày**. Đây là luồng riêng cho tác vụ đã chọn và duyệt, dùng profile đang đăng nhập trong Accounts.

1. **Tìm nhóm và người dùng**: chọn profile, nhập ngành (gara, phụ tùng, nội thất, gia dụng...), khu vực và/hoặc từ khóa. Chọn loại tìm kiếm rồi bấm **Tìm trên Facebook**. Kết quả được lưu riêng cho từng nick; có dừng tìm và giữ kết quả đã đọc. Kết quả tìm kiếm và nhãn ngành/khu vực chưa phải xác minh địa chỉ/nghề nghiệp của đối tượng. Chọn một dòng rồi **Mở đối tượng trong nick** để đối chiếu.
2. **Tham gia nhóm / kết bạn**: chọn tối đa 10 nhóm hoặc người dùng, sang tab 2, chọn tác vụ rồi xem và duyệt lịch. Facebook đã hiển thị đang chờ hoặc đã kết nối thì bỏ qua. Nếu nhóm mở câu hỏi, quy tắc hoặc hộp xác nhận, tác vụ chuyển **Cần kiểm tra** để bạn hoàn tất trực tiếp trên profile; ứng dụng không tự trả lời câu hỏi. Tham gia nhóm không đồng nghĩa quản trị viên đã chấp thuận.
3. **Đăng bài theo khu vực/ngành**: bấm **Nạp nhóm đã tham gia**, chọn nhóm rồi **Gắn ngành / khu vực**. Lọc theo nhãn để chọn đúng tệp, sang tab 2 chọn **Đăng bài nhóm**, soạn nội dung và thêm ảnh/video nếu cần. Đăng bài chỉ dùng nhóm đã đồng bộ của đúng nick; sau khi tham gia nhóm mới, quét lại trong Groups trước. Có thể đặt giờ bắt đầu và chu kỳ lặp theo ngày.
4. **Duy trì tương tác**: chọn người dùng hoặc link bài viết, chọn **Tương tác bài mới** và đặt chu kỳ theo ngày. Mỗi lượt tìm một bài của đúng người dùng trong phần đang hiển thị để thích; không bấm thích của bình luận, không bỏ thích bài đã thích. Nếu chưa thấy bài phù hợp thì ghi nhận bỏ qua và đợi lịch tiếp theo. Tác vụ không tự viết bình luận hoặc nhận xét thay bạn.
5. **Nhắn tin**: thêm loại đối tượng **Hội thoại** bằng link `facebook.com/messages/t/123/`, `facebook.com/messages/e2ee/t/123/` hoặc `messenger.com/t/123/`. Người dùng có UID số có thể dùng **Tạo đích nhắn tin từ UID**; nếu Facebook chuyển sang hội thoại mã hóa có ID khác, thêm lại đúng link đang mở của hội thoại. Chọn tác vụ Nhắn tin, nhập nội dung, xem từng người nhận và nội dung trước khi duyệt. Tin nhắn chạy một lần, không tự lặp. Nội dung hỗ trợ `{ten}`, `{nganh}`, `{khu_vuc}`; lịch lưu nội dung cụ thể cho từng đích.
6. **Quản lý lịch**: lịch được lưu trên máy và chạy khi ứng dụng mở, tùy chọn **Chạy các lịch đến hạn** bật, đúng nick đăng nhập và rảnh. Mỗi nick chạy một tác vụ tại một thời điểm; có giới hạn lượt theo loại tác vụ/ngày và khoảng nghỉ giữa các tác vụ. Bộ đếm ngày dùng UTC+7 và tính cả lượt lỗi/chưa xác nhận. Lịch lặp bỏ qua các kỳ đã lỡ, không chạy dồn khi mở lại máy. Tạm dừng/tiếp tục/hủy từng lịch trong Hàng đợi; hủy tác vụ đang chạy có hiệu lực ở điểm kiểm tra tiếp theo.
7. **Lịch sử ngày**: chọn ngày UTC+7, nick hoặc tất cả nick, loại tác vụ và nội dung tìm kiếm; xuất CSV theo đúng bộ lọc. Kết quả phân biệt đã gửi bài, đã gửi tin, đã gửi yêu cầu, bỏ qua, lỗi và cần kiểm tra. “Đã gửi tin” là thấy nội dung trong hội thoại, không phải xác nhận đã đọc; bài đăng có thể còn chờ duyệt.

Các tác vụ trùng nick/đích/nội dung đã chờ, đang chạy, hoàn tất hoặc cần kiểm tra không được thêm lại. Tác vụ bị gián đoạn không tự gửi lại; sau 10 phút chuyển **Cần kiểm tra**. Xem Facebook và lịch sử trước khi hủy lịch cũ rồi tạo lại nếu cần. Hàng đợi được giữ khi đóng ứng dụng; lịch không chạy khi ứng dụng đã tắt. Khi tắt giữa một thao tác gửi, kết quả có thể cần kiểm tra trực tiếp.

Các bảng `outreach_audiences`, `outreach_jobs`, `outreach_activity`, `outreach_settings` được tạo bổ sung trong `data/app.db`. Trạng thái bật/tắt chạy lịch cũng được giữ qua các lần mở ứng dụng. Không cần token hoặc mật khẩu mới; các thao tác chạy trên QThread đang sở hữu profile. Kiểm thử tính năng dùng database tạm và trang Playwright bị chặn toàn bộ yêu cầu mạng, không gửi lời mời/tin nhắn trên Facebook thật.

## Bộ sưu tập nhóm, kho nội dung và gợi ý AI theo từng bài

- **Posts → Chọn nhóm Facebook**: chọn nhóm, đặt tên và lưu bộ sưu tập. Có thể áp dụng, cập nhật hoặc xóa bộ sưu tập; mỗi bộ thuộc riêng một nick. Nhóm không còn trong danh sách đã đồng bộ sẽ không được tự chọn.
- **Comment → Nhóm Facebook cần tìm**: chọn tất cả nhóm, một nhóm hoặc bộ sưu tập của nick. Bấm **Làm mới nguồn** sau khi tạo bộ sưu tập trong Posts.
- **Comment → AI cho các bài đã chọn**: chọn từ 1 đến 10 bài để tạo gợi ý riêng qua OpenAI. Cần cấu hình `OPENAI_API_KEY` và `OPENAI_MODEL` trong `.env`. Nội dung bài đã chọn và thông tin cửa hàng được gửi tới OpenAI. Có bảng duyệt và sửa từng bình luận trước khi áp dụng. Lỗi một bài không làm mất gợi ý các bài khác. **Dừng gợi ý AI** dừng các bài tiếp theo sau khi yêu cầu hiện tại kết thúc.
- Sau khi áp dụng gợi ý, bấm **Lưu bản nháp đã chọn** để lưu vào Customers. Bài đã sửa trong lúc AI chạy không bị ghi đè. Kết quả từ bình luận có thể gửi qua **Trả lời bình luận đã chọn** sau khi duyệt nội dung.
- **Posts → Lưu thành mẫu / Mở kho nội dung**: lưu nội dung và đường dẫn ảnh/video để dùng lại, tìm mẫu theo tên hoặc nội dung, xóa mẫu không dùng. Cần giữ các tệp media tại đường dẫn đã lưu.
- **Posts** hỗ trợ lần lượt từng nick hoặc song song giữa các nick; trong mỗi nick, các đích luôn chạy lần lượt. Có khoảng nghỉ 0–3600 giây, nút dừng và tự bỏ qua các đích còn lại của nick khi gặp lỗi. Giữ giới hạn 5 nhóm và 5 nick mỗi lượt, xác nhận trước khi đăng. Nội dung đã duyệt được tự lưu thành bản nháp trước khi chạy.
- **Reports**: lịch sử từng đích với trạng thái Đã gửi, Lỗi hoặc Bỏ qua/đã dừng; lọc ngày, trạng thái, tìm kiếm không dấu và xuất CSV theo bộ lọc. Đã gửi không đồng nghĩa bài trong nhóm đã được quản trị viên phê duyệt.

Các bảng `publishing_collections`, `publishing_templates` và `publishing_receipts` được tạo bổ sung trong `data/app.db` khi mở chức năng. Các lịch đăng bài theo tệp và tác vụ kết nối ở mục **Kết nối & chăm sóc** có lịch sử riêng trong tab **Lịch sử hàng ngày**. Tìm từ quảng cáo và quản trị nhóm chưa nằm trong các luồng này.

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
