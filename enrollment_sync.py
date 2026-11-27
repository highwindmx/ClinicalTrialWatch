"""
入组表增量同步（clinWatch 核心模块）

职责：读取项目配置的 xlsx「入组」sheet，按筛选号增量创建参与者，并幂等回填
C1D1 用药、基线肿评与 EOT 治疗结束日期。只新增、不覆盖已有临床数据；C1D1 日期
即入组日期，药物名称取项目配置 default_drug_name，剂量取剂量组数字；癌种按原样
写入，剂量组去掉「回填 / 储备」等字样后匹配项目配置。

设计要点：
- 表头按名称识别（见 HEADER_ALIASES），列顺序变化不影响；
- 内容签名（sha256）只取筛选号（入组表 C 列）：只有新增/删除条目才触发自动同步，
  其他列改动不触发；手动扫描仍可回填 C1D1 / 基线等；
- 手动扫描可 force=True 强制执行，用于补录新列或重试失败行。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import threading
import time

import database

DEFAULT_SHEET = '入组'

# 用户可直接按这些列名调整 xlsx；别名用于兼容既有写法。
HEADER_ALIASES = {
    'screening':      ['筛选号', '筛选编号', '受试者筛选号', '患者编号', '筛选号screeningid'],
    'abbr':           ['参与者缩写', '受试者缩写', '缩写', '参与者代码'],
    'dose_group':     ['剂量组', '剂量组回填', '剂量组名称'],
    'sex':            ['性别'],
    'age':            ['年龄'],
    'ecog':           ['ecog', 'ecog评分', 'ecog评分0-5'],
    'cancer_type':    ['癌种', '癌肿', '癌肿类型', '肿瘤类型', '病理类型'],
    'enroll_date':    ['入组时间', '入组日期'],
    'eot_date':       ['eot日期', 'eot', '治疗结束', '治疗结束日期', 'end of treatment date', 'endtreatmentdate'],
    'baseline_date':  ['基线肿评日期', '基线评估日期', '基线影像日期', '基线检查日期', '基线日期'],
    'baseline_sod':   ['基线靶病灶sod', '基线靶病灶总和', '基线sod', '基线靶病灶径线和', '基线肿瘤径线和'],
}

# 剂量组中的非实质后缀，匹配配置前统一剔除
DOSE_NOISE = ('回填', '储备', '备份', '预留', 'backup')

_COLUMN_KEYS = tuple(HEADER_ALIASES.keys())


def _log(msg):
    print('[enroll-sync] ' + str(msg), flush=True)


def _norm_header(value):
    if value is None:
        return ''
    s = str(value)
    for ch in ('\r', '\n', '\t', ' ', '\u3000'):
        s = s.replace(ch, '')
    return s.strip().lower()


def _norm_name(value):
    """癌种/剂量组名称归一：仅去空白与换行，不改写文字本身。"""
    if value is None:
        return ''
    s = str(value)
    for ch in ('\r', '\n', '\t', '\u3000'):
        s = s.replace(ch, '')
    return s.strip()


def _to_text(value):
    if value is None:
        return ''
    s = str(value).strip()
    if not s or s.startswith('#') or s.lower() in ('nan', 'none', 'nat'):
        return ''
    return s


def _to_date(value):
    """datetime / date / Excel 序列号 / 常见日期字符串 -> YYYY-MM-DD；失败返回 None。"""
    if value is None or value == '':
        return None
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            from openpyxl.utils.datetime import from_excel
            d = from_excel(value)
            return d.date().isoformat() if isinstance(d, _dt.datetime) else d.isoformat()
        except Exception:
            return None
    s = str(value).strip()
    if not s or s.startswith('#'):
        return None
    m = re.search(r'(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})', s)
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def _to_number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(',', '')
    if not s or s.startswith('#'):
        return None
    m = re.fullmatch(r'-?\d+(?:\.\d+)?', s)
    return float(m.group()) if m else None


def _detect_columns(header_row):
    """按表头名称定位列索引，兼容 C1D1 / 基线列的常见写法。"""
    headers = [_norm_header(v) for v in (header_row or ())]
    cols = {}
    for key, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            a = _norm_header(alias)
            if a and a in headers:
                cols[key] = headers.index(a)
                break
    # 兜底：C1D1 / 基线列常带自定义后缀，用关键字识别
    for i, h in enumerate(headers):
        if not h:
            continue
        if 'baseline_date' not in cols and '基线' in h and ('日期' in h or '时间' in h or '影像' in h) and 'sod' not in h and '靶病灶' not in h:
            cols['baseline_date'] = i
        if 'baseline_sod' not in cols and '基线' in h and ('sod' in h or '总和' in h or '径线' in h or '靶病灶' in h):
            cols['baseline_sod'] = i
    return cols, headers


def read_enrollment_rows(path, sheet_name=DEFAULT_SHEET):
    """读取并返回规范化行列表；同时返回表头（供 UI 回显识别到的列）。"""
    if not path or not os.path.isfile(path):
        raise ValueError(f'入组表文件不存在: {path}')
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ValueError('缺少 openpyxl，请先安装: uv add openpyxl')

    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        if sheet_name not in wb.sheetnames:
            raise ValueError(f'工作簿中没有名为「{sheet_name}」的分页；现有分页: {", ".join(wb.sheetnames)}')
        ws = wb[sheet_name]
        it = ws.iter_rows(values_only=True)
        header = next(it, None)
        cols, headers = _detect_columns(header)
        if 'screening' not in cols:
            raise ValueError('未识别到「筛选号」列，请检查表头（可在项目配置中查看已识别列）')

        rows = []
        seen = set()
        for row_no, raw in enumerate(it, start=2):
            def cell(key):
                idx = cols.get(key)
                return raw[idx] if idx is not None and idx < len(raw) else None

            screening = _to_text(cell('screening'))
            # 过滤公式残留行（如 AC 列 #N/A、筛选号为空）
            if not screening or screening.startswith('#') or screening.lower() in ('nan', 'none'):
                continue
            if screening in seen:
                continue
            seen.add(screening)

            # 用户确认：C1D1 用药日期即入组日期，不再依赖 xlsx 额外列
            enroll_date = _to_date(cell('enroll_date'))
            rec = {
                'row': row_no,
                'screening': screening,
                'abbr': _to_text(cell('abbr')),
                'dose_group': _norm_name(cell('dose_group')),
                'sex': _to_text(cell('sex')),
                'age': _to_number(cell('age')),
                'ecog': _to_number(cell('ecog')),
                'cancer_type': _norm_name(cell('cancer_type')),
                'enroll_date': enroll_date,
                'eot_date': _to_date(cell('eot_date')),
                'c1d1_date': enroll_date,
                'baseline_date': _to_date(cell('baseline_date')),
                'baseline_sod': _to_number(cell('baseline_sod')),
            }
            rows.append(rec)
        return rows, {'columns': cols, 'headers': headers}
    finally:
        wb.close()


def compute_signature(rows):
    """签名看筛选号（C 列）+ EOT 日期：新增条目或治疗结束日期变化都触发自动同步。"""
    payload = json.dumps(
        [[str(r.get('screening') or '').strip(), r.get('eot_date')] for r in rows],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _clean_dose_group(text, configured):
    """去掉回填/储备等字样后匹配项目剂量组，返回 (规范名, id)。"""
    cleaned = _norm_name(text)
    if not cleaned:
        return '', None
    stripped = cleaned
    for w in DOSE_NOISE:
        stripped = stripped.replace(w, '')
    stripped = re.sub(r'\s+', '', stripped).strip()
    if not stripped:
        stripped = cleaned

    def canon(name):
        s = _norm_name(name)
        for w in DOSE_NOISE:
            s = s.replace(w, '')
        return re.sub(r'\s+', '', s).strip()

    for dg in configured:
        if canon(dg['name']) == stripped:
            return stripped, dg['id']
    return stripped, None


def _color_for(name):
    palette = ['#378ADD', '#80ffff', '#ffff00', '#00ff80', '#ff8040', '#c084fc', '#fb7185']
    h = int(hashlib.md5(name.encode('utf-8')).hexdigest(), 16)
    return palette[h % len(palette)]


def _dose_from_group(name):
    """剂量取剂量组中的数字部分：50mg回填 -> 50；纯数字 50 -> 50。"""
    s = str(name or '').strip()
    m = re.search(r'(\d+(?:\.\d+)?)\s*mg', s, re.IGNORECASE)
    if m:
        return float(m.group(1))
    if re.fullmatch(r'\d+(?:\.\d+)?', s):
        return float(s)
    return None


def _ensure_config_ids(project_id, dg_name, dg_id, ct_name, ct_id, ctx):
    """为未知的剂量组/癌种补建项目配置；癌种一律原样写入。"""
    if dg_name and not dg_id:
        proj = database.get_project(project_id) or {}
        dg_id = database.create_dose_group({
            'project_id': project_id, 'name': dg_name, 'color': _color_for(dg_name),
            'sort_order': ctx['dg_next'],
            'medication_interval': proj.get('medication_interval'),
            'assessment_interval': proj.get('assessment_interval'),
        })
        ctx['dg_next'] += 1
        if dg_name not in ctx['created_dose_groups']:
            ctx['created_dose_groups'].append(dg_name)
    if ct_name and not ct_id:
        ct_id = database.create_cancer_type({
            'project_id': project_id, 'name': ct_name, 'sort_order': ctx['ct_next'],
        })
        ctx['ct_next'] += 1
        if ct_name not in ctx['created_cancer_types']:
            ctx['created_cancer_types'].append(ct_name)
    return dg_id, ct_id


def sync_enrollment(project_id, path=None, sheet_name=None, force=False, dry_run=False):
    """
    执行一次同步。

    :param force: 手动扫描时为 True，忽略内容签名重复检查
    :param dry_run: 只解析不写库（用于校验）
    :return: dict（success / skipped / created / medications / assessments / warnings / errors / rows / columns）
    """
    cfg = database.get_xlsx_watch_config(project_id)
    path = path or cfg.get('xlsx_path')
    sheet = sheet_name or cfg.get('sheet_name') or DEFAULT_SHEET
    if not path:
        raise ValueError('尚未配置入组表路径，请先在「项目配置 → 入组表自动同步」中填写')

    rows, meta = read_enrollment_rows(path, sheet)
    signature = compute_signature(rows)
    result = {
        'success': True, 'skipped': False, 'reason': '',
        'rows': len(rows), 'columns': meta['columns'], 'signature': signature,
        'created': 0, 'medications': 0, 'assessments': 0,
        'existing': 0, 'would_create': 0, 'would_create_screenings': [],
        'created_screenings': [], 'created_patient_ids': [],
        'eot_updated': 0, 'eot_screenings': [],
        'eot_rows': sum(1 for r in rows if r.get('eot_date')),
        'warnings': [], 'errors': [],
        'created_dose_groups': [], 'created_cancer_types': [],
        'scanned_at': _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    if not force and not dry_run and cfg.get('last_signature') == signature:
        result.update(skipped=True, reason='内容未变化，跳过')
        return result

    if dry_run:
        # 试扫也要告诉用户「预计新增谁 / 库中已存在多少」，避免误以为漏建
        known = {p['patient_id'] for p in database.get_patients(project_id)}
        would = [r['screening'] for r in rows if r['screening'] not in known]
        result.update(
            reason='dry-run：未写入数据库',
            would_create=len(would),
            would_create_screenings=would,
            existing=len(rows) - len(would),
        )
        return result

    project = database.get_project(project_id) or {}
    # 默认药物名称由项目配置项提供；未配置时退回项目编号，不阻断同步
    drug_name = project.get('default_drug_name') or project.get('code') or '研究药物'
    configured_dg = database.get_dose_groups(project_id)
    configured_ct = database.get_cancer_types(project_id)
    ctx = {
        'dg_next': max([d.get('sort_order', 0) for d in configured_dg] or [-1]) + 1,
        'ct_next': max([c.get('sort_order', 0) for c in configured_ct] or [-1]) + 1,
        'created_dose_groups': result['created_dose_groups'],
        'created_cancer_types': result['created_cancer_types'],
    }

    for rec in rows:
        try:
            dg_name, dg_id = _clean_dose_group(rec['dose_group'], configured_dg)
            ct_name = rec['cancer_type']
            ct_id = next((c['id'] for c in configured_ct if c['name'] == ct_name), None)

            existing = database.find_patient_by_number(project_id, rec['screening'])
            if existing:
                patient_db_id = existing['id']
                result['existing'] += 1
                # 已存在者只做 C1D1 / 基线 / EOT 幂等回填，不改基线信息
                dg_id, ct_id = _ensure_config_ids(project_id, dg_name, dg_id, ct_name, ct_id, ctx)
                if rec['eot_date']:
                    cur = database.get_patient(patient_db_id) or {}
                    if not cur.get('end_treatment_date'):
                        cur_status = cur.get('status') or 'treatment'
                        database.update_patient(patient_db_id, {
                            'end_treatment_date': rec['eot_date'],
                            # treatment 自动转 followup；off_study 等手动状态保留
                            'status': 'followup' if cur_status == 'treatment' else cur_status,
                        })
                        result['eot_updated'] += 1
                        result['eot_screenings'].append(rec['screening'])
            else:
                dg_id, ct_id = _ensure_config_ids(project_id, dg_name, dg_id, ct_name, ct_id, ctx)
                custom = json.dumps({'abbr': rec['abbr']}, ensure_ascii=False) if rec['abbr'] else '{}'
                patient_db_id = database.create_patient({
                    'project_id': project_id,
                    'patient_id': rec['screening'],
                    'status': 'followup' if rec['eot_date'] else 'treatment',
                    'enroll_date': rec['enroll_date'],
                    'end_treatment_date': rec['eot_date'],
                    'dlt_observation': 1,
                    'age': rec['age'], 'sex': rec['sex'],
                    'cancer_type': ct_name, 'cancer_type_id': ct_id,
                    'ecog_score': rec['ecog'],
                    'dose_group': dg_name, 'dose_group_id': dg_id,
                    'custom_data': custom,
                })
                result['created'] += 1
                result['created_screenings'].append(rec['screening'])
                result['created_patient_ids'].append(patient_db_id)

                # 新建的配置项加入缓存，避免同一批次重复创建
            if dg_id and not any(d['id'] == dg_id for d in configured_dg):
                configured_dg.append({'id': dg_id, 'name': dg_name})
            if ct_id and not any(c['id'] == ct_id for c in configured_ct):
                configured_ct.append({'id': ct_id, 'name': ct_name})

            # C1D1 用药：日期=入组日期，已有则不重复写
            if rec['c1d1_date'] and not database.has_c1d1_medication(patient_db_id):
                database.create_medication({
                    'patient_id': patient_db_id,
                    'drug_name': drug_name,
                    'actual_date': rec['c1d1_date'],
                    'dose': _dose_from_group(dg_name),
                    'dose_unit': 'mg' if _dose_from_group(dg_name) is not None else None,
                    'cycle': 'C1D1',
                    'notes': '入组表自动同步',
                })
                result['medications'] += 1

            # 基线肿评：已有基线则不覆盖
            if (rec['baseline_date'] or rec['baseline_sod'] is not None) and not database.has_baseline_assessment(patient_db_id):
                database.create_tumor_assessment({
                    'patient_id': patient_db_id,
                    'eval_date': rec['baseline_date'] or rec['enroll_date'],
                    'eval_type': '基线',
                    'target_sod': rec['baseline_sod'],
                    'sod_change': 0,
                    'notes': '入组表自动同步',
                })
                result['assessments'] += 1

            if not rec['cancer_type']:
                result['warnings'].append(f"第{rec['row']}行：癌种为空")
            if not dg_id:
                result['warnings'].append(f"第{rec['row']}行：剂量组为空或未匹配")
        except Exception as exc:
            result['errors'].append(f"第{rec['row']}行({rec['screening']}): {exc}")
            _log(f'行同步失败: {exc}')

    if not any(r['c1d1_date'] for r in rows):
        result['warnings'].append('xlsx 未识别到「入组时间/日期」，本次未写入 C1D1 用药')
    if 'baseline_date' not in meta['columns'] and 'baseline_sod' not in meta['columns']:
        result['warnings'].append('xlsx 尚无「基线肿评日期 / 基线靶病灶SOD」列，本次未写入基线肿评')

    if result['warnings']:
        # 同类提示压成一条，避免刷屏
        seen = set()
        compact = []
        for w in result['warnings']:
            key = re.sub(r'第\d+行', '第N行', w)
            if key not in seen:
                seen.add(key)
                compact.append(key)
        result['warnings'] = compact

    if result['errors']:
        result['success'] = False

    database.save_xlsx_watch_config(project_id, {
        'last_scan_at': result['scanned_at'],
        'last_signature': signature,
        'last_result': json.dumps({k: result[k] for k in ('created', 'created_screenings', 'medications', 'assessments', 'existing', 'eot_updated', 'eot_screenings', 'warnings', 'errors')}, ensure_ascii=False),
    })
    _log(f'project={project_id} 新增参与者={result["created"]} C1D1={result["medications"]} 基线肿评={result["assessments"]} 错误={len(result["errors"])}')
    return result


# ==================== 后台监听 ====================

class EnrollmentWatchService:
    """watchdog 目录级监听 + 防抖 + 失败重试；watchdog 不可用时退化为空闲等待。"""

    def __init__(self, debounce=2.0, poll_interval=10.0):
        self.debounce = debounce
        self.poll_interval = poll_interval
        self._lock = threading.Lock()
        self._pending = {}          # path -> (fire_at, attempts)
        self._observer = None
        self._thread = None
        self._stop = threading.Event()
        self._keys = set()
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self._run, name='enroll-watch', daemon=True)
        self._thread.start()
        _log('后台监听已启动（不做启动扫描）')

    def stop(self):
        self._stop.set()
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass

    def reload(self):
        """配置保存后调用：重建监听目标。"""
        with self._lock:
            self._keys.add('reload')

    def _watchdog_available(self):
        try:
            from watchdog.observers import Observer  # noqa: F401
            return True
        except Exception:
            return False

    def _run(self):
        while not self._stop.is_set():
            try:
                self._refresh_observer()
                self._fire_due()
            except Exception as exc:
                _log(f'监听循环异常: {exc}')
            self._stop.wait(1.0)

    def _refresh_observer(self):
        configs = database.get_all_xlsx_watch_configs()
        keys = {(c['xlsx_path'], c.get('sheet_name') or DEFAULT_SHEET) for c in configs}
        need_rebuild = 'reload' in self._keys or keys != self._keys - {'reload'}
        if not need_rebuild:
            return
        self._keys = set(keys)
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
            self._observer = None
        if not keys or not self._watchdog_available():
            return

        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        service = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                if event.is_directory:
                    return
                path = os.path.abspath(event.src_path)
                service._queue_path(path)

        observer = Observer()
        dirs = set()
        for path, _sheet in keys:
            directory = os.path.dirname(os.path.abspath(path))
            if os.path.isdir(directory) and directory not in dirs:
                observer.schedule(Handler(), directory, recursive=False)
                dirs.add(directory)
        if dirs:
            observer.start()
            self._observer = observer
            _log(f'watchdog 监听目录 {len(dirs)} 个，文件 {len(keys)} 个')

    def _queue_path(self, changed_path):
        configs = database.get_all_xlsx_watch_configs()
        for cfg in configs:
            path = cfg.get('xlsx_path')
            if path and os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(changed_path)):
                with self._lock:
                    self._pending[path] = (time.time() + self.debounce, 0)
                return

    def _fire_due(self):
        now = time.time()
        with self._lock:
            due = [(p, v) for p, v in self._pending.items() if v[0] <= now]
            for p, _ in due:
                self._pending.pop(p, None)
        for path, (_fire_at, attempts) in due:
            configs = [c for c in database.get_all_xlsx_watch_configs()
                       if c.get('xlsx_path') and os.path.normcase(os.path.abspath(c['xlsx_path'])) == os.path.normcase(os.path.abspath(path))]
            for cfg in configs:
                try:
                    res = sync_enrollment(cfg['project_id'], path=path, sheet_name=cfg.get('sheet_name'), force=False)
                    # 自动同步新增参与者或回填 EOT：留下通知，前端轮询后提示
                    if res.get('created') or res.get('eot_updated'):
                        database.save_xlsx_watch_config(cfg['project_id'], {
                            'auto_notice': json.dumps({
                                'at': res['scanned_at'],
                                'created': res['created'],
                                'screenings': res['created_screenings'],
                                'patient_ids': res['created_patient_ids'],
                                'eot_updated': res.get('eot_updated', 0),
                                'eot_screenings': res.get('eot_screenings', []),
                            }, ensure_ascii=False)
                        })
                except Exception as exc:
                    _log(f'自动同步失败: {exc}')
                    if attempts < 2:
                        with self._lock:
                            self._pending[path] = (time.time() + 5, attempts + 1)


watch_service = EnrollmentWatchService()


def start_watch_service():
    watch_service.start()


def reload_watch_service():
    watch_service.reload()
