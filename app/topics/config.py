"""Versioned channel strategy defaults; project config.yaml may override them."""
from .discovery import OFFICIAL

VERSION = 'topic-strategy-v1'
DEFAULTS = {
    'concept': '복잡한 돈과 집 이야기를 쉽고 재미있게 설명하는 경제 인스타툰',
    'audience': ['25~39세 직장인', '사회초년생', '신혼부부', '1인 가구'],
    'quota': {'housing': 9, 'finance': 7, 'economy': 4},
    'weekly_count': 3,
    'priority_threshold': 80,
    'review_threshold': 65,
    'news_recheck_hours': 24,
    'news_max_age_days': 7,
    'evergreen_recheck_days': 30,
    'official_domains': list(OFFICIAL),
    'rss_sources': [],
    'character': 'tory_01',
    'character_rights': 'owned',
}
