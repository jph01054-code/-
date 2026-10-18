import json
import os
from pathlib import Path
from .rules import Settings, defaults


def data_dir():
    return Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'SmartStoreAssistantV2'


def load(path):
    if not path.exists():
        return defaults(), None
    try:
        values = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(values, dict):
            raise ValueError('설정 형식 오류')
        values['mode'] = 'demo'
        return Settings.from_dict(values), None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return defaults(), f'저장된 설정을 읽지 못해 기본값을 표시합니다: {type(exc).__name__}'


def save(path, settings):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
