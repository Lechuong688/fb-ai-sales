from PySide6.QtWidgets import QLabel

class Breadcrumb(QLabel):
    def __init__(self):
        super().__init__()

        self.setObjectName("breadcrumb")
        
        # Gọi mặc định khi mới khởi tạo
        self.set_page("Dashboard")

    def set_page(self, page_or_path):
        """
        Hàm set_page giờ đây có thể nhận:
        - Chuỗi (str): set_page("Dashboard") -> 🏠 Dashboard
        - Danh sách (list): set_page(["Dashboard", "Cài đặt"]) -> 🏠 Dashboard ❯ Cài đặt
        """
        icon = "🏠"
        
        if isinstance(page_or_path, list):
            # Nối các phần tử bằng ký tự mũi tên ' ❯ '
            path_str = " ❯ ".join(page_or_path)
            self.setText(f"{icon} {path_str}")
        else:
            # Giữ nguyên hành vi cũ nếu truyền vào một chuỗi
            self.setText(f"{icon} {page_or_path}")