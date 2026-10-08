"""Small atomic JSON records. Audit revisions preserve scores/evidence across production and edits."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

from .schema import Topic, Evidence, now


def identifier(prefix: str, value: str) -> str:
    return prefix + '_' + hashlib.sha256(value.encode()).hexdigest()[:16]


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.errors = []

    def path(self, kind: str, key: str) -> Path:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', key):
            raise ValueError('잘못된 전략 기록 ID')
        return self.root / kind / (key + '.json')

    def save_topic(self, topic: Topic, action: str = 'update') -> Topic:
        data = topic.model_dump()
        write(self.path('topics', topic.topic_id), data)
        write(self.root / 'audit' / topic.topic_id / (uuid.uuid4().hex + '.json'),
              {'action': action, 'at': now(), 'config_version': 'topic-strategy-v1', 'topic': data})
        return topic

    def get(self, key: str) -> Topic:
        return Topic.model_validate_json(self.path('topics', key).read_text(encoding='utf-8'))

    def topics(self) -> list[Topic]:
        topics = []
        self.errors = []
        for path in sorted((self.root / 'topics').glob('*.json')):
            try:
                topics.append(Topic.model_validate_json(path.read_text(encoding='utf-8')))
            except (ValueError, OSError) as exc:
                self.errors.append({'file':path.name, 'error':type(exc).__name__})
        return topics

    def save_evidence(self, row: Evidence) -> None:
        path = self.path('evidence', row.evidence_id)
        # Keep original text as a separate immutable snapshot when refreshing a URL.
        if path.exists():
            write(self.root / 'evidence_history' / row.evidence_id / (uuid.uuid4().hex + '.json'), self.read(path))
        write(path, row.model_dump())

    def evidence(self, topic: Topic) -> list[Evidence]:
        return [Evidence.model_validate_json(self.path('evidence', key).read_text(encoding='utf-8')) for key in topic.evidence_ids]

    @staticmethod
    def read(path: Path, default=None):
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

    def history(self) -> list[dict]:
        return self.read(self.root / 'publication_history.json', [])

    def add_publication(self, record: dict) -> None:
        rows = self.history()
        if not any(r['topic_id'] == record['topic_id'] and r.get('project_id') == record.get('project_id') for r in rows):
            write(self.root / 'publication_history.json', [*rows, record])
