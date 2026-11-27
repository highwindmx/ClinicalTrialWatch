"""
临床研究数据看板 - Flask 主应用
启动方式: python app.py
访问地址: http://localhost:5003
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import database
import enrollment_sync
import ocr_link
import os
import sys
import json
import traceback
from datetime import datetime, timedelta
import calendar

# 冻结态路径：只读资源(frontend/ico)解压到 sys._MEIPASS，可写数据(data)在 exe 旁；
# 开发态两者都用脚本目录，行为与原相对路径一致。
if getattr(sys, "frozen", False):
    _RES_ROOT = sys._MEIPASS
    _DATA_ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _RES_ROOT = _HERE
    _DATA_ROOT = _HERE

FRONTEND_DIR = os.path.join(_RES_ROOT, "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
# 安全：仅允许同源（本地前端）跨域，避免任意站点读取临床数据。
# 被 baseMan 托管时端口由 BASEMAN_PORT 下发，白名单跟着端口走；独立运行仍是 5003。
APP_PORT = int(os.environ.get("BASEMAN_PORT") or 5003)
CORS(app, origins=[f'http://127.0.0.1:{APP_PORT}', f'http://localhost:{APP_PORT}'])

# 请求结束关闭连接池复用的连接（见 database.get_db 的连接缓存）
app.teardown_appcontext(database.close_request_connection)

# ==================== 统一错误处理 ====================

def api_error_handler(func):
    """API统一错误处理装饰器：捕获异常，返回标准错误响应"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            return jsonify({'error': f'参数错误: {str(e)}'}), 400
        except KeyError as e:
            return jsonify({'error': f'缺少必要字段: {str(e)}'}), 400
        except database.sqlite3.IntegrityError as e:
            err_msg = str(e)
            app.logger.error(f"数据完整性错误 in {func.__name__}: {err_msg}\n{traceback.format_exc()}")
            if 'UNIQUE' in err_msg:
                if 'project.code' in err_msg:
                    return jsonify({'error': '项目代码已存在，请使用其他代码'}), 400
                return jsonify({'error': '数据冲突：该记录已存在'}), 400
            return jsonify({'error': f'数据完整性错误: {err_msg}'}), 400
        except database.sqlite3.Error as e:
            app.logger.error(f"数据库错误 in {func.__name__}: {str(e)}\n{traceback.format_exc()}")
            return jsonify({'error': '数据库操作失败，请联系管理员'}), 500
        except Exception as e:
            app.logger.error(f"未预期错误 in {func.__name__}: {str(e)}\n{traceback.format_exc()}")
            return jsonify({'error': '服务器内部错误'}), 500
    wrapper.__name__ = func.__name__
    return wrapper

# 初始化数据库
database.init_db()

# ==================== 全局错误处理器 ====================

@app.errorhandler(404)
def handle_404(e):
    return jsonify({'error': '资源不存在'}), 404

@app.errorhandler(405)
def handle_405(e):
    return jsonify({'error': '方法不允许'}), 405

@app.errorhandler(500)
def handle_500(e):
    app.logger.error(f"服务器错误: {str(e)}\n{traceback.format_exc()}")
    return jsonify({'error': '服务器内部错误'}), 500

# ==================== 前端页面路由 ====================

# 说明：Flask 已通过 static_folder='frontend', static_url_path='' 把 /js/*、/css/* 等
# 静态资源直接托管（其内置 static 路由即 /<path:filename>，且静态字面路径如 /api/* 始终
# 优先于动态通配，故不会遮蔽接口）。因此无需再写通配路由；此处仅保留 '/' 与 '/charts'
# 两个显式入口，用于返回 index.html / charts.html。已删除旧版 '/<path:filename>' 通配。

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/charts')
def charts_page():
    return send_from_directory(FRONTEND_DIR, 'charts.html')

# ==================== 项目 API ====================

@app.route('/api/projects', methods=['GET'])
def api_get_projects():
    projects = database.get_projects()
    return jsonify(projects)

@api_error_handler
@app.route('/api/projects', methods=['POST'])
def api_create_project():
    data = request.get_json()
    new_id = database.create_project(data)
    return jsonify({'id': new_id}), 201

@api_error_handler
@app.route('/api/projects/<int:pid>', methods=['GET'])
def api_get_project(pid):
    proj = database.get_project(pid)
    if not proj:
        return jsonify({'error': '项目不存在'}), 404
    return jsonify(proj)

@api_error_handler
@app.route('/api/projects/<int:pid>', methods=['PUT'])
def api_update_project(pid):
    data = request.get_json()
    database.update_project(pid, data)
    return jsonify({'ok': True})

@api_error_handler
@app.route('/api/projects/<int:pid>', methods=['DELETE'])
def api_delete_project(pid):
    database.delete_project(pid)
    return jsonify({'ok': True})

@api_error_handler
@app.route('/api/projects/<int:pid>/demo-data', methods=['POST'])
def api_demo_data(pid):
    result = database.generate_demo_data(pid)
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result), 201

# ==================== 入组表自动同步 API ====================

@api_error_handler
@app.route('/api/projects/<int:pid>/enrollment-sync', methods=['GET'])
def api_get_enrollment_sync(pid):
    """读取项目的入组表同步配置，并附带当前文件的表头识别预览。"""
    cfg = database.get_xlsx_watch_config(pid)
    cfg['last_result'] = json.loads(cfg['last_result']) if cfg.get('last_result') else None
    cfg['file_exists'] = bool(cfg.get('xlsx_path') and os.path.isfile(cfg['xlsx_path']))
    cfg['preview'] = None
    cfg['preview_error'] = None
    if cfg['file_exists']:
        try:
            rows, meta = enrollment_sync.read_enrollment_rows(
                cfg['xlsx_path'], cfg.get('sheet_name') or enrollment_sync.DEFAULT_SHEET)
            cfg['preview'] = {
                'row_count': len(rows),
                'columns': meta['columns'],
                'headers': meta['headers'],
                'sample': rows[:3],
            }
        except Exception as e:
            cfg['preview_error'] = str(e)
    return jsonify(cfg)


@api_error_handler
@app.route('/api/projects/<int:pid>/enrollment-sync', methods=['PUT'])
def api_save_enrollment_sync(pid):
    """保存同步配置；保存后立即重建 watchdog 监听目标。"""
    data = request.get_json() or {}
    allowed = ('xlsx_path', 'sheet_name', 'enabled')
    payload = {k: data[k] for k in allowed if k in data}
    cfg = database.save_xlsx_watch_config(pid, payload)
    enrollment_sync.reload_watch_service()
    return jsonify({'ok': True, 'config': cfg})


@api_error_handler
@app.route('/api/projects/<int:pid>/enrollment-sync/scan', methods=['POST'])
def api_scan_enrollment(pid):
    """手动扫描：强制按当前文件内容增量写入；dry_run=true 时只解析不写库。"""
    data = request.get_json() or {}
    result = enrollment_sync.sync_enrollment(
        pid,
        path=data.get('path') or None,
        sheet_name=data.get('sheet_name') or None,
        force=True,
        dry_run=bool(data.get('dry_run')),
    )
    if not result.get('success'):
        return jsonify(result), 400
    return jsonify(result)


@app.route('/api/projects/<int:pid>/enrollment-sync/notice', methods=['GET'])
def api_get_enrollment_notice(pid):
    """读取并清除 watchdog 自动同步通知（读后即焚，避免重复提示）。"""
    cfg = database.get_xlsx_watch_config(pid)
    raw = cfg.get('auto_notice')
    if raw:
        database.save_xlsx_watch_config(pid, {'auto_notice': None})
    try:
        notice = json.loads(raw) if raw else None
    except Exception:
        notice = None
    return jsonify({'notice': notice})


@app.route('/api/projects/<int:pid>/ocr-visits', methods=['GET'])
@api_error_handler
def api_get_ocr_visits(pid):
    """只读扫描 minerUOCR 资料目录，返回按筛选号匹配的访视标记（不调用 minerUOCR 服务）。"""
    project = database.get_project(pid)
    root = (project or {}).get('ocr_dir') or ''
    if not root or not os.path.isdir(root):
        return jsonify({'configured': False, 'root': root, 'mapped': {},
                        'unmatched': [], 'total_dirs': 0, 'dated_dirs': 0})
    patients = database.get_patients(pid)
    ids = [p.get('patient_id') for p in patients if p.get('patient_id')]
    mapped, unmatched, total, dated = ocr_link.scan(root, ids)
    return jsonify({'configured': True, 'root': root, 'mapped': mapped,
                    'unmatched': unmatched, 'total_dirs': total, 'dated_dirs': dated})

# ==================== 患者 API ====================

@api_error_handler
@app.route('/api/patients', methods=['GET'])
def api_get_patients():
    project_id = request.args.get('project_id', type=int)
    patients = database.get_patients(project_id)
    return jsonify(patients)

@api_error_handler
@app.route('/api/patients/<int:pid>', methods=['GET'])
def api_get_patient(pid):
    patient = database.get_patient(pid)
    if not patient:
        return jsonify({'error': '患者不存在'}), 404
    return jsonify(patient)

@api_error_handler
@app.route('/api/patients', methods=['POST'])
def api_create_patient():
    data = request.get_json()
    new_id = database.create_patient(data)
    return jsonify({'id': new_id}), 201

@api_error_handler
@app.route('/api/patients/<int:pid>', methods=['PUT'])
def api_update_patient(pid):
    data = request.get_json()
    database.update_patient(pid, data)
    return jsonify({'ok': True})

@api_error_handler
@app.route('/api/patients/<int:pid>', methods=['DELETE'])
def api_delete_patient(pid):
    database.delete_patient(pid)
    return jsonify({'ok': True})

# ==================== 用药 API ====================

@api_error_handler
@app.route('/api/patients/<int:pid>/medications', methods=['GET'])
def api_get_medications(pid):
    meds = database.get_medications(pid)
    return jsonify(meds)

@api_error_handler
@app.route('/api/patients/<int:pid>/medications', methods=['POST'])
def api_create_medication(pid):
    data = request.get_json()
    data['patient_id'] = pid
    new_id = database.create_medication(data)
    return jsonify({'id': new_id}), 201

@api_error_handler
@app.route('/api/medications/<int:mid>', methods=['PUT'])
def api_update_medication(mid):
    data = request.get_json()
    database.update_medication(mid, data)
    return jsonify({'ok': True})

@api_error_handler
@app.route('/api/medications/<int:mid>', methods=['DELETE'])
def api_delete_medication(mid):
    database.delete_medication(mid)
    return jsonify({'ok': True})

# ==================== 肿瘤评估 API ====================

@api_error_handler
@app.route('/api/patients/<int:pid>/tumor-assessments', methods=['GET'])
def api_get_tumor_assessments(pid):
    rows = database.get_tumor_assessments(pid)
    return jsonify(rows)

@api_error_handler
@app.route('/api/patients/<int:pid>/tumor-assessments', methods=['POST'])
def api_create_tumor_assessment(pid):
    data = request.get_json()
    data['patient_id'] = pid
    new_id = database.create_tumor_assessment(data)
    return jsonify({'id': new_id}), 201

@api_error_handler
@app.route('/api/tumor-assessments/<int:tid>', methods=['PUT'])
def api_update_tumor_assessment(tid):
    data = request.get_json()
    database.update_tumor_assessment(tid, data)
    return jsonify({'ok': True})

@api_error_handler
@app.route('/api/tumor-assessments/<int:tid>', methods=['DELETE'])
def api_delete_tumor_assessment(tid):
    database.delete_tumor_assessment(tid)
    return jsonify({'ok': True})

# ==================== 不良事件 API ====================

@api_error_handler
@app.route('/api/patients/<int:pid>/adverse-events', methods=['GET'])
def api_get_adverse_events(pid):
    rows = database.get_adverse_events(pid)
    return jsonify(rows)

@api_error_handler
@app.route('/api/projects/<int:pid>/adverse-events', methods=['GET'])
def api_get_project_adverse_events(pid):
    """项目级 AE 汇总：返回该项目下全部不良事件（含患者编号）"""
    rows = database.get_project_adverse_events(pid)
    return jsonify(rows)

@api_error_handler
@app.route('/api/patients/<int:pid>/adverse-events', methods=['POST'])
def api_create_adverse_event(pid):
    data = request.get_json()
    data['patient_id'] = pid
    new_id = database.create_adverse_event(data)
    return jsonify({'id': new_id}), 201

@api_error_handler
@app.route('/api/adverse-events/<int:aid>', methods=['PUT'])
def api_update_adverse_event(aid):
    data = request.get_json()
    database.update_adverse_event(aid, data)
    return jsonify({'ok': True})

@api_error_handler
@app.route('/api/adverse-events/<int:aid>', methods=['DELETE'])
def api_delete_adverse_event(aid):
    database.delete_adverse_event(aid)
    return jsonify({'ok': True})

# ==================== PK数据 API ====================

@api_error_handler
@app.route('/api/patients/<int:pid>/pk-data', methods=['GET'])
def api_get_pk_data(pid):
    rows = database.get_pk_data(pid)
    return jsonify(rows)

@api_error_handler
@app.route('/api/patients/<int:pid>/pk-data', methods=['POST'])
def api_create_pk_data(pid):
    data = request.get_json()
    data['patient_id'] = pid
    new_id = database.create_pk_data(data)
    return jsonify({'id': new_id}), 201

@api_error_handler
@app.route('/api/pk-data/<int:pkid>', methods=['PUT'])
def api_update_pk_data(pkid):
    data = request.get_json()
    database.update_pk_data(pkid, data)
    return jsonify({'ok': True})

@api_error_handler
@app.route('/api/pk-data/<int:pkid>', methods=['DELETE'])
def api_delete_pk_data(pkid):
    database.delete_pk_data(pkid)
    return jsonify({'ok': True})

# ==================== 肿瘤指标 API ====================

@api_error_handler
@app.route('/api/patients/<int:pid>/tumor-markers', methods=['GET'])
def api_get_tumor_markers(pid):
    rows = database.get_tumor_markers(pid)
    return jsonify(rows)

@api_error_handler
@app.route('/api/patients/<int:pid>/tumor-markers', methods=['POST'])
def api_create_tumor_marker(pid):
    data = request.get_json()
    data['patient_id'] = pid
    new_id = database.create_tumor_marker(data)
    return jsonify({'id': new_id}), 201

@api_error_handler
@app.route('/api/tumor-markers/<int:tmid>', methods=['PUT'])
def api_update_tumor_marker(tmid):
    data = request.get_json()
    database.update_tumor_marker(tmid, data)
    return jsonify({'ok': True})

@api_error_handler
@app.route('/api/tumor-markers/<int:tmid>', methods=['DELETE'])
def api_delete_tumor_marker(tmid):
    database.delete_tumor_marker(tmid)
    return jsonify({'ok': True})

# ==================== 自定义列 API ====================

@api_error_handler
@app.route('/api/projects/<int:proj_id>/custom-columns', methods=['GET'])
def api_get_custom_columns(proj_id):
    module = request.args.get('module')
    rows = database.get_custom_columns(proj_id, module)
    return jsonify(rows)

@api_error_handler
@app.route('/api/projects/<int:proj_id>/custom-columns', methods=['POST'])
def api_create_custom_column(proj_id):
    data = request.get_json()
    data['project_id'] = proj_id
    new_id = database.create_custom_column(data)
    return jsonify({'id': new_id}), 201

@api_error_handler
@app.route('/api/custom-columns/<int:ccid>', methods=['DELETE'])
def api_delete_custom_column(ccid):
    database.delete_custom_column(ccid)
    return jsonify({'ok': True})

# ==================== 甘特图 API ====================

@api_error_handler
@app.route('/api/gantt-full', methods=['GET'])
def api_get_gantt_full():
    """获取完整时间轴甘特图数据：从最早事件到最晚事件，前后各30天缓冲"""
    project_id = request.args.get('project_id', type=int)
    if not project_id:
        return jsonify({'error': '缺少 project_id'}), 400

    # 获取该项目所有事件的时间范围（性能优化：用 SQL MIN/MAX 聚合直接算出最早/最晚日期，
    # 不再在 Python 里全量拉取所有事件再扫一遍）
    patients = database.get_patients(project_id)
    earliest_str, latest_str = database.get_gantt_date_range(project_id)

    if not earliest_str:
        # 没有任何事件，默认显示当前季度
        ref_date = datetime.now()
        q = (ref_date.month - 1) // 3
        start_date = datetime(ref_date.year, q * 3 + 1, 1)
        if q < 3:
            next_q_start = datetime(ref_date.year, (q + 1) * 3 + 1, 1)
        else:
            next_q_start = datetime(ref_date.year + 1, 1, 1)
        end_date = next_q_start - timedelta(days=1)
    else:
        earliest = datetime.strptime(earliest_str, '%Y-%m-%d')
        latest = datetime.strptime(latest_str, '%Y-%m-%d')
        today = datetime.now()
        # 确保时间轴包含今日，且今日大致居中
        # 起始：最早事件-30天 或 今日前90天（取更早的）
        # 结束：最晚事件+30天 或 今日后90天（取更晚的）
        start_date = min(earliest - timedelta(days=30), today - timedelta(days=90))
        end_date = max(latest + timedelta(days=30), today + timedelta(days=90))

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    days = (end_date - start_date).days + 1

    # 重新获取范围内的完整事件
    events = database.get_events_for_gantt_range(project_id, start_str, end_str)

    # 生成日期标签和星期
    labels = []
    weekdays = []
    weekday_names = ['一', '二', '三', '四', '五', '六', '日']
    for i in range(days):
        d = start_date + timedelta(days=i)
        labels.append(str(d.day))
        weekdays.append(weekday_names[d.weekday()])

    # 生成月份合并标签
    month_labels = []
    current_month = None
    span = 0
    for i in range(days):
        d = start_date + timedelta(days=i)
        m = d.strftime('%Y年%m月')
        if m != current_month:
            if current_month is not None:
                month_labels.append({'label': current_month, 'span': span})
            current_month = m
            span = 1
        else:
            span += 1
    if current_month is not None:
        month_labels.append({'label': current_month, 'span': span})

    # 获取剂量组颜色与排序映射
    dose_colors = {}
    dose_group_order = {}
    try:
        dose_groups = database.get_dose_groups(project_id)
        dose_colors = {dg['name']: dg.get('color', '#378ADD') for dg in dose_groups}
        dose_group_order = {dg['name']: dg.get('sort_order', 0) for dg in dose_groups}
        dose_group_interval = {dg['name']: (dg.get('medication_interval') or 21) for dg in dose_groups}
    except Exception as e:
        app.logger.warning(f"获取剂量组失败: {e}")
        # 失败后继续使用空映射，不阻断主流程

    # 获取 DLT 观察期天数及周期间隔
    dlt_days = 21
    med_interval = 21
    assess_interval = 42
    assess_calc_base = 'baseline'
    try:
        proj_info = database.get_project(project_id)
        if proj_info:
            if proj_info.get('dlt_days') is not None:
                dlt_days = int(proj_info['dlt_days'])
            if proj_info.get('medication_interval') is not None:
                med_interval = int(proj_info['medication_interval'])
            if proj_info.get('assessment_interval') is not None:
                assess_interval = int(proj_info['assessment_interval'])
            if proj_info.get('assessment_calc_base'):
                assess_calc_base = proj_info['assessment_calc_base']
    except Exception as e:
        app.logger.warning(f"获取项目信息失败: {e}")

    return jsonify({
        'patients': patients,
        'events': events,
        'date_range': {
            'start': start_str,
            'end': end_str,
            'days': days,
            'labels': labels,
            'weekdays': weekdays,
            'month_labels': month_labels
        },
        'dose_colors': dose_colors,
        'dose_group_order': dose_group_order,
        'dose_group_interval': dose_group_interval,
        'dlt_days': dlt_days,
        'medication_interval': med_interval,
        'assessment_interval': assess_interval,
        'assessment_calc_base': assess_calc_base
    })

# ==================== 剂量组 API ====================

@api_error_handler
@app.route('/api/projects/<int:proj_id>/dose-groups', methods=['GET'])
def api_get_dose_groups(proj_id):
    groups = database.get_dose_groups(proj_id)
    return jsonify(groups)

@api_error_handler
@app.route('/api/projects/<int:proj_id>/dose-groups', methods=['POST'])
def api_create_dose_group(proj_id):
    data = request.get_json()
    data['project_id'] = proj_id
    new_id = database.create_dose_group(data)
    return jsonify({'id': new_id}), 201

@api_error_handler
@app.route('/api/dose-groups/<int:dgid>', methods=['PUT'])
def api_update_dose_group(dgid):
    data = request.get_json()
    database.update_dose_group(dgid, data)
    return jsonify({'ok': True})

@api_error_handler
@app.route('/api/dose-groups/<int:dgid>', methods=['DELETE'])
def api_delete_dose_group(dgid):
    database.delete_dose_group(dgid)
    return jsonify({'ok': True})

# ==================== 癌肿类型 API ====================

@api_error_handler
@app.route('/api/projects/<int:proj_id>/cancer-types', methods=['GET'])
def api_get_cancer_types(proj_id):
    types = database.get_cancer_types(proj_id)
    return jsonify(types)

@api_error_handler
@app.route('/api/projects/<int:proj_id>/cancer-types', methods=['POST'])
def api_create_cancer_type(proj_id):
    data = request.get_json()
    data['project_id'] = proj_id
    new_id = database.create_cancer_type(data)
    return jsonify({'id': new_id}), 201

@api_error_handler
@app.route('/api/cancer-types/<int:ctid>', methods=['PUT'])
def api_update_cancer_type(ctid):
    data = request.get_json()
    database.update_cancer_type(ctid, data)
    return jsonify({'ok': True})

@api_error_handler
@app.route('/api/cancer-types/<int:ctid>', methods=['DELETE'])
def api_delete_cancer_type(ctid):
    database.delete_cancer_type(ctid)
    return jsonify({'ok': True})

# ==================== Excel 导入导出 API ====================

@api_error_handler
@app.route('/api/export/<int:project_id>', methods=['GET'])
def api_export_excel(project_id):
    """导出项目数据为 Excel"""
    try:
        from openpyxl import Workbook
    except ImportError:
        return jsonify({'error': '需要安装 openpyxl: pip install openpyxl'}), 500

    proj = database.get_project(project_id)
    if not proj:
        return jsonify({'error': '项目不存在'}), 404

    patients = database.get_patients(project_id)
    wb = Workbook()

    # 基线数据 sheet（与编辑界面字段一致：患者编号/年龄/性别/癌肿/ECOG/剂量组/入组日期/DLT观察/状态）
    ws_base = wb.active
    ws_base.title = "基线数据"
    ws_base.append(["患者编号", "年龄", "性别", "癌肿", "ECOG评分", "剂量组", "入组日期", "DLT观察", "状态"])
    for p in patients:
        dlt_obs = p.get('dlt_observation', 1)
        if dlt_obs is None: dlt_obs = 1
        ws_base.append([p.get('patient_id'), p.get('age'), p.get('sex'),
                        p.get('cancer_type'), p.get('ecog_score'), p.get('dose_group'),
                        p.get('enroll_date'), int(dlt_obs), p.get('status')])

    # 用药数据 sheet（与编辑界面字段一致：患者编号/药物/计划日期/实际日期/剂量/周期/给药途径/备注）
    # 性能优化：按项目一次性批量取出并按患者分组，避免逐患者查库（N+1）
    meds_by_patient = database.get_medications_by_project(project_id)
    ws_med = wb.create_sheet("用药数据")
    ws_med.append(["患者编号", "药物名称", "计划日期", "实际日期", "剂量", "剂量单位", "周期", "给药途径", "备注"])
    for p in patients:
        for m in meds_by_patient.get(p['id'], []):
            ws_med.append([p['patient_id'], m.get('drug_name'), m.get('planned_date'),
                          m.get('actual_date'), m.get('dose'), m.get('dose_unit'),
                          m.get('cycle'), m.get('route'), m.get('notes')])

    # 肿瘤评估 sheet（与编辑界面字段一致：患者编号/日期/时间点/靶病灶SOD/SOD变化/最佳疗评/确认CRPR/新发病灶/备注）
    ta_by_patient = database.get_tumor_assessments_by_project(project_id)
    ws_ta = wb.create_sheet("肿瘤评估")
    ws_ta.append(["患者编号", "评估日期", "时间点", "靶病灶SOD(mm)", "SOD变化(%)", "最佳疗评", "确认CR/PR", "新发病灶", "备注"])
    for p in patients:
        for t in ta_by_patient.get(p['id'], []):
            ws_ta.append([p['patient_id'], t.get('eval_date'), t.get('eval_type'),
                         t.get('target_sod'), t.get('sod_change'), t.get('best_response'),
                         t.get('confirmed_crpr'), t.get('new_lesions'), t.get('notes')])

    # AE sheet（与编辑界面字段一致：患者编号/AE名称/发生日期/结束日期/等级/转归/与药物关系/严重AE/采取措施/备注）
    ae_by_patient = database.get_adverse_events_by_project(project_id)
    ws_ae = wb.create_sheet("不良事件")
    ws_ae.append(["患者编号", "AE名称", "发生日期", "结束日期", "等级", "转归", "与药物关系", "严重AE", "采取措施", "备注"])
    for p in patients:
        for a in ae_by_patient.get(p['id'], []):
            ws_ae.append([p['patient_id'], a.get('ae_term'), a.get('onset_date'), a.get('end_date'),
                         a.get('grade'), a.get('outcome'), a.get('drug_relation'),
                         a.get('serious'), a.get('action_taken'), a.get('notes')])

    # PK数据 sheet
    pk_by_patient = database.get_pk_data_by_project(project_id)
    ws_pk = wb.create_sheet("PK数据")
    ws_pk.append(["患者编号", "采样日期", "采样时间", "时间点", "浓度", "单位", "周期", "备注"])
    for p in patients:
        for k in pk_by_patient.get(p['id'], []):
            ws_pk.append([p['patient_id'], k.get('sample_date'), k.get('sample_time'),
                         k.get('time_point'), k.get('concentration'), k.get('unit'),
                         k.get('cycle'), k.get('notes')])

    # 肿瘤指标 sheet
    tm_by_patient = database.get_tumor_markers_by_project(project_id)
    ws_tm = wb.create_sheet("肿瘤指标")
    ws_tm.append(["患者编号", "检测日期", "指标名称", "值", "单位", "正常上限", "备注"])
    for p in patients:
        for t in tm_by_patient.get(p['id'], []):
            ws_tm.append([p['patient_id'], t.get('test_date'), t.get('marker_name'),
                         t.get('value'), t.get('unit'), t.get('upper_limit'), t.get('notes')])

    # 导出前清理超过1天的旧文件，防止累积
    export_dir = os.path.join(_DATA_ROOT, 'data', 'exports')
    os.makedirs(export_dir, exist_ok=True)
    now = datetime.now().timestamp()
    for fname in os.listdir(export_dir):
        fpath = os.path.join(export_dir, fname)
        if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 86400:
            try:
                os.remove(fpath)
            except Exception:
                pass
    filename = f"{proj.get('code', 'export')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join(export_dir, filename)
    wb.save(filepath)

    return send_from_directory(export_dir, filename, as_attachment=True)

@api_error_handler
@app.route('/api/import/<int:project_id>', methods=['POST'])
def api_import_excel(project_id):
    """从 Excel 导入数据"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return jsonify({'error': '需要安装 openpyxl: pip install openpyxl'}), 500

    if 'file' not in request.files:
        return jsonify({'error': '未上传文件'}), 400

    file = request.files['file']
    wb = load_workbook(file)
    imported = {'patients': 0, 'medications': 0, 'assessments': 0, 'aes': 0, 'pk': 0, 'markers': 0}
    errors = []

    # 清空该项目下的患者及关联数据（保留项目配置：癌肿类型、剂量组、自定义列）
    database.clear_project_data(project_id)

    # 导入基线数据（新格式：患者编号/年龄/性别/癌肿/ECOG/剂量组/入组日期/DLT观察/状态）
    # 预加载该项目的癌肿类型和剂量组配置（用于文本→ID匹配）
    cancer_type_map = {ct['name']: ct['id'] for ct in database.get_cancer_types(project_id)}
    dose_group_map = {dg['name']: dg['id'] for dg in database.get_dose_groups(project_id)}

    # 患者编号 -> db_id 映射（导入基线数据时逐步填充，供后续sheet使用）
    pid_map = {}

    if '基线数据' in wb.sheetnames:
        ws = wb['基线数据']
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0]:
                continue
            # 兼容多种旧格式
            row_list = list(row)
            # 检测是否为旧格式（含姓名列）：第2列是字符串且非数字
            if len(row_list) >= 9 and isinstance(row_list[1], str) and not str(row_list[1]).strip().isdigit() and row_list[1] not in (None, ''):
                # 旧格式（含姓名）：患者编号/姓名/年龄/性别/癌肿/ECOG/剂量组/入组日期/状态
                ct_text = str(row_list[4]) if row_list[4] else ''
                dg_text = str(row_list[6]) if row_list[6] else ''
                data = {
                    'project_id': project_id,
                    'patient_id': str(row_list[0]),
                    'age': row_list[2],
                    'sex': row_list[3],
                    'cancer_type': ct_text,
                    'cancer_type_id': cancer_type_map.get(ct_text),
                    'ecog_score': row_list[5],
                    'dose_group': dg_text,
                    'dose_group_id': dose_group_map.get(dg_text),
                    'enroll_date': str(row_list[7]) if row_list[7] else None,
                    'status': row_list[8] or 'treatment'
                }
            elif len(row_list) >= 9 and str(row_list[7]).strip().isdigit() and int(row_list[7]) in (0, 1):
                # 新格式（含DLT观察）：患者编号/年龄/性别/癌肿/ECOG/剂量组/入组日期/DLT观察/状态
                ct_text = str(row_list[3]) if row_list[3] else ''
                dg_text = str(row_list[5]) if row_list[5] else ''
                data = {
                    'project_id': project_id,
                    'patient_id': str(row_list[0]),
                    'age': row_list[1],
                    'sex': row_list[2],
                    'cancer_type': ct_text,
                    'cancer_type_id': cancer_type_map.get(ct_text),
                    'ecog_score': row_list[4],
                    'dose_group': dg_text,
                    'dose_group_id': dose_group_map.get(dg_text),
                    'enroll_date': str(row_list[6]) if row_list[6] else None,
                    'dlt_observation': int(row_list[7]) if row_list[7] is not None else 1,
                    'status': row_list[8] or 'treatment'
                }
            else:
                # 中间格式（无姓名无DLT）：患者编号/年龄/性别/癌肿/ECOG/剂量组/入组日期/状态
                ct_text = str(row_list[3]) if row_list[3] else ''
                dg_text = str(row_list[5]) if row_list[5] else ''
                data = {
                    'project_id': project_id,
                    'patient_id': str(row_list[0]),
                    'age': row_list[1],
                    'sex': row_list[2],
                    'cancer_type': ct_text,
                    'cancer_type_id': cancer_type_map.get(ct_text),
                    'ecog_score': row_list[4],
                    'dose_group': dg_text,
                    'dose_group_id': dose_group_map.get(dg_text),
                    'enroll_date': str(row_list[6]) if row_list[6] else None,
                    'status': row_list[7] or 'screening'
                }
            pid_text = str(row_list[0])
            try:
                db_id = database.create_patient(data)
                pid_map[pid_text] = db_id
                imported['patients'] += 1
            except Exception as e:
                errors.append(f"基线数据第{row_idx}行(患者{pid_text}): {str(e)}")

    # 导入用药数据（患者编号/药物名称/计划日期/实际日期/剂量/剂量单位/周期/给药途径/备注）
    if '用药数据' in wb.sheetnames:
        ws = wb['用药数据']
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0]:
                continue
            pid_text = str(row[0])
            if pid_text not in pid_map:
                errors.append(f"用药数据第{row_idx}行: 患者编号'{pid_text}'不存在")
                continue
            data = {
                'patient_id': pid_map[pid_text],
                'drug_name': row[1],
                'planned_date': str(row[2]) if row[2] else None,
                'actual_date': str(row[3]) if row[3] else None,
                'dose': row[4],
                'dose_unit': row[5],
                'cycle': row[6],
                'route': row[7] if len(row) > 7 else None,
                'notes': row[8] if len(row) > 8 else None
            }
            try:
                database.create_medication(data)
                imported['medications'] += 1
            except Exception as e:
                errors.append(f"用药数据第{row_idx}行: {str(e)}")

    # 导入肿瘤评估（患者编号/评估日期/时间点/靶病灶SOD/SOD变化/最佳疗评/确认CR-PR/新发病灶/备注）
    if '肿瘤评估' in wb.sheetnames:
        ws = wb['肿瘤评估']
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0]:
                continue
            pid_text = str(row[0])
            if pid_text not in pid_map:
                errors.append(f"肿瘤评估第{row_idx}行: 患者编号'{pid_text}'不存在")
                continue
            data = {
                'patient_id': pid_map[pid_text],
                'eval_date': str(row[1]) if row[1] else None,
                'eval_type': str(row[2]) if row[2] else None,
                'target_sod': row[3],
                'sod_change': row[4],
                'best_response': str(row[5]) if row[5] else None,
                'confirmed_crpr': int(row[6]) if row[6] is not None else 0,
                'new_lesions': int(row[7]) if row[7] is not None else 0,
                'notes': row[8] if len(row) > 8 else None
            }
            try:
                database.create_tumor_assessment(data)
                imported['assessments'] += 1
            except Exception as e:
                errors.append(f"肿瘤评估第{row_idx}行: {str(e)}")

    # 导入不良事件（患者编号/AE名称/发生日期/结束日期/等级/转归/与药物关系/严重AE/采取措施/备注）
    if '不良事件' in wb.sheetnames:
        ws = wb['不良事件']
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0]:
                continue
            pid_text = str(row[0])
            if pid_text not in pid_map:
                errors.append(f"不良事件第{row_idx}行: 患者编号'{pid_text}'不存在")
                continue
            data = {
                'patient_id': pid_map[pid_text],
                'ae_term': str(row[1]) if row[1] else None,
                'onset_date': str(row[2]) if row[2] else None,
                'end_date': str(row[3]) if row[3] else None,
                'grade': row[4],
                'outcome': str(row[5]) if row[5] else None,
                'drug_relation': str(row[6]) if row[6] else None,
                'serious': int(row[7]) if row[7] is not None else 0,
                'action_taken': str(row[8]) if len(row) > 8 and row[8] else None,
                'notes': row[9] if len(row) > 9 else None
            }
            try:
                database.create_adverse_event(data)
                imported['aes'] += 1
            except Exception as e:
                errors.append(f"不良事件第{row_idx}行: {str(e)}")

    # 导入PK数据（患者编号/采样日期/采样时间/时间点/浓度/单位/周期/备注）
    if 'PK数据' in wb.sheetnames:
        ws = wb['PK数据']
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0]:
                continue
            pid_text = str(row[0])
            if pid_text not in pid_map:
                errors.append(f"PK数据第{row_idx}行: 患者编号'{pid_text}'不存在")
                continue
            data = {
                'patient_id': pid_map[pid_text],
                'sample_date': str(row[1]) if row[1] else None,
                'sample_time': str(row[2]) if row[2] else None,
                'time_point': str(row[3]) if row[3] else None,
                'concentration': row[4],
                'unit': str(row[5]) if row[5] else 'ng/mL',
                'cycle': str(row[6]) if row[6] else None,
                'notes': row[7] if len(row) > 7 else None
            }
            try:
                database.create_pk_data(data)
                imported['pk'] += 1
            except Exception as e:
                errors.append(f"PK数据第{row_idx}行: {str(e)}")

    # 导入肿瘤指标（患者编号/检测日期/指标名称/值/单位/正常上限/备注）
    if '肿瘤指标' in wb.sheetnames:
        ws = wb['肿瘤指标']
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0]:
                continue
            pid_text = str(row[0])
            if pid_text not in pid_map:
                errors.append(f"肿瘤指标第{row_idx}行: 患者编号'{pid_text}'不存在")
                continue
            data = {
                'patient_id': pid_map[pid_text],
                'test_date': str(row[1]) if row[1] else None,
                'marker_name': str(row[2]) if row[2] else None,
                'value': row[3],
                'unit': str(row[4]) if row[4] else None,
                'upper_limit': row[5],
                'notes': row[6] if len(row) > 6 else None
            }
            try:
                database.create_tumor_marker(data)
                imported['markers'] += 1
            except Exception as e:
                errors.append(f"肿瘤指标第{row_idx}行: {str(e)}")

    return jsonify({'imported': imported, 'errors': errors})

# ==================== 图表数据 API ====================

@api_error_handler
@app.route('/api/charts/baseline/<int:project_id>', methods=['GET'])
def api_chart_baseline(project_id):
    """基线统计表数据"""
    patients = database.get_patients(project_id)
    return jsonify(patients)

@api_error_handler
@app.route('/api/charts/waterfall/<int:project_id>', methods=['GET'])
def api_chart_waterfall(project_id):
    """瀑布图数据：每个患者的SOD变化 + 患者状态 + 确认CR/PR
    SOD变化自动计算：(本次靶病灶SOD - 基线SOD) / 基线SOD * 100
    """
    patients = database.get_patients(project_id)
    ta_by_patient = database.get_tumor_assessments_by_project(project_id)
    result = []
    for p in patients:
        assessments = ta_by_patient.get(p['id'], [])
        if assessments:
            # 按日期排序，第一个为基线
            sorted_assess = sorted(assessments, key=lambda a: a.get('eval_date', ''))
            baseline_sod = float(sorted_assess[0].get('target_sod') or 0) if sorted_assess else 0

            # 最佳SOD变化（最负=最好），跳过基线
            best_change = None
            for a in sorted_assess[1:]:
                change = a.get('sod_change')
                if change is None or change == 0:
                    # 数据库无 sod_change，用 target_sod 计算
                    if baseline_sod > 0:
                        cur_sod = float(a.get('target_sod') or 0)
                        if cur_sod > 0:
                            change = (cur_sod - baseline_sod) / baseline_sod * 100
                if change is not None and change != 0:
                    if best_change is None or change < best_change:
                        best_change = change

            sod_change_result = best_change if best_change is not None else 0

            # 确认CR/PR：非基线评估中，有 confirmed_crpr=True 且 best_response 为 CR/PR
            baseline_assess = sorted_assess[0]
            confirmed_crpr = any(
                bool(a.get('confirmed_crpr')) and a.get('best_response') in ('CR', 'PR')
                for a in sorted_assess
                if a is not baseline_assess
            )
            # 最佳疗评（跳过基线，按 RECIST 优先级：CR>PR>SD>PD>NE）
            best_resp = ''
            resp_priority = {'CR': 0, 'PR': 1, 'SD': 2, 'PD': 3, 'NE': 4}
            best_prio = 99
            for a in sorted_assess[1:]:
                r = a.get('best_response', '')
                if r and resp_priority.get(r, 99) < best_prio:
                    best_prio = resp_priority[r]
                    best_resp = r

            # 患者状态
            patient_status = p.get('status', 'treatment')
            status_map = {
                'treatment': '在组治疗中',
                'followup': '结束治疗随访中',
                'off_study': '死亡/失访'
            }
            waterfall_status = status_map.get(patient_status, '在组治疗中')

            result.append({
                'patient_id': p['patient_id'],
                'sod_change': sod_change_result,
                'best_response': best_resp,
                'confirmed_crpr': confirmed_crpr,
                'patient_status': waterfall_status,
                'status_raw': patient_status,
                'dose_group': p.get('dose_group', ''),
                'cancer_type': p.get('cancer_type', '')
            })
    return jsonify(result)

@api_error_handler
@app.route('/api/charts/swimmer/<int:project_id>', methods=['GET'])
def api_chart_swimmer(project_id):
    """泳道图数据：患者治疗持续时间 + 各时点疗评结果 + 患者状态"""
    patients = database.get_patients(project_id)
    meds_by_patient = database.get_medications_by_project(project_id)
    ta_by_patient = database.get_tumor_assessments_by_project(project_id)
    ae_by_patient = database.get_adverse_events_by_project(project_id)
    result = []
    for p in patients:
        meds = meds_by_patient.get(p['id'], [])
        assessments = ta_by_patient.get(p['id'], [])
        aes = ae_by_patient.get(p['id'], [])

        # ============================================================
        # 泳道图坐标系统：所有条形和图示以入组日期为 0 天
        # ============================================================
        patient_status = p.get('status', 'treatment')
        today = datetime.now().strftime('%Y-%m-%d')
        enroll_date = p.get('enroll_date')
        death_lost_date = p.get('death_lost_date')

        # 获取用药日期
        drug_dates = []
        for m in meds:
            if m.get('actual_date'):
                drug_dates.append(m['actual_date'])

        end_treatment_date = p.get('end_treatment_date')
        if drug_dates:
            first_drug_date = min(drug_dates)
            last_drug_date = max(drug_dates)
            # 治疗用药天数：首次用药 → 治疗结束时间（非在组治疗时）或今天（在组治疗时）
            if patient_status == 'treatment':
                drug_end = today
            else:
                drug_end = end_treatment_date or last_drug_date or today
            days = (datetime.strptime(drug_end, '%Y-%m-%d') - datetime.strptime(first_drug_date, '%Y-%m-%d')).days
        else:
            first_drug_date = ''
            last_drug_date = ''
            days = 0

        # 入组相对参考日期（无入组日期时回退到首次用药）
        ref_date = enroll_date if enroll_date else (first_drug_date if first_drug_date else '')

        # 研究状态天数（从入组到终点事件/今天）
        if enroll_date:
            if patient_status == 'off_study':
                study_end_date = death_lost_date if death_lost_date else (last_drug_date if last_drug_date else today)
            else:
                study_end_date = today
            study_days = (datetime.strptime(study_end_date, '%Y-%m-%d') - datetime.strptime(enroll_date, '%Y-%m-%d')).days
        else:
            study_end_date = ''
            study_days = 0

        # 用药起始偏移（从入组到首次用药的天数）
        if enroll_date and first_drug_date:
            ds = datetime.strptime(first_drug_date, '%Y-%m-%d') - datetime.strptime(enroll_date, '%Y-%m-%d')
            drug_start_offset = ds.days
        else:
            drug_start_offset = 0

        # 各时点疗评结果（跳过基线，以入组日期为0天参考）
        assessment_points = []
        sorted_assessments = sorted(assessments, key=lambda a: a.get('eval_date', ''))
        for a in sorted_assessments:
            if a == sorted_assessments[0]:
                continue
            if a.get('eval_date') and a.get('best_response'):
                if ref_date and a['eval_date']:
                    try:
                        assess_days = (datetime.strptime(a['eval_date'], '%Y-%m-%d') - datetime.strptime(ref_date, '%Y-%m-%d')).days
                    except ValueError:
                        assess_days = 0
                else:
                    assess_days = 0
                assessment_points.append({
                    'days': assess_days,
                    'response': a['best_response'],
                    'confirmed': a.get('confirmed_crpr', 0)
                })

        # AE期间数据（以入组日期为0天参考）
        ae_periods = []
        for ae in aes:
            if ae.get('onset_date'):
                onset_date = ae['onset_date']
                ae_end_date = ae.get('end_date') or onset_date
                ae_start_days = 0
                if ref_date and onset_date:
                    try:
                        ae_start_days = max(0, (datetime.strptime(onset_date, '%Y-%m-%d') - datetime.strptime(ref_date, '%Y-%m-%d')).days)
                    except ValueError:
                        ae_start_days = 0
                ae_end_days = ae_start_days
                if ref_date and ae_end_date:
                    try:
                        ae_end_days = max(0, (datetime.strptime(ae_end_date, '%Y-%m-%d') - datetime.strptime(ref_date, '%Y-%m-%d')).days)
                    except ValueError:
                        ae_end_days = ae_start_days
                ae_periods.append({
                    'start_days': ae_start_days,
                    'end_days': ae_end_days,
                    'max_grade': ae.get('grade', 1),
                    'ae_term': ae.get('ae_term', 'AE')
                })

        has_sae = any(a.get('serious', 0) for a in aes)

        # 最佳疗评（跳过基线，按 RECIST 优先级：CR>PR>SD>PD>NE）
        resp_priority = {'CR': 0, 'PR': 1, 'SD': 2, 'PD': 3, 'NE': 4}
        best_resp = ''
        best_prio = 99
        for a in sorted_assessments[1:]:
            r = a.get('best_response', '')
            if r and resp_priority.get(r, 99) < best_prio:
                best_prio = resp_priority[r]
                best_resp = r

        # 患者状态: treatment(在组治疗中), followup(结束治疗随访中), off_study(死亡/失访)
        status_map = {
            'treatment': '在组治疗中',
            'followup': '结束治疗随访中',
            'off_study': '死亡/失访'
        }
        swimmer_status = status_map.get(patient_status, '在组治疗中')

        result.append({
            'patient_id': p['patient_id'],
            'days': days,                       # 治疗用药天数（首次→末次）
            'study_days': study_days,           # 研究状态天数（入组→终点/今天）
            'drug_start_offset': drug_start_offset,  # 入组到首次用药偏移天数
            'start_date': first_drug_date,      # 首次实际用药日期
            'end_date': last_drug_date,         # 末次实际用药日期
            'enroll_date': enroll_date,         # 入组日期
            'study_end_date': study_end_date,   # 研究终点日期
            'death_lost_date': death_lost_date,
            'is_extended': False,
            'first_drug_date': first_drug_date,
            'last_drug_date': last_drug_date,
            'best_response': best_resp,
            'has_sae': has_sae,
            'dose_group': p.get('dose_group', ''),
            'cancer_type': p.get('cancer_type', ''),
            'assessment_points': assessment_points,
            'ae_periods': ae_periods,
            'patient_status': swimmer_status,
            'status_raw': patient_status
        })
    return jsonify(result)

@api_error_handler
@app.route('/api/charts/spider/<int:project_id>', methods=['GET'])
def api_chart_spider(project_id):
    """蜘蛛图数据：每位患者SOD随时间变化，横坐标为距首次基线肿评天数"""
    patients = database.get_patients(project_id)
    ta_by_patient = database.get_tumor_assessments_by_project(project_id)
    result = []
    for p in patients:
        assessments = ta_by_patient.get(p['id'], [])
        if assessments:
            # 按日期排序，第一个为基线
            sorted_assess = sorted(assessments, key=lambda a: a.get('eval_date', ''))
            first_date = sorted_assess[0].get('eval_date') if sorted_assess else None
            baseline_sod = float(sorted_assess[0].get('target_sod') or 0) if sorted_assess else 0

            points = []
            for a in sorted_assess:
                if a.get('eval_date'):
                    # 计算距基线评估的天数
                    try:
                        days_from_baseline = (datetime.strptime(a['eval_date'], '%Y-%m-%d') - datetime.strptime(first_date, '%Y-%m-%d')).days
                    except ValueError:
                        days_from_baseline = 0
                    # 基线评估的SOD变化为0%
                    if a['eval_date'] == first_date:
                        points.append({
                            'date': a['eval_date'],
                            'days': 0,
                            'sod_change': 0
                        })
                    else:
                        # SOD变化：优先用已存值，否则自动计算
                        sod_change = a.get('sod_change')
                        if sod_change is None or sod_change == 0:
                            current_sod = float(a.get('target_sod') or 0)
                            if baseline_sod > 0 and current_sod > 0:
                                sod_change = (current_sod - baseline_sod) / baseline_sod * 100
                        if sod_change is not None:
                            points.append({
                                'date': a['eval_date'],
                                'days': max(0, days_from_baseline),
                                'sod_change': sod_change
                            })
            if points:
                result.append({
                    'patient_id': p['patient_id'],
                    'dose_group': p.get('dose_group', ''),
                    'cancer_type': p.get('cancer_type', ''),
                    'points': points
                })
    return jsonify(result)

@api_error_handler
@app.route('/api/charts/tumor-markers/<int:project_id>', methods=['GET'])
def api_chart_tumor_markers(project_id):
    """肿瘤指标趋势图数据，横坐标为距首次检测天数"""
    patients = database.get_patients(project_id)
    tm_by_patient = database.get_tumor_markers_by_project(project_id)
    marker_name = request.args.get('marker', 'CEA')
    result = []
    for p in patients:
        markers = tm_by_patient.get(p['id'], [])
        points = [m for m in markers if m.get('marker_name') == marker_name and m.get('test_date')]
        if points:
            # 找到最早的检测日期作为基线
            first_date = min(m['test_date'] for m in points)
            points_data = []
            for m in points:
                try:
                    days_from_first = (datetime.strptime(m['test_date'], '%Y-%m-%d') - datetime.strptime(first_date, '%Y-%m-%d')).days
                except ValueError:
                    days_from_first = 0
                points_data.append({
                    'date': m['test_date'],
                    'days': days_from_first,
                    'value': m['value'],
                    'upper_limit': m.get('upper_limit')
                })
            result.append({
                'patient_id': p['patient_id'],
                'dose_group': p.get('dose_group', ''),
                'points': points_data
            })
    return jsonify(result)

# ==================== 启动 ====================

if __name__ == '__main__':
    print("=" * 50)
    print("  临床研究数据看板")
    print(f"  访问地址: http://localhost:{APP_PORT}")
    print("=" * 50)
    # 入组表监听：只监听配置中启用的项目，不做启动时扫描（需求确认）
    enrollment_sync.start_watch_service()
    # debug=False 关闭 reloader：避免子进程重复、退出不干净（托盘模式下必需）
    # 安全：仅绑定本机回环地址，避免临床数据被局域网/公网直接访问
    app.run(debug=False, host='127.0.0.1', port=APP_PORT)
