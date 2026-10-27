import json
from pathlib import Path


class ProfileLabelService:
    """Store editable display labels without renaming browser data folders."""

    def __init__(self, path=Path("data/profile_labels.json")):
        self.path = Path(path)
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.labels = {
                str(profile): str(label)
                for profile, label in data.items()
                if isinstance(label, str)
            }
        else:
            self.labels = {}

    def get_label(self, profile):
        return self.labels.get(profile, profile)

    def set_label(self, profile, label):
        label = (label or "").strip()
        if label and label != profile:
            self.labels[profile] = label
        else:
            self.labels.pop(profile, None)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(self.labels, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
        return self.get_label(profile)
