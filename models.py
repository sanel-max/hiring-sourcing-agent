from dataclasses import dataclass, field


@dataclass
class BinaryFilter:
    label: str          # e.g. "Worked as a backend engineer for 12+ months"
    description: str    # longer context the model uses to judge it


@dataclass
class Role:
    id: str
    name: str
    job_description: str
    good_examples: str = ""     # free text: what a strong candidate looks like
    bad_examples: str = ""      # free text: red flags / disqualifiers
    binary_filters: list = field(default_factory=list)   # list[BinaryFilter]
    keywords: list = field(default_factory=list)          # search keywords/titles used to query each platform
    location: str = ""
    platforms: list = field(default_factory=lambda: ["linkedin", "twitter", "instagram"])
    auto_search: bool = False   # opt-in: re-searched automatically once/day, new candidates only

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d["id"],
            name=d["name"],
            job_description=d.get("job_description", ""),
            good_examples=d.get("good_examples", ""),
            bad_examples=d.get("bad_examples", ""),
            binary_filters=[BinaryFilter(**f) for f in d.get("binary_filters", [])],
            keywords=d.get("keywords", []),
            location=d.get("location", ""),
            platforms=d.get("platforms") or ["linkedin", "twitter", "instagram"],
            auto_search=bool(d.get("auto_search", False)),
        )


@dataclass
class Candidate:
    platform: str
    handle: str
    name: str
    profile_url: str
    bio: str = ""
    headline: str = ""
    extra: dict = field(default_factory=dict)   # raw platform-specific fields kept for scoring context
