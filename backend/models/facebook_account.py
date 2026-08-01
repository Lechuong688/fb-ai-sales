from dataclasses import dataclass


@dataclass
class FacebookAccount:

    id: int

    name: str

    uid: str

    profile: str

    status: str = "Offline"