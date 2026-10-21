"""Metadata-only directory index; no source file contents are opened."""
import difflib
import json
import math
import os
from pathlib import Path
import threading
import time

class LocalIndex:
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve()
        self.lock = threading.RLock()
        self.scan_lock = threading.Lock()
        self.entries = {}
        self.last_refresh = None
        self.skipped = 0
        self.reload()
        self.rebuild()

    def reload(self):
        cfg = json.loads(self.config_path.read_text(encoding='utf-8-sig'))
        if set(cfg) - {'dirs', 'exclude_hidden', 'refresh_interval_seconds'}:
            raise ValueError('Unknown config keys')
        dirs = cfg.get('dirs')
        if not isinstance(dirs, list) or not dirs or any(not isinstance(p, str) or not p.strip() for p in dirs):
            raise ValueError('dirs must be a nonempty list of paths')
        if type(cfg.get('exclude_hidden', True)) is not bool:
            raise ValueError('exclude_hidden must be boolean')
        interval = cfg.get('refresh_interval_seconds', 600)
        if type(interval) not in (int, float) or not math.isfinite(interval) or interval < 1:
            raise ValueError('refresh_interval_seconds must be >= 1')
        roots = []
        for raw in dirs:
            p = Path(os.path.expandvars(raw)).expanduser()
            p = (self.config_path.parent / p).resolve() if not p.is_absolute() else p.resolve()
            if not p.is_dir():
                raise ValueError(f'Configured directory unavailable: {p}')
            roots.append(p)
        self.roots = tuple(dict.fromkeys(roots))
        self.exclude_hidden = cfg.get('exclude_hidden', True)
        self.interval = interval

    def allowed(self, path):
        p = Path(path).resolve()
        for root in self.roots:
            if p == root or root in p.parents:
                if self.exclude_hidden and any(self.hidden(part) for part in [p, *p.parents] if part != root and root in part.parents):
                    raise ValueError('Hidden path excluded')
                return p
        raise ValueError('Path outside configured roots')

    @staticmethod
    def hidden(path):
        if path.name.startswith('.'):
            return True
        try:
            return bool(getattr(path.stat(), 'st_file_attributes', 0) & 2)
        except OSError:
            return False

    @staticmethod
    def metadata(path):
        st = path.stat()
        return {'path': str(path), 'name': path.name, 'parent': str(path.parent),
                'kind': 'directory' if path.is_dir() else 'file', 'size': st.st_size,
                'extension': path.suffix.lower(), 'modified_time': st.st_mtime,
                'accessed_time': st.st_atime}

    def rebuild(self):
        with self.scan_lock:
            self.reload()
            entries, skipped = {}, 0
            def scan_error(_):
                nonlocal skipped
                skipped += 1
            for root in self.roots:
                entries[str(root)] = self.metadata(root)
                for parent, dirs, files in os.walk(root, followlinks=False, onerror=scan_error):
                    base = Path(parent)
                    dirs[:] = [n for n in dirs if not (base / n).is_symlink() and not (self.exclude_hidden and self.hidden(base / n))]
                    for name in dirs + files:
                        p = base / name
                        if p.is_symlink() or (self.exclude_hidden and self.hidden(p)):
                            continue
                        try:
                            entries[str(p)] = self.metadata(p)
                        except OSError:
                            skipped += 1
            with self.lock:
                self.entries = entries
                self.last_refresh = time.time()
                self.skipped = skipped
            return {'indexed_entries': len(entries), 'skipped': skipped, 'refreshed_at': self.last_refresh}

    @staticmethod
    def page(rows, offset, limit):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('offset >= 0; limit between 1 and 100')
        end = offset + limit
        return {'items': rows[offset:end], 'total': len(rows), 'offset': offset,
                'next_offset': end if end < len(rows) else None}

    def browse(self, path=None, offset=0, limit=20):
        with self.lock:
            if path is None:
                rows = [self.entries[str(p)] for p in self.roots]
            else:
                p = self.allowed(path)
                if str(p) not in self.entries or self.entries[str(p)]['kind'] != 'directory':
                    raise ValueError('Directory not indexed')
                rows = [r for r in self.entries.values() if r['parent'] == str(p) and r['path'] != str(p)]
            rows.sort(key=lambda r: (r['kind'] != 'directory', r['name'].casefold(), r['path']))
            return self.page(rows, offset, limit)

    def search(self, query='', kind='all', extension=None, sort_by='relevance', modified_since=None, accessed_since=None, offset=0, limit=20):
        if len(query) > 256 or kind not in ('all', 'file', 'directory') or sort_by not in ('relevance', 'modified', 'accessed'):
            raise ValueError('Invalid query, kind or sort_by')
        for value in (modified_since, accessed_since):
            if value is not None and not math.isfinite(value):
                raise ValueError('Time filters must be finite Unix timestamps')
        ext = extension.lower().lstrip('.') if extension else None
        q = query.casefold().strip()
        rows = []
        with self.lock:
            for item in self.entries.values():
                if kind != 'all' and item['kind'] != kind:
                    continue
                if ext is not None and (item['kind'] != 'file' or item['extension'].lstrip('.') != ext):
                    continue
                if modified_since is not None and item['modified_time'] < modified_since:
                    continue
                if accessed_since is not None and item['accessed_time'] < accessed_since:
                    continue
                score = 1.0 if not q or q in item['path'].casefold() else difflib.SequenceMatcher(None, q, item['name'].casefold()).ratio()
                if score >= 0.45:
                    rows.append(dict(item, score=round(score, 4)))
        key = {'relevance': 'score', 'modified': 'modified_time', 'accessed': 'accessed_time'}[sort_by]
        rows.sort(key=lambda r: (-r[key], r['path']))
        return self.page(rows, offset, limit)

    def get_metadata(self, path):
        with self.lock:
            p = self.allowed(path)
            if str(p) not in self.entries or p.is_symlink():
                raise ValueError('Path not indexed')
            return self.metadata(p)
