"""minerUOCR 资料目录只读扫描。

只读取 <root>/<参与者>/visits.json 与文件名，不写任何文件、不调用 minerUOCR 服务。
匹配规则：
1. 目录名即筛选号（如 S01011）；
2. 目录名是姓名缩写时，目录内文件名出现且只出现一个本项目筛选号。
"""

import json
import os
import re

SCREENING_RE = re.compile(r'S\d{5}', re.I)
VISITS_FILE = 'visits.json'


def _load_visits(path):
    """兼容 UTF-8 / GBK 的 visits.json；结构异常时返回空列表。"""
    for enc in ('utf-8', 'gbk'):
        try:
            with open(path, 'r', encoding=enc) as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        except OSError:
            return []
    return []


def _count_files(path):
    n = 0
    for _dp, _dirs, files in os.walk(path):
        n += sum(1 for f in files if not f.startswith('.'))
    return n


def _screenings_in_files(path):
    found = set()
    for _dp, _dirs, files in os.walk(path):
        for fn in files:
            found.update(m.upper() for m in SCREENING_RE.findall(fn))
    return found


def scan(root_dir, patient_ids=None):
    """扫描目录，返回 (mapped, unmatched, total_dirs, dated_dirs)。

    mapped = {筛选号: {dir, rel_path, visits:[{label,date}], doc_count, match_by}}
    unmatched = 有访视日期但无法匹配到本项目患者的目录（预筛/缩写目录）
    """
    mapped = {}
    unmatched = []
    pid_set = {str(x).strip().upper() for x in (patient_ids or []) if x}
    try:
        entries = sorted(os.scandir(root_dir), key=lambda e: e.name)
    except OSError:
        return mapped, unmatched, 0, 0

    total = 0
    dated = 0
    for entry in entries:
        if not entry.is_dir():
            continue
        total += 1
        visits_path = os.path.join(entry.path, VISITS_FILE)
        if not os.path.isfile(visits_path):
            continue

        items = []
        for v in _load_visits(visits_path):
            if not isinstance(v, dict):
                continue
            label = str(v.get('label') or '').strip()
            date = str(v.get('date') or '').strip()
            if label and date:
                items.append({'label': label, 'date': date})
        if not items:
            continue
        dated += 1

        name = entry.name
        key = name.upper()
        match_by = None
        if SCREENING_RE.fullmatch(name):
            if not pid_set or key in pid_set:
                match_by = 'dirname'
        elif pid_set:
            hits = _screenings_in_files(entry.path) & pid_set
            if len(hits) == 1:
                key = hits.pop()
                match_by = 'filename'

        if not match_by:
            unmatched.append({'dir': name, 'visits': len(items)})
            continue

        mapped[key] = {
            'dir': name,
            'rel_path': name,
            'visits': items,
            'doc_count': _count_files(entry.path),
            'match_by': match_by,
        }
    return mapped, unmatched, total, dated
