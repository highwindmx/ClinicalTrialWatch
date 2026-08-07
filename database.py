import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'clinical.db')

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

@contextmanager
def get_db_ctx():
    """数据库连接上下文管理器，自动关闭连接（推荐新代码使用此方式）"""
    conn = get_db()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """初始化数据库，创建所有表"""
    conn = get_db()
    c = conn.cursor()

    # 项目表
    c.execute('''CREATE TABLE IF NOT EXISTS project (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT UNIQUE,
        description TEXT,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # 患者表
    c.execute('''CREATE TABLE IF NOT EXISTS patient (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        patient_id TEXT NOT NULL,
        name TEXT,
        status TEXT DEFAULT 'treatment',
        enroll_date DATE,
        off_study_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
        UNIQUE(project_id, patient_id)
    )''')

    # 数据库迁移：为已有数据库添加 off_study_date 列（如果不存在）
    try:
        c.execute("ALTER TABLE patient ADD COLUMN off_study_date DATE")
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 基线数据表
    c.execute('''CREATE TABLE IF NOT EXISTS baseline (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        age INTEGER,
        sex TEXT,
        cancer_type TEXT,
        cancer_type_id INTEGER,
        ecog_score INTEGER,
        dose_group TEXT,
        dose_group_id INTEGER,
        custom_data TEXT DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patient(id) ON DELETE CASCADE,
        FOREIGN KEY (cancer_type_id) REFERENCES cancer_type(id) ON DELETE SET NULL,
        FOREIGN KEY (dose_group_id) REFERENCES dose_group(id) ON DELETE SET NULL,
        UNIQUE(patient_id)
    )''')

    # 用药数据表
    c.execute('''CREATE TABLE IF NOT EXISTS medication (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        drug_name TEXT,
        planned_date DATE,
        actual_date DATE,
        dose REAL,
        dose_unit TEXT,
        cycle TEXT,
        day_in_cycle INTEGER,
        route TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patient(id) ON DELETE CASCADE
    )''')

    # 肿瘤评估表
    c.execute('''CREATE TABLE IF NOT EXISTS tumor_assessment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        eval_date DATE,
        eval_type TEXT,
        best_response TEXT,
        sod_change REAL,
        confirmed_crpr INTEGER DEFAULT 0,
        target_sod REAL,
        target_lesions TEXT,
        non_target_lesions TEXT,
        new_lesions INTEGER DEFAULT 0,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patient(id) ON DELETE CASCADE
    )''')

    # 不良事件表
    c.execute('''CREATE TABLE IF NOT EXISTS adverse_event (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        ae_term TEXT,
        onset_date DATE,
        end_date DATE,
        grade INTEGER,
        severity TEXT,
        outcome TEXT,
        drug_relation TEXT,
        action_taken TEXT,
        serious INTEGER DEFAULT 0,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patient(id) ON DELETE CASCADE
    )''')

    # PK数据表
    c.execute('''CREATE TABLE IF NOT EXISTS pk_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        sample_date DATE,
        sample_time TIME,
        time_point TEXT,
        concentration REAL,
        unit TEXT DEFAULT 'ng/mL',
        cycle TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patient(id) ON DELETE CASCADE
    )''')

    # 肿瘤指标表
    c.execute('''CREATE TABLE IF NOT EXISTS tumor_marker (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        test_date DATE,
        marker_name TEXT,
        value REAL,
        unit TEXT,
        upper_limit REAL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patient(id) ON DELETE CASCADE
    )''')

    # 自定义列定义表
    c.execute('''CREATE TABLE IF NOT EXISTS custom_column (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        module TEXT NOT NULL,
        column_name TEXT NOT NULL,
        column_label TEXT,
        column_type TEXT DEFAULT 'text',
        options TEXT,
        sort_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
        UNIQUE(project_id, module, column_name)
    )''')

    # 剂量组配置表
    c.execute('''CREATE TABLE IF NOT EXISTS dose_group (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        color TEXT DEFAULT '#378ADD',
        medication_interval INTEGER,
        assessment_interval INTEGER,
        sort_order INTEGER DEFAULT 0,
        FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE
    )''')

    # 癌肿类型配置表
    c.execute('''CREATE TABLE IF NOT EXISTS cancer_type (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        sort_order INTEGER DEFAULT 0,
        FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE
    )''')

    # ---- 数据库迁移：兼容旧表结构 ----
    # 1. medication.cycle: INTEGER → TEXT (如"C1D1")
    try:
        col_type = conn.execute("SELECT type FROM pragma_table_info('medication') WHERE name='cycle'").fetchone()
        if col_type and col_type[0] == 'INTEGER':
            conn.execute("ALTER TABLE medication RENAME COLUMN cycle TO cycle_old")
            conn.execute("ALTER TABLE medication ADD COLUMN cycle TEXT")
            conn.execute("UPDATE medication SET cycle = CAST(cycle_old AS TEXT)")
            conn.execute("ALTER TABLE medication DROP COLUMN cycle_old")
            print("迁移：medication.cycle 字段已从 INTEGER 转为 TEXT")
    except Exception as e:
        print(f"迁移 medication.cycle 失败: {e}")
        raise  # 关键迁移失败应上抛，避免数据不一致

    # 2. tumor_assessment: 新增 target_sod 字段（靶病灶SOD值，mm）
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(tumor_assessment)").fetchall()]
        if 'target_sod' not in cols:
            conn.execute("ALTER TABLE tumor_assessment ADD COLUMN target_sod REAL")
            print("迁移：tumor_assessment 表添加 target_sod 字段")
    except Exception as e:
        print(f"迁移 tumor_assessment.target_sod 失败: {e}")
        raise

    # 3. pk_data.cycle: INTEGER → TEXT
    try:
        col_type = conn.execute("SELECT type FROM pragma_table_info('pk_data') WHERE name='cycle'").fetchone()
        if col_type and col_type[0] == 'INTEGER':
            conn.execute("ALTER TABLE pk_data RENAME COLUMN cycle TO cycle_old")
            conn.execute("ALTER TABLE pk_data ADD COLUMN cycle TEXT")
            conn.execute("UPDATE pk_data SET cycle = CAST(cycle_old AS TEXT)")
            conn.execute("ALTER TABLE pk_data DROP COLUMN cycle_old")
            print("迁移：pk_data.cycle 字段已从 INTEGER 转为 TEXT")
    except Exception as e:
        print(f"迁移 pk_data.cycle 失败: {e}")
        raise

    conn.commit()
    conn.close()
    print(f"数据库初始化完成: {DB_PATH}")

    # 运行迁移
    migrate_db()

def migrate_db():
    """数据库迁移：添加新字段（幂等，重复运行安全）"""
    conn = get_db()
    c = conn.cursor()
    # 添加 dlt_days 字段
    try:
        c.execute("ALTER TABLE project ADD COLUMN dlt_days INTEGER DEFAULT 21")
        conn.commit()
        print("迁移：project 表添加 dlt_days 字段")
    except Exception as e:
        if "duplicate column name" not in str(e).lower():
            print(f"迁移 project.dlt_days 失败: {e}")
        # 已存在则忽略（幂等）

    # 添加 medication_interval（用药间隔天数，默认21天）
    try:
        c.execute("ALTER TABLE project ADD COLUMN medication_interval INTEGER DEFAULT 21")
        conn.commit()
        print("迁移：project 表添加 medication_interval 字段")
    except Exception as e:
        if "duplicate column name" not in str(e).lower():
            print(f"迁移 project.medication_interval 失败: {e}")

    # 添加 assessment_interval（肿评间隔天数，默认42天≈6周）
    try:
        c.execute("ALTER TABLE project ADD COLUMN assessment_interval INTEGER DEFAULT 42")
        conn.commit()
        print("迁移：project 表添加 assessment_interval 字段")
    except Exception as e:
        if "duplicate column name" not in str(e).lower():
            print(f"迁移 project.assessment_interval 失败: {e}")

    # 添加 assessment_calc_base（预计下次影像计算基准：baseline=基于基线影像时间，enroll=基于入组日期）
    try:
        c.execute("ALTER TABLE project ADD COLUMN assessment_calc_base TEXT DEFAULT 'baseline'")
        conn.commit()
        print("迁移：project 表添加 assessment_calc_base 字段")
    except Exception as e:
        if "duplicate column name" not in str(e).lower():
            print(f"迁移 project.assessment_calc_base 失败: {e}")

    # 添加 patient.dlt_observation 字段（是否进行DLT观察，默认1=是）
    try:
        c.execute("ALTER TABLE patient ADD COLUMN dlt_observation INTEGER DEFAULT 1")
        conn.commit()
        print("迁移：patient 表添加 dlt_observation 字段")
    except Exception as e:
        if "duplicate column name" not in str(e).lower():
            print(f"迁移 patient.dlt_observation 失败: {e}")
        # 已存在则忽略（幂等）

    # 删除 patient.name 冗余字段（SQLite 3.35+ 支持 DROP COLUMN）
    try:
        c.execute("ALTER TABLE patient DROP COLUMN name")
        conn.commit()
        print("迁移：patient 表删除 name 冗余字段")
    except Exception as e:
        if "no such column" not in str(e).lower():
            print(f"迁移 patient.name 失败: {e}")
        # 列已不存在则忽略（幂等）

    # baseline 表添加 cancer_type_id / dose_group_id 外键字段
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info('baseline')").fetchall()]
        if 'cancer_type_id' not in cols:
            conn.execute("ALTER TABLE baseline ADD COLUMN cancer_type_id INTEGER")
            conn.commit()
            print("迁移：baseline 表添加 cancer_type_id 字段")
    except Exception as e:
        if "duplicate column name" not in str(e).lower():
            print(f"迁移 baseline.cancer_type_id 失败: {e}")

    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info('baseline')").fetchall()]
        if 'dose_group_id' not in cols:
            conn.execute("ALTER TABLE baseline ADD COLUMN dose_group_id INTEGER")
            conn.commit()
            print("迁移：baseline 表添加 dose_group_id 字段")
    except Exception as e:
        if "duplicate column name" not in str(e).lower():
            print(f"迁移 baseline.dose_group_id 失败: {e}")

    # 添加 dose_group.medication_interval / assessment_interval（用药/肿评间隔，按剂量组配置）
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info('dose_group')").fetchall()]
        if 'medication_interval' not in cols:
            conn.execute("ALTER TABLE dose_group ADD COLUMN medication_interval INTEGER")
            conn.commit()
            print("迁移：dose_group 表添加 medication_interval 字段")
    except Exception as e:
        print(f"迁移 dose_group.medication_interval 失败: {e}")

    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info('dose_group')").fetchall()]
        if 'assessment_interval' not in cols:
            conn.execute("ALTER TABLE dose_group ADD COLUMN assessment_interval INTEGER")
            conn.commit()
            print("迁移：dose_group 表添加 assessment_interval 字段")
    except Exception as e:
        print(f"迁移 dose_group.assessment_interval 失败: {e}")

    conn.close()

# ==================== 项目 CRUD ====================

def get_projects():
    conn = get_db()
    rows = conn.execute("SELECT * FROM project ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_project(pid):
    conn = get_db()
    row = conn.execute("SELECT * FROM project WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_project(data):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO project (name, code, description, status) VALUES (?,?,?,?)",
              (data.get('name'), data.get('code'), data.get('description'), data.get('status', 'active')))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def update_project(pid, data):
    # 安全说明：字段名来自硬编码白名单 ('name','code','description','status','dlt_days')，
    # 非用户输入，不存在SQL注入风险；值使用参数化查询(?)
    conn = get_db()
    fields = []
    vals = []
    for k in ('name', 'code', 'description', 'status', 'dlt_days', 'medication_interval', 'assessment_interval', 'assessment_calc_base'):
        if k in data:
            fields.append(f"{k}=?")
            vals.append(data[k])
    if fields:
        fields.append("updated_at=CURRENT_TIMESTAMP")
        vals.append(pid)
        conn.execute(f"UPDATE project SET {','.join(fields)} WHERE id=?", vals)
        conn.commit()
    conn.close()

def delete_project(pid):
    with get_db_ctx() as conn:
        conn.execute("DELETE FROM project WHERE id=?", (pid,))
        conn.commit()

# ==================== 患者 CRUD ====================

def clear_project_data(project_id):
    """清空项目下的患者及所有关联数据（保留项目配置：癌肿类型、剂量组、自定义列）"""
    conn = get_db()
    try:
        # 获取该项目的所有患者db id
        patient_ids = [r[0] for r in conn.execute(
            "SELECT id FROM patient WHERE project_id=?", (project_id,)).fetchall()]
        if patient_ids:
            placeholders = ','.join('?' * len(patient_ids))
            # 按依赖顺序删除关联数据
            conn.execute(f"DELETE FROM tumor_marker WHERE patient_id IN ({placeholders})", patient_ids)
            conn.execute(f"DELETE FROM pk_data WHERE patient_id IN ({placeholders})", patient_ids)
            conn.execute(f"DELETE FROM adverse_event WHERE patient_id IN ({placeholders})", patient_ids)
            conn.execute(f"DELETE FROM tumor_assessment WHERE patient_id IN ({placeholders})", patient_ids)
            conn.execute(f"DELETE FROM medication WHERE patient_id IN ({placeholders})", patient_ids)
            conn.execute(f"DELETE FROM baseline WHERE patient_id IN ({placeholders})", patient_ids)
            conn.execute("DELETE FROM patient WHERE project_id=?", (project_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_patients(project_id=None):
    conn = get_db()
    if project_id:
        rows = conn.execute("""
            SELECT p.*, b.age, b.sex, b.cancer_type, b.cancer_type_id, b.ecog_score, b.dose_group, b.dose_group_id
            FROM patient p LEFT JOIN baseline b ON p.id=b.patient_id
            WHERE p.project_id=? ORDER BY p.patient_id
        """, (project_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT p.*, b.age, b.sex, b.cancer_type, b.cancer_type_id, b.ecog_score, b.dose_group, b.dose_group_id
            FROM patient p LEFT JOIN baseline b ON p.id=b.patient_id
            ORDER BY p.id
        """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_patient(pid):
    conn = get_db()
    row = conn.execute("""
        SELECT p.*, b.age, b.sex, b.cancer_type, b.cancer_type_id, b.ecog_score, b.dose_group, b.dose_group_id, b.custom_data
        FROM patient p LEFT JOIN baseline b ON p.id=b.patient_id
        WHERE p.id=?
    """, (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_patient(data):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO patient
                    (project_id, patient_id, status, enroll_date,
                     end_treatment_date, death_lost_date, dlt_observation)
                    VALUES (?,?,?,?,?,?,?)""",
                  (data['project_id'], data['patient_id'],
                   data.get('status', 'treatment'),
                   data.get('enroll_date'),
                   data.get('end_treatment_date'), data.get('death_lost_date'),
                   data.get('dlt_observation', 1)))
        new_id = c.lastrowid
        # 同时创建基线记录（cancer_type/dose_group 同时存 ID 和名称）
        cancer_type = data.get('cancer_type', '')
        dose_group = data.get('dose_group', '')
        cancer_type_id = data.get('cancer_type_id')
        dose_group_id = data.get('dose_group_id')
        # 如果传入了 ID 但没有名称，自动从配置表查名称
        if cancer_type_id and not cancer_type:
            row = conn.execute("SELECT name FROM cancer_type WHERE id=?", (cancer_type_id,)).fetchone()
            if row:
                cancer_type = row[0]
        if dose_group_id and not dose_group:
            row = conn.execute("SELECT name FROM dose_group WHERE id=?", (dose_group_id,)).fetchone()
            if row:
                dose_group = row[0]
        c.execute("INSERT INTO baseline (patient_id, age, sex, cancer_type, cancer_type_id, ecog_score, dose_group, dose_group_id, custom_data) VALUES (?,?,?,?,?,?,?,?,?)",
                  (new_id, data.get('age'), data.get('sex'), cancer_type, cancer_type_id,
                   data.get('ecog_score'), dose_group, dose_group_id, data.get('custom_data', '{}')))
        conn.commit()
        return new_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def update_patient(pid, data):
    # 安全说明：字段名来自硬编码白名单，非用户输入；值使用参数化查询
    conn = get_db()
    try:
        fields = []
        vals = []
        # 允许更新的字段白名单（含新增时间字段）
        allowed = ('patient_id', 'status', 'enroll_date',
                   'end_treatment_date', 'death_lost_date', 'dlt_observation')
        for k in allowed:
            if k in data:
                fields.append(f"{k}=?")
                vals.append(data[k])
        # 状态自动计算：优先使用传入值，否则基于三个日期自动计算
        auto_status = None
        if 'status' in data:
            auto_status = data['status']
        else:
            row = conn.execute(
                "SELECT enroll_date, end_treatment_date, death_lost_date FROM patient WHERE id=?", (pid,)
            ).fetchone()
            if row:
                db_enroll = data.get('enroll_date', row[0])
                db_end = data.get('end_treatment_date', row[1])
                db_death = data.get('death_lost_date', row[2])
                if db_death:
                    auto_status = 'off_study'
                elif db_end:
                    auto_status = 'followup'
                elif db_enroll:
                    auto_status = 'treatment'
                else:
                    auto_status = 'treatment'
        if auto_status and 'status' not in data:
            fields.append("status=?")
            vals.append(auto_status)
        if fields:
            fields.append("updated_at=CURRENT_TIMESTAMP")
            vals.append(pid)
            conn.execute(f"UPDATE patient SET {','.join(fields)} WHERE id=?", vals)
            conn.commit()
        # 更新基线（如果传入 cancer_type_id/dose_group_id，自动查名称）
        baseline_keys = ('age', 'sex', 'cancer_type', 'cancer_type_id', 'ecog_score', 'dose_group', 'dose_group_id', 'custom_data')
        bdata = {k: data[k] for k in baseline_keys if k in data}
        # 自动查名称：如果有ID就查名称；如果ID为None且没有同时传名称，才清除名称
        if 'cancer_type_id' in bdata and bdata['cancer_type_id']:
            row = conn.execute("SELECT name FROM cancer_type WHERE id=?", (bdata['cancer_type_id'],)).fetchone()
            if row:
                bdata['cancer_type'] = row[0]
        elif 'cancer_type_id' in bdata and bdata['cancer_type_id'] is None and 'cancer_type' not in bdata:
            bdata['cancer_type'] = None
        if 'dose_group_id' in bdata and bdata['dose_group_id']:
            row = conn.execute("SELECT name FROM dose_group WHERE id=?", (bdata['dose_group_id'],)).fetchone()
            if row:
                bdata['dose_group'] = row[0]
        elif 'dose_group_id' in bdata and bdata['dose_group_id'] is None and 'dose_group' not in bdata:
            bdata['dose_group'] = None
        if bdata:
            sets = ", ".join(f"{k}=?" for k in bdata)
            vals = list(bdata.values()) + [pid]
            conn.execute(f"UPDATE baseline SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE patient_id=?", vals)
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def delete_patient(pid):
    conn = get_db()
    conn.execute("DELETE FROM patient WHERE id=?", (pid,))
    conn.commit()
    conn.close()

# ==================== 用药 CRUD ====================

def get_medications(patient_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM medication WHERE patient_id=? ORDER BY actual_date, cycle, day_in_cycle", (patient_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_medication(data):
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO medication (patient_id, drug_name, planned_date, actual_date, dose, dose_unit, cycle, day_in_cycle, route, notes)
                 VALUES (?,?,?,?,?,?,?,?,?,?)""",
              (data['patient_id'], data.get('drug_name'), data.get('planned_date'), data.get('actual_date'),
               data.get('dose'), data.get('dose_unit'), data.get('cycle'), data.get('day_in_cycle'),
               data.get('route'), data.get('notes')))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def update_medication(mid, data):
    # 安全说明：字段名来自硬编码白名单，非用户输入；值使用参数化查询
    conn = get_db()
    fields = []
    vals = []
    for k in ('drug_name', 'planned_date', 'actual_date', 'dose', 'dose_unit', 'cycle', 'day_in_cycle', 'route', 'notes'):
        if k in data:
            fields.append(f"{k}=?")
            vals.append(data[k])
    if fields:
        fields.append("updated_at=CURRENT_TIMESTAMP")
        vals.append(mid)
        conn.execute(f"UPDATE medication SET {','.join(fields)} WHERE id=?", vals)
        conn.commit()
    conn.close()

def delete_medication(mid):
    conn = get_db()
    conn.execute("DELETE FROM medication WHERE id=?", (mid,))
    conn.commit()
    conn.close()

# ==================== 肿瘤评估 CRUD ====================

def get_tumor_assessments(patient_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM tumor_assessment WHERE patient_id=? ORDER BY eval_date", (patient_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_tumor_assessment(data):
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO tumor_assessment (patient_id, eval_date, eval_type, best_response, sod_change, confirmed_crpr, target_sod, target_lesions, non_target_lesions, new_lesions, notes)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
              (data['patient_id'], data.get('eval_date'), data.get('eval_type'), data.get('best_response'),
               data.get('sod_change'), data.get('confirmed_crpr', 0), data.get('target_sod'),
               data.get('target_lesions'), data.get('non_target_lesions'), data.get('new_lesions', 0), data.get('notes')))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def update_tumor_assessment(tid, data):
    # 安全说明：字段名来自硬编码白名单，非用户输入；值使用参数化查询
    conn = get_db()
    fields = []
    vals = []
    for k in ('eval_date', 'eval_type', 'best_response', 'sod_change', 'confirmed_crpr', 'target_sod', 'target_lesions', 'non_target_lesions', 'new_lesions', 'notes'):
        if k in data:
            fields.append(f"{k}=?")
            vals.append(data[k])
    if fields:
        fields.append("updated_at=CURRENT_TIMESTAMP")
        vals.append(tid)
        conn.execute(f"UPDATE tumor_assessment SET {','.join(fields)} WHERE id=?", vals)
        conn.commit()
    conn.close()

def delete_tumor_assessment(tid):
    conn = get_db()
    conn.execute("DELETE FROM tumor_assessment WHERE id=?", (tid,))
    conn.commit()
    conn.close()

# ==================== 不良事件 CRUD ====================

def get_adverse_events(patient_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM adverse_event WHERE patient_id=? ORDER BY onset_date", (patient_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_project_adverse_events(project_id):
    """获取项目下所有不良事件（JOIN 患者编号与剂量组），用于 AE 汇总页面"""
    conn = get_db()
    rows = conn.execute("""
        SELECT a.id, a.patient_id, p.patient_id as pid_text, b.dose_group,
               a.ae_term, a.onset_date, a.end_date, a.grade,
               a.severity, a.outcome, a.drug_relation, a.action_taken,
               a.serious, a.notes
        FROM adverse_event a
        JOIN patient p ON a.patient_id = p.id
        LEFT JOIN baseline b ON p.id = b.patient_id
        WHERE p.project_id = ?
        ORDER BY p.patient_id, a.onset_date
    """, (project_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_adverse_event(data):
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO adverse_event (patient_id, ae_term, onset_date, end_date, grade, severity, outcome, drug_relation, action_taken, serious, notes)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
              (data['patient_id'], data.get('ae_term'), data.get('onset_date'), data.get('end_date'),
               data.get('grade'), data.get('severity'), data.get('outcome'), data.get('drug_relation'),
               data.get('action_taken'), data.get('serious', 0), data.get('notes')))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def update_adverse_event(aid, data):
    # 安全说明：字段名来自硬编码白名单，非用户输入；值使用参数化查询
    conn = get_db()
    fields = []
    vals = []
    for k in ('ae_term', 'onset_date', 'end_date', 'grade', 'severity', 'outcome', 'drug_relation', 'action_taken', 'serious', 'notes'):
        if k in data:
            fields.append(f"{k}=?")
            vals.append(data[k])
    if fields:
        fields.append("updated_at=CURRENT_TIMESTAMP")
        vals.append(aid)
        conn.execute(f"UPDATE adverse_event SET {','.join(fields)} WHERE id=?", vals)
        conn.commit()
    conn.close()

def delete_adverse_event(aid):
    conn = get_db()
    conn.execute("DELETE FROM adverse_event WHERE id=?", (aid,))
    conn.commit()
    conn.close()

# ==================== PK数据 CRUD ====================

def get_pk_data(patient_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM pk_data WHERE patient_id=? ORDER BY sample_date, sample_time", (patient_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_pk_data(data):
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO pk_data (patient_id, sample_date, sample_time, time_point, concentration, unit, cycle, notes)
                 VALUES (?,?,?,?,?,?,?,?)""",
              (data['patient_id'], data.get('sample_date'), data.get('sample_time'), data.get('time_point'),
               data.get('concentration'), data.get('unit', 'ng/mL'), data.get('cycle'), data.get('notes')))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def update_pk_data(pkid, data):
    # 安全说明：字段名来自硬编码白名单，非用户输入；值使用参数化查询
    conn = get_db()
    fields = []
    vals = []
    for k in ('sample_date', 'sample_time', 'time_point', 'concentration', 'unit', 'cycle', 'notes'):
        if k in data:
            fields.append(f"{k}=?")
            vals.append(data[k])
    if fields:
        fields.append("updated_at=CURRENT_TIMESTAMP")
        vals.append(pkid)
        conn.execute(f"UPDATE pk_data SET {','.join(fields)} WHERE id=?", vals)
        conn.commit()
    conn.close()

def delete_pk_data(pkid):
    conn = get_db()
    conn.execute("DELETE FROM pk_data WHERE id=?", (pkid,))
    conn.commit()
    conn.close()

# ==================== 肿瘤指标 CRUD ====================

def get_tumor_markers(patient_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM tumor_marker WHERE patient_id=? ORDER BY test_date", (patient_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_tumor_marker(data):
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO tumor_marker (patient_id, test_date, marker_name, value, unit, upper_limit, notes)
                 VALUES (?,?,?,?,?,?,?)""",
              (data['patient_id'], data.get('test_date'), data.get('marker_name'), data.get('value'),
               data.get('unit'), data.get('upper_limit'), data.get('notes')))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def update_tumor_marker(tmid, data):
    # 安全说明：字段名来自硬编码白名单，非用户输入；值使用参数化查询
    conn = get_db()
    fields = []
    vals = []
    for k in ('test_date', 'marker_name', 'value', 'unit', 'upper_limit', 'notes'):
        if k in data:
            fields.append(f"{k}=?")
            vals.append(data[k])
    if fields:
        fields.append("updated_at=CURRENT_TIMESTAMP")
        vals.append(tmid)
        conn.execute(f"UPDATE tumor_marker SET {','.join(fields)} WHERE id=?", vals)
        conn.commit()
    conn.close()

def delete_tumor_marker(tmid):
    conn = get_db()
    conn.execute("DELETE FROM tumor_marker WHERE id=?", (tmid,))
    conn.commit()
    conn.close()

# ==================== 自定义列 CRUD ====================

def get_custom_columns(project_id, module=None):
    conn = get_db()
    if module:
        rows = conn.execute("SELECT * FROM custom_column WHERE project_id=? AND module=? ORDER BY sort_order",
                            (project_id, module)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM custom_column WHERE project_id=? ORDER BY module, sort_order",
                            (project_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_custom_column(data):
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO custom_column (project_id, module, column_name, column_label, column_type, options, sort_order)
                 VALUES (?,?,?,?,?,?,?)""",
              (data['project_id'], data['module'], data['column_name'], data.get('column_label'),
               data.get('column_type', 'text'), data.get('options'), data.get('sort_order', 0)))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def delete_custom_column(ccid):
    conn = get_db()
    conn.execute("DELETE FROM custom_column WHERE id=?", (ccid,))
    conn.commit()
    conn.close()

# ==================== 甘特图事件聚合 ====================

def get_events_for_gantt(project_id, year, month):
    """获取指定项目、年月下所有患者的日历事件（用于甘特图展示）
    内部转换为日期范围调用 get_events_for_gantt_range，避免重复代码
    """
    # 计算该月第一天和最后一天
    import calendar as cal_module
    first_day = f"{year}-{month:02d}-01"
    last_day_num = cal_module.monthrange(year, month)[1]
    last_day = f"{year}-{month:02d}-{last_day_num}"
    return get_events_for_gantt_range(project_id, first_day, last_day)

def get_events_for_gantt_range(project_id, start_date, end_date):
    """获取指定项目、日期范围内所有患者的日历事件（用于甘特图展示）
    包含真实事件 + 在组治疗患者的预测下次用药/肿评事件
    """
    from datetime import date, timedelta
    conn = get_db()
    events = []

    # 获取项目配置（用药间隔、肿评间隔、预计下次影像计算基准）
    proj = conn.execute(
        "SELECT medication_interval, assessment_interval, assessment_calc_base FROM project WHERE id=?",
        (project_id,)
    ).fetchone()
    med_interval = proj['medication_interval'] if proj else 21
    assess_interval = proj['assessment_interval'] if proj else 42
    assess_calc_base = proj['assessment_calc_base'] if proj else 'baseline'

    # 用药事件（仅实际给药日期）
    med_rows = conn.execute("""
        SELECT m.id, m.patient_id, p.patient_id as pid_text,
               m.drug_name, m.actual_date, m.dose, m.dose_unit, m.cycle
        FROM medication m JOIN patient p ON m.patient_id=p.id
        WHERE p.project_id=? AND m.actual_date >= ? AND m.actual_date <= ?
    """, (project_id, start_date, end_date)).fetchall()

    for r in med_rows:
        if r['actual_date']:
            events.append({
                'type': 'drug', 'id': r['id'], 'patient_id': r['patient_id'],
                'pid_text': r['pid_text'],
                'date': r['actual_date'], 'actual_date': r['actual_date'],
                'label': f"{r['drug_name']} {r['cycle'] or ''}",
                'detail': f"剂量: {r['dose']}{r['dose_unit'] or ''}"
            })

    # 肿瘤评估事件
    ta_rows = conn.execute("""
        SELECT t.id, t.patient_id, p.patient_id as pid_text,
               t.eval_date, t.eval_type, t.best_response
        FROM tumor_assessment t JOIN patient p ON t.patient_id=p.id
        WHERE p.project_id=? AND t.eval_date >= ? AND t.eval_date <= ?
    """, (project_id, start_date, end_date)).fetchall()

    for r in ta_rows:
        if r['eval_date']:
            events.append({
                'type': 'assessment', 'id': r['id'], 'patient_id': r['patient_id'],
                'pid_text': r['pid_text'],
                'date': r['eval_date'], 'label': f"疗评:{r['best_response'] or r['eval_type'] or ''}",
                'detail': f"最佳疗评: {r['best_response'] or '-'}"
            })

    # AE事件
    ae_rows = conn.execute("""
        SELECT a.id, a.patient_id, p.patient_id as pid_text,
               a.ae_term, a.onset_date, a.end_date, a.grade
        FROM adverse_event a JOIN patient p ON a.patient_id=p.id
        WHERE p.project_id=? AND (
            (a.onset_date >= ? AND a.onset_date <= ?) OR
            (a.end_date >= ? AND a.end_date <= ?) OR
            (a.onset_date < ? AND (a.end_date IS NULL OR a.end_date > ?))
        )
    """, (project_id, start_date, end_date, start_date, end_date, start_date, end_date)).fetchall()

    for r in ae_rows:
        start = r['onset_date']
        end = r['end_date'] or start
        if start:
            events.append({
                'type': 'ae', 'id': r['id'], 'patient_id': r['patient_id'],
                'pid_text': r['pid_text'],
                'date': start, 'end_date': end,
                'label': f"AE:{r['ae_term']} G{r['grade']}",
                'detail': f"{r['ae_term']} {r['grade']}级 ({start}~{end or '持续'})",
                'grade': r['grade']
            })

    # PK事件
    pk_rows = conn.execute("""
        SELECT k.id, k.patient_id, p.patient_id as pid_text,
               k.sample_date, k.time_point, k.concentration, k.cycle
        FROM pk_data k JOIN patient p ON k.patient_id=p.id
        WHERE p.project_id=? AND k.sample_date >= ? AND k.sample_date <= ?
    """, (project_id, start_date, end_date)).fetchall()

    for r in pk_rows:
        if r['sample_date']:
            events.append({
                'type': 'pk', 'id': r['id'], 'patient_id': r['patient_id'],
                'pid_text': r['pid_text'],
                'date': r['sample_date'], 'label': f"PK:{r['time_point'] or 'C'+str(r['cycle'] or '')}",
                'detail': f"浓度: {r['concentration']} {r['unit'] if 'unit' in r.keys() else 'ng/mL'}"
            })

    # 为在组治疗中的患者生成预测下次用药和肿评事件
    # 每个患者的间隔取自其剂量组配置（剂量组未设置时跳过预测）
    treatment_patients = conn.execute("""
        SELECT p.id, p.patient_id, p.enroll_date,
               (SELECT MAX(actual_date) FROM medication WHERE patient_id=p.id AND actual_date IS NOT NULL) as last_drug_date,
               (SELECT MAX(eval_date) FROM tumor_assessment WHERE patient_id=p.id AND eval_date IS NOT NULL) as last_assess_date,
               (SELECT COUNT(*) FROM tumor_assessment WHERE patient_id=p.id) as assess_count,
               dg.medication_interval as dg_med_interval,
               dg.assessment_interval as dg_assess_interval
        FROM patient p
        LEFT JOIN baseline b ON p.id = b.patient_id
        LEFT JOIN dose_group dg ON b.dose_group_id = dg.id
        WHERE p.project_id=? AND p.status='treatment'
    """, (project_id,)).fetchall()

    # 根据剂量组间隔生成预测事件
    for p in treatment_patients:
        # 预测下次用药
        if p['last_drug_date'] and p['dg_med_interval'] is not None:
            last_drug = date.fromisoformat(p['last_drug_date'])
            next_drug = last_drug + timedelta(days=p['dg_med_interval'])
            next_drug_str = next_drug.isoformat()
            if start_date <= next_drug_str <= end_date:
                events.append({
                    'type': 'next_drug',
                    'patient_id': p['id'],
                    'pid_text': p['patient_id'],
                    'date': next_drug_str,
                    'label': '计划用药',
                    'detail': f"上次用药: {p['last_drug_date']}, 间隔: {p['dg_med_interval']}天"
                })
        # 预测下次肿评（支持两种计算基准）
        if p['dg_assess_interval'] is not None:
            next_assess = None
            detail_text = ''
            label_text = '预测肿评'

            if assess_calc_base == 'enroll' and p['enroll_date']:
                # 基于入组日期：入组日期 + 间隔 × 已完成评估次数
                enroll = date.fromisoformat(p['enroll_date'])
                count = p['assess_count'] or 0
                if count == 0:
                    next_assess = enroll
                else:
                    next_assess = enroll + timedelta(days=count * p['dg_assess_interval'])
                detail_text = f"入组日期: {p['enroll_date']}, 间隔: {p['dg_assess_interval']}天, 已完成评估: {count}次"
                label_text = '预测影像'
            elif p['last_assess_date']:
                # 基于基线影像时间：上次影像日期 + 间隔（原有逻辑）
                last_assess = date.fromisoformat(p['last_assess_date'])
                next_assess = last_assess + timedelta(days=p['dg_assess_interval'])
                detail_text = f"上次肿评: {p['last_assess_date']}, 间隔: {p['dg_assess_interval']}天"

            if next_assess:
                next_assess_str = next_assess.isoformat()
                if start_date <= next_assess_str <= end_date:
                    events.append({
                        'type': 'next_assessment',
                        'patient_id': p['id'],
                        'pid_text': p['patient_id'],
                        'date': next_assess_str,
                        'label': label_text,
                        'detail': detail_text
                    })

    conn.close()
    return events


# ==================== 剂量组 CRUD ====================

def get_dose_groups(project_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM dose_group WHERE project_id=? ORDER BY sort_order, id", (project_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_dose_group(data):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO dose_group (project_id, name, color, medication_interval, assessment_interval, sort_order) VALUES (?,?,?,?,?,?)",
              (data['project_id'], data.get('name'), data.get('color', '#378ADD'),
               data.get('medication_interval'), data.get('assessment_interval'),
               data.get('sort_order', 0)))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def update_dose_group(dgid, data):
    conn = get_db()
    fields = []
    vals = []
    for k in ('name', 'color', 'sort_order', 'medication_interval', 'assessment_interval'):
        if k in data:
            fields.append(f"{k}=?")
            vals.append(data[k])
    if fields:
        vals.append(dgid)
        conn.execute(f"UPDATE dose_group SET {','.join(fields)} WHERE id=?", vals)
        conn.commit()
    conn.close()

def delete_dose_group(dgid):
    conn = get_db()
    conn.execute("DELETE FROM dose_group WHERE id=?", (dgid,))
    conn.commit()
    conn.close()


# ==================== 癌肿类型 CRUD ====================

def get_cancer_types(project_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM cancer_type WHERE project_id=? ORDER BY sort_order, id", (project_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_cancer_type(data):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO cancer_type (project_id, name, sort_order) VALUES (?,?,?)",
              (data['project_id'], data.get('name'), data.get('sort_order', 0)))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def update_cancer_type(ctid, data):
    conn = get_db()
    fields = []
    vals = []
    for k in ('name', 'sort_order'):
        if k in data:
            fields.append(f"{k}=?")
            vals.append(data[k])
    if fields:
        vals.append(ctid)
        conn.execute(f"UPDATE cancer_type SET {','.join(fields)} WHERE id=?", vals)
        conn.commit()
    conn.close()

def delete_cancer_type(ctid):
    conn = get_db()
    conn.execute("DELETE FROM cancer_type WHERE id=?", (ctid,))
    conn.commit()
    conn.close()


# ==================== Demo 数据生成 ====================

def generate_demo_data(project_id):
    """为指定项目生成demo数据：配置项 + 患者 + 全部临床数据"""
    from datetime import date, timedelta
    conn = get_db()
    c = conn.cursor()

    # 检查项目是否存在
    proj = conn.execute("SELECT id FROM project WHERE id=?", (project_id,)).fetchone()
    if not proj:
        conn.close()
        return {'error': '项目不存在'}

    # 检查是否已有患者数据（避免重复生成）
    existing = conn.execute("SELECT COUNT(*) FROM patient WHERE project_id=?", (project_id,)).fetchone()[0]
    if existing > 0:
        conn.close()
        return {'error': f'该项目已有 {existing} 例患者，请先清空再生成Demo数据'}

    today = date.today()

    # ── 1. 剂量组 ──
    dose_groups = [
        ('3mg/kg',  '#3B82F6', 0, 21,  42),
        ('6mg/kg',  '#10B981', 1, 21,  42),
        ('10mg/kg', '#F59E0B', 2, 21,  42),
    ]
    dose_group_ids = {}
    for name, color, order, med_int, assess_int in dose_groups:
        c.execute("INSERT INTO dose_group (project_id, name, color, sort_order, medication_interval, assessment_interval) VALUES (?,?,?,?,?,?)",
                  (project_id, name, color, order, med_int, assess_int))
        dose_group_ids[name] = c.lastrowid

    # ── 2. 癌肿类型 ──
    cancer_types = ['NSCLC', 'PDAC']
    cancer_type_ids = {}
    for i, name in enumerate(cancer_types):
        c.execute("INSERT INTO cancer_type (project_id, name, sort_order) VALUES (?,?,?)",
                  (project_id, name, i))
        cancer_type_ids[name] = c.lastrowid

    # ── 3. 患者（8例） ──
    # 日期相对于today动态计算，确保demo数据总是"当前"的
    # enroll_offsets: 入组距今天数
    patients_spec = [
        # (patient_id, status, enroll_offset_days, age, sex, cancer_type, ecog, dose_group, dlt_observation)
        ('001', 'treatment', -105, 62, '男', 'NSCLC', 1, '3mg/kg',  1),
        ('002', 'treatment', -100, 55, '女', 'NSCLC', 0, '3mg/kg',  1),
        ('003', 'treatment', -90,  68, '男', 'PDAC',  2, '3mg/kg',  1),
        ('004', 'treatment', -80,  49, '女', 'NSCLC', 1, '6mg/kg',  1),
        ('005', 'followup',  -72,  71, '男', 'NSCLC', 1, '6mg/kg',  1),
        ('006', 'treatment', -61,  58, '女', 'NSCLC', 0, '6mg/kg',  1),
        ('007', 'treatment', -52,  63, '男', 'NSCLC', 1, '10mg/kg', 1),
        ('008', 'treatment', -30,  45, '女', 'NSCLC', 0, '10mg/kg', 1),
    ]
    pat_ids = {}
    for pid, status, offset, age, sex, ctype, ecog, dgrp, dlt in patients_spec:
        enroll_date = (today + timedelta(days=offset)).isoformat()
        c.execute("INSERT INTO patient (project_id, patient_id, status, enroll_date, dlt_observation) VALUES (?,?,?,?,?)",
                  (project_id, pid, status, enroll_date, dlt))
        db_id = c.lastrowid
        c.execute("INSERT INTO baseline (patient_id, age, sex, cancer_type, cancer_type_id, ecog_score, dose_group, dose_group_id, custom_data) VALUES (?,?,?,?,?,?,?,?,?)",
                  (db_id, age, sex, ctype, cancer_type_ids[ctype], ecog, dgrp, dose_group_ids[dgrp], '{}'))
        pat_ids[pid] = db_id
    conn.commit()

    # ── 4. 用药数据 ──
    # 每位患者每21天一个疗程，cycle_count根据入组时间计算
    drug_name = 'ABC-001'
    dose_map = {'3mg/kg': 200, '6mg/kg': 400, '10mg/kg': 600}
    for pid, status, offset, age, sex, ctype, ecog, dgrp, dlt in patients_spec:
        db_id = pat_ids[pid]
        enroll_date = today + timedelta(days=offset)
        # 计算可完成的疗程数（距今天数 / 21），最多6个，已停药患者少几个
        max_cycles = 6
        if pid == '005':
            max_cycles = 3  # PD停药
        elif pid == '008':
            max_cycles = 2  # 入组晚
        elif pid == '006':
            max_cycles = 4
        elif pid == '007':
            max_cycles = 3

        for cycle in range(1, max_cycles + 1):
            planned = (enroll_date + timedelta(days=21 * (cycle - 1))).isoformat()
            # 最后一个疗程如果还没到则 actual_date 为空
            planned_date = enroll_date + timedelta(days=21 * (cycle - 1))
            if planned_date > today:
                actual = None
            else:
                actual = planned
            c.execute("""INSERT INTO medication (patient_id, drug_name, planned_date, actual_date, dose, dose_unit, cycle, day_in_cycle, route)
                         VALUES (?,?,?,?,?,?,?,?,?)""",
                      (db_id, drug_name, planned, actual, dose_map[dgrp], 'mg', f'C{cycle}', 1, 'iv'))
    conn.commit()

    # ── 5. 肿瘤评估 ──
    # 每位患者从入组起每6-8周评估一次
    ta_specs = {
        # pid: (baseline_sod, [(weeks_offset, best_response, sod_change, confirmed_crpr)])
        '001': (80, [
            (0, '', 0, 0),      # 基线
            (7, 'SD', -18.0, 0),
            (14, 'PR', -36.5, 0),
            (21, 'PR', -41.2, 1),
        ]),
        '002': (85, [
            (0, '', 0, 0),
            (7, 'SD', -12.0, 0),
            (14, 'PR', -31.5, 0),
            (21, 'PR', -38.0, 1),
        ]),
        '003': (100, [
            (0, '', 0, 0),
            (7, 'SD', -8.0, 0),
            (14, 'SD', -14.0, 0),
            (21, 'SD', -17.5, 0),
        ]),
        '004': (75, [
            (0, '', 0, 0),
            (7, 'SD', -15.5, 0),
            (14, 'PR', -33.0, 0),
            (21, 'PR', -39.5, 1),
        ]),
        '005': (70, [
            (0, '', 0, 0),
            (7, 'SD', 5.0, 0),
            (14, 'PD', 22.5, 0),
        ]),
        '006': (90, [
            (0, '', 0, 0),
            (7, 'SD', -10.0, 0),
            (14, 'PR', -29.5, 0),
            (21, 'PR', -35.0, 1),
        ]),
        '007': (78, [
            (0, '', 0, 0),
            (7, 'SD', -20.0, 0),
            (14, 'PR', -42.5, 0),
        ]),
    }
    for pid, (baseline_sod, entries) in ta_specs.items():
        db_id = pat_ids[pid]
        enroll_offset = dict((p[0], p[2]) for p in patients_spec)[pid]
        enroll_date = today + timedelta(days=enroll_offset)
        for i, (weeks, best_resp, sod, confirmed) in enumerate(entries):
            eval_date = (enroll_date + timedelta(weeks=weeks)).isoformat()
            eval_type = '基线' if i == 0 else f'V{i}'
            target_sod = round(baseline_sod * (1 + sod / 100), 1)
            # 只插入不晚于今天的评估
            if enroll_date + timedelta(weeks=weeks) <= today + timedelta(days=7):
                c.execute("""INSERT INTO tumor_assessment
                             (patient_id, eval_date, eval_type, best_response, sod_change, confirmed_crpr, target_sod, new_lesions)
                             VALUES (?,?,?,?,?,?,?,?)""",
                          (db_id, eval_date, eval_type, best_resp, sod, confirmed, target_sod, 0))
    conn.commit()

    # ── 6. 不良事件 ──
    ae_specs = [
        # (pid, ae_term, weeks_after_enroll, duration_days, grade, severity, outcome, drug_relation, action_taken, serious)
        ('001', '皮疹',          4, 23, 2, '中度', '已恢复', '可能相关', '对症处理', 0),
        ('002', '乏力',          5, 20, 1, '轻度', '已恢复', '可能相关', '观察', 0),
        ('003', '恶心呕吐',      1, 15, 1, '轻度', '已恢复', '可能相关', '止吐药', 0),
        ('004', '肝功能异常',    4, 18, 2, '中度', '已恢复', '可能相关', '剂量调整', 0),
        ('005', '甲状腺功能减退', 4, 0, 3, '重度', '持续', '很可能相关', '激素替代治疗', 1),
        ('006', '皮疹',          3, 19, 3, '重度', '已恢复', '很可能相关', '停药14天', 1),
        ('007', '输液反应',      0, 1, 1, '轻度', '已恢复', '可能相关', '减慢输液速度', 0),
    ]
    for pid, term, weeks, dur, grade, sev, outcome, relation, action, serious in ae_specs:
        db_id = pat_ids[pid]
        enroll_offset = dict((p[0], p[2]) for p in patients_spec)[pid]
        onset = (today + timedelta(days=enroll_offset) + timedelta(weeks=weeks)).isoformat()
        end = (today + timedelta(days=enroll_offset) + timedelta(weeks=weeks) + timedelta(days=dur)).isoformat() if dur > 0 else None
        # 只插入不晚于今天的AE
        if today + timedelta(days=enroll_offset) + timedelta(weeks=weeks) <= today:
            c.execute("""INSERT INTO adverse_event
                         (patient_id, ae_term, onset_date, end_date, grade, severity, outcome, drug_relation, action_taken, serious)
                         VALUES (?,?,?,?,?,?,?,?,?,?)""",
                      (db_id, term, onset, end, grade, sev, outcome, relation, action, serious))
    conn.commit()

    # ── 7. PK数据 ──
    pk_timepoints = ['0h', '0.5h', '1h', '2h', '4h', '6h', '8h', '24h']
    pk_times = ['08:00', '08:30', '09:00', '10:00', '12:00', '14:00', '16:00', '08:00']
    pk_specs = {
        # pid: [conc_list]
        '001': [0, 85.2, 142.6, 198.4, 176.3, 134.5, 98.7, 42.1],
        '002': [0, 78.5, 130.2, 185.7, 162.4, 122.8, 89.3, 38.6],
        '004': [0, 152.3, 248.7, 342.5, 315.8, 241.6, 178.2, 76.4],
    }
    for pid, conclist in pk_specs.items():
        db_id = pat_ids[pid]
        enroll_offset = dict((p[0], p[2]) for p in patients_spec)[pid]
        pk_date = (today + timedelta(days=enroll_offset)).isoformat()
        for i, (tp, conc) in enumerate(zip(pk_timepoints, conclist)):
            c.execute("""INSERT INTO pk_data (patient_id, sample_date, sample_time, time_point, concentration, unit, cycle)
                         VALUES (?,?,?,?,?,?,?)""",
                      (db_id, pk_date, pk_times[i], tp, conc, 'ng/mL', 'C1'))
    conn.commit()

    # ── 8. 肿瘤标记物 ──
    marker_specs = {
        '001': [(7, 'CEA', 18.5), (14, 'CEA', 9.2), (21, 'CEA', 6.8)],
        '002': [(7, 'CEA', 22.1), (14, 'CEA', 11.4), (21, 'CEA', 7.3)],
        '003': [(7, 'CEA', 45.2), (14, 'CEA', 38.7), (21, 'CEA', 34.1)],
        '004': [(7, 'CEA', 16.3), (14, 'CEA', 8.5), (21, 'CEA', 5.9)],
        '005': [(7, 'CEA', 12.8), (14, 'CEA', 28.6)],
        '006': [(7, 'CEA', 19.4), (14, 'CEA', 10.2), (21, 'CEA', 7.1)],
        '007': [(7, 'CEA', 21.5), (14, 'CEA', 8.8)],
    }
    for pid, entries in marker_specs.items():
        db_id = pat_ids[pid]
        enroll_offset = dict((p[0], p[2]) for p in patients_spec)[pid]
        for weeks, marker_name, value in entries:
            test_date = (today + timedelta(days=enroll_offset) + timedelta(weeks=weeks)).isoformat()
            if today + timedelta(days=enroll_offset) + timedelta(weeks=weeks) <= today + timedelta(days=7):
                c.execute("""INSERT INTO tumor_marker (patient_id, test_date, marker_name, value, unit, upper_limit)
                             VALUES (?,?,?,?,?,?)""",
                          (db_id, test_date, marker_name, value, 'ng/mL', 5.0))
    conn.commit()
    conn.close()

    return {
        'ok': True,
        'stats': {
            'dose_groups': len(dose_groups),
            'cancer_types': len(cancer_types),
            'patients': len(patients_spec),
        }
    }
