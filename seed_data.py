"""
重新生成示例数据脚本（命令行用）
- 清空全库数据
- 创建一个 Demo 项目
- 调用 database.generate_demo_data() 填充数据
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import database

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'clinical.db')

def run():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()

    # ── 清空旧数据（保留表结构）──────────────────────────────────
    for t in ['tumor_marker','pk_data','adverse_event','tumor_assessment',
              'medication','baseline','patient','cancer_type','dose_group',
              'custom_column','project']:
        c.execute(f"DELETE FROM {t}")
    for t in ['tumor_marker','pk_data','adverse_event','tumor_assessment',
              'medication','baseline','patient','cancer_type','dose_group',
              'custom_column','project']:
        c.execute(f"DELETE FROM sqlite_sequence WHERE name='{t}'")
    conn.commit()
    conn.close()

    # ── 创建项目 ──
    proj_id = database.create_project({
        'name': 'ABC-001 非小细胞肺癌',
        'code': 'ABC-001',
        'description': 'PD-1抑制剂 II期临床试验',
    })

    # ── 填充Demo数据（复用 database.generate_demo_data，日期动态计算）──
    result = database.generate_demo_data(proj_id)
    if 'error' in result:
        print(f"❌ 生成失败: {result['error']}")
        return

    s = result['stats']
    print("✅ 示例数据生成完成！")
    print(f"  项目: ABC-001 非小细胞肺癌 (id={proj_id})")
    print(f"  剂量组: {s['dose_groups']}个")
    print(f"  癌肿类型: {s['cancer_types']}个")
    print(f"  患者: {s['patients']}例")

if __name__ == '__main__':
    run()
