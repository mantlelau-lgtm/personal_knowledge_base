from __future__ import annotations


DEFAULT_SENSITIVE_KEYWORDS = ("salary", "password", "secret", "private")


class PrivacyScreener:
    def __init__(self, sensitive_keywords: tuple[str, ...] | None = None) -> None:
        self.sensitive_keywords = sensitive_keywords or DEFAULT_SENSITIVE_KEYWORDS

    def filter_scope(self, scope: str, blacklist_topics: list[str]) -> tuple[bool, str]:
        text = (scope or "").lower()
        for keyword in self.sensitive_keywords:
            if keyword and keyword.lower() in text:
                return False, f"contains sensitive keyword: {keyword}"
        for topic in blacklist_topics or []:
            if topic and topic.lower() in text:
                return False, f"hits blacklist topic: {topic}"
        return True, ""
