import re
from urllib.parse import unquote, urlparse

from backend.database.models.group import Group
from backend.database.repositories.group_repository import GroupRepository
from backend.database.repositories.profile_group_repository import (
    ProfileGroupRepository,
)


class GroupService:

    def __init__(self):

        self.repo = GroupRepository()
        self.profile_groups = ProfileGroupRepository()

    def get_all(self):

        return self.repo.get_all()

    @staticmethod
    def clean_group_name(name, url=""):
        text = str(name or "").replace("\u00a0", " ").strip()
        text = re.sub(
            r"\s*(?:Lần hoạt động gần nhất|Last active)\s*:?\s*.*$",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        lines = [re.sub(r"\s+", " ", line).strip(" ·•\t:-") for line in text.splitlines()]
        ignored = {
            "groups",
            "facebook groups",
            "see all",
            "xem tất cả",
            "nhóm",
            "xem nhóm",
            "see group",
            "view group",
            "xem thêm",
            "see more",
            "your groups",
            "groups you manage",
            "nhóm bạn đã tham gia",
            "tất cả các nhóm bạn đã tham gia",
            "all groups you have joined",
            "all groups you've joined",
            "join group",
            "join this group",
            "tham gia nhóm",
            "nhóm của bạn",
            "các nhóm của bạn",
        }
        time_only = re.compile(
            r"\d+\s*(?:phút|ph|giờ|ngày|tuần|tháng|năm|minutes?|mins?|hours?|days?|weeks?|months?|years?)(?:\s*(?:trước|ago))?",
            re.IGNORECASE,
        )
        for line in lines:
            line = re.sub(r"\s*\(\d+\)\s*$", "", line)
            if not line or line.casefold() in ignored or time_only.fullmatch(line):
                continue
            # Strip a trailing numeric group id that older scraping stored as part of the name.
            line = re.sub(r"\s*[·•|]\s*\d{8,}\s*$", "", line).strip()
            if time_only.fullmatch(line):
                continue
            if line and not line.casefold().startswith("lần hoạt động gần nhất"):
                return line
        parsed = urlparse(url or "")
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        group_id = parts[1] if len(parts) > 1 and parts[0] == "groups" else ""
        return f"Facebook Group {group_id}" if group_id else "Facebook Group"

    def create(self, name, url):

        name = self.clean_group_name(name, url)
        url = (url or "").strip()

        if not url:
            return None

        # Không thêm trùng
        existing = self.repo.get_by_url(url)

        if existing:
            old_name = (existing.name or "").strip()
            is_real_name = name and not name.startswith("Facebook Group")
            if is_real_name and old_name != name:
                existing.name = name
                self.repo.update(existing)
            return existing

        group = Group(
            name=name or "Facebook Group",
            url=url,
            member_count="0",
            privacy="Unknown",
            status="Ready"
        )

        return self.repo.add(
            group
        )

    def link_to_profile(self, profile, group_id):
        profile = (profile or "").strip()
        if not profile or not group_id:
            return None
        return self.profile_groups.link(profile, group_id)

    def get_for_profile(self, profile):
        linked_groups = self.profile_groups.get_groups_for_profile(profile)
        groups = []
        invalid_ids = []
        for group in linked_groups:
            clean_name = self.clean_group_name(group.name, group.url)
            if clean_name.startswith("Facebook Group"):
                invalid_ids.append(group.id)
                continue
            if group.name != clean_name:
                group.name = clean_name
                self.repo.update(group)
            groups.append(group)
        self.profile_groups.unlink_many(profile, invalid_ids)
        return groups

    def sync_profile_groups(self, profile, group_ids):
        return self.profile_groups.sync_profile_groups(profile, group_ids)

    def delete(self, group_id):

        self.repo.delete(
            group_id
        )
