from PySide6.QtCore import QObject, Signal, Slot

from backend.browser.pool import browser_pool
from backend.services.account_service import AccountService
from backend.services.group_service import GroupService
from backend.services.logger import AppLogger


class BrowserWorker(QObject):

    finished = Signal()
    error = Signal(str)

    account_updated = Signal(object)
    groups_synced = Signal(int)

    @Slot(object)
    def open_profile(self, account):

        try:

            profile_name = account.profile.strip()

            if not profile_name:

                raise RuntimeError(
                    "Profile không được để trống."
                )

            AppLogger.log(
                f"Đang mở Profile: {profile_name}"
            )

            browser = browser_pool.get(
                profile_name
            )

            browser.start(
                profile_name
            )

            facebook = browser.facebook

            browser.open_url(
                "https://www.facebook.com/"
            )

            AppLogger.log(
                f"Profile {profile_name} đã được mở."
            )

            # =================================================
            # CHỜ LOGIN
            # =================================================

            AppLogger.log(
                "Đang chờ Facebook đăng nhập..."
            )

            import time

            while True:

                try:

                    if facebook.is_logged_in():
                        break

                except Exception:
                    pass

                time.sleep(2)

            AppLogger.log(
                "Đã phát hiện Facebook đăng nhập."
            )

            # =================================================
            # PROFILE
            # =================================================

            profile = facebook.get_profile()

            uid = profile.get(
                "uid",
                ""
            ).strip()

            name = profile.get(
                "name",
                ""
            ).strip()

            if name:

                AppLogger.log(
                    f"Facebook: {name}"
                )

            else:

                AppLogger.log(
                    "Facebook: chưa lấy được tên."
                )

            if uid:

                AppLogger.log(
                    f"UID: {uid}"
                )

            else:

                AppLogger.log(
                    "UID: chưa lấy được."
                )

            # Không cho www.facebook.com
            if not uid:

                raise RuntimeError(
                    "Facebook đã đăng nhập nhưng "
                    "không lấy được UID."
                )

            # =================================================
            # UPDATE ACCOUNT
            # =================================================

            account.uid = uid

            if name:
                account.name = name

            account.status = "Online"

            AccountService().update(
                account
            )

            self.account_updated.emit(
                account
            )

            # =================================================
            # GROUPS
            # =================================================

            AppLogger.log(
                "Đang quét Groups Facebook..."
            )

            groups = facebook.get_groups()

            service = GroupService()

            added = 0

            for group in groups:

                try:

                    result = service.create(
                        group["name"],
                        group["url"]
                    )

                    if result:
                        added += 1

                except Exception as e:

                    AppLogger.log(
                        f"Lỗi group: {e}"
                    )

            AppLogger.log(
                f"Đã quét {len(groups)} nhóm, "
                f"thêm mới {added} nhóm."
            )

            self.groups_synced.emit(
                added
            )

            self.finished.emit()

        except Exception as e:

            AppLogger.log(
                f"Lỗi Browser: {e}"
            )

            self.error.emit(
                str(e)
            )

            self.finished.emit()