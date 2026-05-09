# ClinicalTrialWatch / 临床研究数据看板

<div align="center">

**一个面向临床试验的开源数据可视化与管理工具**
*A lightweight, open-source clinical trial data visualization & management tool.*

[English](#english) | [中文](#中文)

---

</div>

<a name="中文"></a>
## 中文介绍

ClinicalTrialWatch 是为临床试验研究人员打造的数据看板系统，提供从患者入组到疗效评估的全流程数据可视化管理。

### 核心功能

| 模块 | 说明 |
|------|------|
| 📅 日历视图 | 甘特图形式展示患者用药、疗效评估、AE、PK 等事件时间轴 |
| 🏊 泳道图 | 以患者为行、时间为轴，直观展示研究状态与治疗用药条形图 |
| 📉 瀑布图 | RECIST 1.1 最佳疗效百分比变化可视化 |
| 🕷️ 蜘蛛图 | 肿瘤靶病灶 SOD 随时间变化的趋势追踪 |
| 🔬 肿瘤指标 | CEA / CA125 / CA199 等肿瘤标志物趋势图 |
| ⚙️ 项目配置 | 剂量组、癌种类型、DLT 观察期等参数可界面化管理 |

### 技术栈

- **后端**：Python 3.13 + Flask + SQLite
- **前端**：原生 JS + ECharts 5
- **数据交换**：支持 Excel 导入 / 导出

### 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/highwindmx/ClinicalTrialWatch.git
cd ClinicalTrialWatch

# 2. 初始化环境（Windows 双击运行）
setup.bat

# 3. 启动服务
venv\Scripts\python app.py

# 4. 浏览器访问 http://localhost:5000
```

> macOS / Linux 用户请手动创建虚拟环境并安装依赖：
> ```bash
> python3 -m venv venv
> source venv/bin/activate
> pip install -r requirements.txt
> python app.py
> ```

### 项目结构

```
ClinicalTrialWatch/
├── app.py              # Flask 后端入口
├── database.py         # 数据库模型与查询
├── requirements.txt    # Python 依赖
├── setup.bat          # Windows 一键初始化
├── data/              # SQLite 数据库（不提交到仓库）
└── frontend/          # 前端静态文件
    ├── index.html
    ├── css/style.css
    └── js/
        ├── api.js       # API 封装
        ├── calendar.js  # 日历甘特图
        ├── charts.js    # ECharts 图表
        ├── slidepanel.js# 患者详情滑出面板
        └── config.js    # 项目配置
```

### 数据隐私

`data/` 目录已被 `.gitignore` 排除，**不会上传真实临床数据**。克隆仓库后需运行 `setup.bat` 重新初始化空数据库。

---

<br/>

<a name="english"></a>
## English

ClinicalTrialWatch is an open-source data dashboard for clinical trial researchers, providing full-process data visualization from patient enrollment to efficacy assessment.

### Features

| Module | Description |
|--------|-------------|
| 📅 Calendar View | Gantt-chart timeline of drug administration, tumor assessment, AE, PK events |
| 🏊 Swimmer Plot | Patient-level study status and treatment bar visualization |
| 📉 Waterfall Plot | RECIST 1.1 best overall response (% change) visualization |
| 🕷️ Spider Plot | Tumor target lesion SOD trend tracking over time |
| 🔬 Tumor Markers | CEA / CA125 / CA199 trend charts |
| ⚙️ Project Config | UI-managed dose groups, cancer types, DLT observation window |

### Tech Stack

- **Backend**: Python 3.13 + Flask + SQLite
- **Frontend**: Vanilla JS + ECharts 5
- **Data Exchange**: Excel import / export support

### Quick Start

```bash
# 1. Clone
git clone https://github.com/highwindmx/ClinicalTrialWatch.git
cd ClinicalTrialWatch

# 2. Initialize (Windows: double-click setup.bat)
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python -c "import database; database.init_db()"

# 3. Run
python app.py

# 4. Open http://localhost:5000
```

### Project Structure

```
ClinicalTrialWatch/
├── app.py              # Flask backend entry
├── database.py         # DB models & queries
├── requirements.txt    # Python dependencies
├── setup.bat          # Windows one-click setup
├── data/              # SQLite DB (excluded from repo)
└── frontend/          # Frontend static files
    ├── index.html
    ├── css/style.css
    └── js/
        ├── api.js
        ├── calendar.js
        ├── charts.js
        ├── slidepanel.js
        └── config.js
```

### Data Privacy

The `data/` directory is excluded by `.gitignore`. **No real clinical data is ever committed to the repository.** A fresh empty database is created when you run the setup script.

---

<div align="center">

### Acknowledgments / 致谢

**Made with ❤️ by [highwindmx](https://github.com/highwindmx)**

Special thanks to **WorkBuddy** 🐾 — the AI coding assistant that powered the entire development process, from debugging ECharts edge cases to writing this README. Couldn't have built this without you, buddy.

特别感谢 **WorkBuddy** 🐾 —— 全程参与开发的 AI 编程助手，从 ECharts 图表调试到这份 README 的撰写，整个项目都有它的身影。兄弟，没你真不行。

---

*ClinicalTrialWatch is for research and educational purposes only. Not for clinical decision making.* \
*本工具仅供研究与教学用途，不用于临床决策。*

</div>
