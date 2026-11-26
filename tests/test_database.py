"""
clinWatch 数据库最小单元测试（纯标准库，可直接 `python tests/test_database.py` 运行，
也可用 pytest 运行）。

测试使用 CLINWATCH_TEST_DB 环境变量把数据库指向临时文件，不污染真实 data/clinical.db。
注意：必须在 import database 之前设置该环境变量，因为 DB_PATH 在模块导入时读取。
"""

import os
import sys
import tempfile

# 把项目根目录加入 sys.path，使 `python tests/test_database.py` 也能 import database
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 必须在 import database 之前设置，DB_PATH 在模块加载时读取
_TEST_DB = os.path.join(tempfile.gettempdir(), "clinwatch_test.db")
for _suffix in ("", "-wal", "-shm"):
    _p = _TEST_DB + _suffix
    if os.path.exists(_p):
        try:
            os.remove(_p)
        except OSError:
            pass
os.environ["CLINWATCH_TEST_DB"] = _TEST_DB

import database as db  # noqa: E402  (env var set above)


def teardown_module(module):
    for _suffix in ("", "-wal", "-shm"):
        _p = _TEST_DB + _suffix
        if os.path.exists(_p):
            try:
                os.remove(_p)
            except OSError:
                pass


def test_init_db_idempotent():
    """init_db 可重复调用且不抛异常（表/索引 CREATE IF NOT EXISTS 幂等）。"""
    db.init_db()
    db.init_db()  # 第二次必须安全

    conn = db.get_db()
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    finally:
        conn.close()

    for t in ("project", "patient", "baseline", "medication", "tumor_assessment",
              "adverse_event", "pk_data", "tumor_marker", "cancer_type", "dose_group"):
        assert t in names, f"缺少表 {t}"

    # 新增的 patient_id 索引应已建立
    for t in ("medication", "tumor_assessment", "adverse_event", "pk_data",
              "tumor_marker", "baseline"):
        assert f"idx_{t}_patient_id" in indexes, f"缺少索引 idx_{t}_patient_id"


def test_migrations_repeatable():
    """迁移可重复执行，不应抛错（ALTER ADD COLUMN 幂等）。"""
    db.init_db()
    db.migrate_db()  # 第二次运行应安全（重复列名被忽略）
    db.migrate_db()


def test_project_and_patient_crud():
    db.init_db()

    pid = db.create_project({"name": "测试项目", "code": "TEST-1"})
    assert db.get_project(pid)["name"] == "测试项目"

    p_id = db.create_patient({
        "project_id": pid,
        "patient_id": "P-001",
        "age": 60,
        "sex": "男",
        "cancer_type": "肺癌",
        "ecog_score": 1,
        "dose_group": "A组",
    })
    p = db.get_patient(p_id)
    assert p["patient_id"] == "P-001"
    assert p["age"] == 60
    # create_patient 应自动创建 baseline 记录
    assert p["cancer_type"] == "肺癌"
    assert p["ecog_score"] == 1

    db.update_patient(p_id, {"status": "off_study", "death_lost_date": "2026-01-01"})
    p2 = db.get_patient(p_id)
    assert p2["status"] == "off_study"

    patients = db.get_patients(pid)
    assert len(patients) == 1
    assert patients[0]["id"] == p_id

    # 清空项目数据后患者应消失（保留项目配置）
    db.clear_project_data(pid)
    assert db.get_patients(pid) == []
    assert db.get_project(pid) is not None  # 项目本身保留

    db.delete_project(pid)
    assert db.get_project(pid) is None


def test_clear_project_data_isolated():
    """clear_project_data 只清空指定项目，不影响其它项目。"""
    db.init_db()
    pa = db.create_project({"name": "A", "code": "A"})
    pb = db.create_project({"name": "B", "code": "B"})
    db.create_patient({"project_id": pa, "patient_id": "A-1"})
    db.create_patient({"project_id": pb, "patient_id": "B-1"})

    db.clear_project_data(pa)
    assert db.get_patients(pa) == []
    assert len(db.get_patients(pb)) == 1

    db.delete_project(pa)
    db.delete_project(pb)


if __name__ == "__main__":
    test_init_db_idempotent()
    test_migrations_repeatable()
    test_project_and_patient_crud()
    test_clear_project_data_isolated()
    print("全部数据库测试通过 ✅")
