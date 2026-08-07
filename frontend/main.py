import sys
from pathlib import Path

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from frontend.main_window import MainWindow

from backend.services.session_service import SessionService

def load_styles(app, base_dir: Path):
    # Sử dụng đường dẫn tuyệt đối, an toàn dù bạn chạy script từ bất kỳ đâu
    qss_path = base_dir / "styles" / "theme.qss"

    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    else:
        print(f"[CẢNH BÁO] Không tìm thấy file giao diện tại: {qss_path}")


def main():
    app = QApplication(sys.argv)

    # 1. Base Style "Fusion": Giúp giao diện phẳng và đồng bộ trên mọi Hệ điều hành
    app.setStyle("Fusion")

    # 2. Global Font: Cài đặt font chữ mặc định chuẩn UI hiện đại cho toàn bộ App
    # (Bạn có thể đổi thành "Inter", "Roboto" hoặc font chữ thương hiệu của bạn)
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # 3. Load CSS (theme.qss sẽ ghi đè lên các thành phần được định nghĩa)
    # Lấy thư mục gốc chứa file main.py này
    base_dir = Path(__file__).resolve().parent
    load_styles(app, base_dir)

    # 4. Khởi tạo và hiển thị MainWindow
    window = MainWindow()
    
    # (Tùy chọn) Thêm Icon cho ứng dụng trên thanh Taskbar
    # icon_path = base_dir / "frontend" / "assets" / "app_icon.png"
    # if icon_path.exists():
    #     app.setWindowIcon(QIcon(str(icon_path)))

    window.show()


    session_service = SessionService()

    session_service.start()
    # 5. Khởi chạy Event Loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()