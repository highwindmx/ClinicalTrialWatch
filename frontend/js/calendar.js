/**
 * 临床研究数据看板 - 主模块
 * SPA单页，6个Tab(日历/基线/瀑布/蜘蛛/肿瘤指标/项目配置)
 * 支持4级缩放(季/月/2周/周)，冻结患者列，月份合并行，泳道图，事件过滤
 */

const Calendar = {
    currentProject: null,
    colWidth: 24,          // 每列宽度(px)，可通过Ctrl+滚轮调节
    zoomLevels: [8, 24, 60],           // 3级离散缩放：小/中/大（2倍于原尺寸）
    zoomLevelIdx: 1,       // 当前缩放级别索引（默认"中"）
    refDate: new Date(),
    projects: [],
    patients: [],
    events: [],
    dateRange: null,
    sortBy: 'patient_id',
    sortOrder: 'asc',
    sortedPatients: [],
    currentTab: 'calendar',
    // 事件过滤状态
    eventFilters: {
        drug: true, assessment: true, ae: true, pk: true, status: true
    },

    // 颜色映射
    typeColors: {
        drug: { bg: '#378ADD', light: '#e8f2fd', label: '用药' },
        assessment: { bg: '#639922', light: '#edf5e0', label: '疗评' },
        ae: { bg: '#D85A30', light: '#fef0eb', label: 'AE' },
        pk: { bg: '#7F77DD', light: '#f0eeff', label: 'PK' },
        multi: { bg: '#BA7517', light: '#fef6e8', label: '多事件' }
    },
    aeGradeColors: { 1: '#fdba74', 2: '#fb923c', 3: '#f97316', 4: '#ea580c', 5: '#b91c1c' },
    assessColors: { CR: '#22c55e', PR: '#639922', SD: '#fbbf24', PD: '#D85A30', NE: '#9ca3af' },

    /** 初始化 */
    async init() {
        await this.loadProjects();
        this.bindEvents();
        const savedTab = localStorage.getItem('ct-active-tab');
        const validTabs = ['calendar', 'baseline', 'waterfall', 'swimmer', 'spider', 'tumorMarker', 'config'];
        const tabToRestore = (savedTab && validTabs.includes(savedTab)) ? savedTab : 'calendar';
        if (this.projects && this.projects.length > 0) {
            // 优先从 localStorage 恢复上次选中的项目
            const savedProjectId = localStorage.getItem('ct-current-project');
            const savedProject = this.projects.find(p => p.id === parseInt(savedProjectId));
            this.currentProject = savedProject ? savedProject.id : this.projects[0].id;
            document.getElementById('projectSelect').value = this.currentProject;
            await this.refresh();
            this.switchTab(tabToRestore);
        } else {
            this.showEmpty();
        }
        this.updateZoomUI();
    },

    /** 加载项目列表 */
    async loadProjects() {
        this.projects = await api.getProjects();
        this.renderProjectSelector();
    },

    /** 渲染项目下拉选择器 */
    renderProjectSelector() {
        const sel = document.getElementById('projectSelect');
        sel.innerHTML = this.projects.map(p =>
            '<option value="' + p.id + '">' + this.escapeHtml(p.name) + '</option>'
        ).join('');
        if (this.currentProject) sel.value = this.currentProject;
    },

    /** 绑定所有事件 */
    bindEvents() {
        // 项目切换
        document.getElementById('projectSelect').addEventListener('change', async (e) => {
            this.currentProject = parseInt(e.target.value);
            localStorage.setItem('ct-current-project', this.currentProject);  // 持久化当前项目
            await this.refresh();
            this.onTabSwitch(this.currentTab);
        });
        document.getElementById('projectAddBtn').addEventListener('click', () => this.showProjectModal());
        // projectEditBtn 已通过 onclick="Calendar.switchTab('config')" 直接处理

        // 主Tab切换
        document.querySelectorAll('.main-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                this.switchTab(tab.dataset.tab);
            });
        });

        // 日历导航
        document.getElementById('todayBtn').addEventListener('click', () => this.goToday());

        // 缩放
        document.getElementById('zoomInBtn').addEventListener('click', () => this.zoomIn());
        document.getElementById('zoomOutBtn').addEventListener('click', () => this.zoomOut());

        // 排序
        document.querySelectorAll('.sort-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const field = chip.dataset.sort;
                if (this.sortBy === field) {
                    this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
                } else {
                    this.sortBy = field;
                    this.sortOrder = 'asc';
                }
                document.querySelectorAll('.sort-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                this.renderCurrentView();
            });
        });

        // 导出导入
        document.getElementById('exportBtn').addEventListener('click', () => {
            if (this.currentProject) api.exportExcel(this.currentProject);
        });
        document.getElementById('importBtn').addEventListener('click', () => {
            document.getElementById('importFile').click();
        });
        document.getElementById('importFile').addEventListener('change', async (e) => {
            if (e.target.files[0] && this.currentProject) {
                try {
                    const result = await api.importExcel(this.currentProject, e.target.files[0]);
                    const imp = result.imported || {};
                    const total = Object.values(imp).reduce((a, b) => a + b, 0);
                    let msg = `导入完成:\n患者: ${imp.patients||0}  用药: ${imp.medications||0}  肿瘤评估: ${imp.assessments||0}\n不良事件: ${imp.aes||0}  PK数据: ${imp.pk||0}  肿瘤指标: ${imp.markers||0}`;
                    if (result.errors && result.errors.length > 0) {
                        msg += `\n\n⚠ 错误/跳过(${result.errors.length}条):\n` + result.errors.slice(0, 10).join('\n');
                        if (result.errors.length > 10) msg += `\n...等${result.errors.length}条`;
                    }
                    showToast(msg, 'success');
                    this.refresh();
                } catch (err) {
                    showError('导入失败: ' + (err.message || err));
                }
                // 重置 file input 以便重复选择同一文件
                e.target.value = '';
            }
        });

        // Ctrl+滚轮缩放
        document.getElementById('ganttContainer').addEventListener('wheel', (e) => {
            if (e.ctrlKey) {
                e.preventDefault();
                if (e.deltaY < 0) this.zoomIn(); else this.zoomOut();
            }
        }, { passive: false });

        // 事件过滤：平铺chips
        document.querySelectorAll('.filter-chip input[type=checkbox]').forEach(cb => {
            cb.addEventListener('change', () => {
                this.eventFilters[cb.dataset.filter] = cb.checked;
                this.renderCurrentView();
            });
        });

        // 窗口大小（防抖200ms，避免拖拽时密集重渲染）
        window.addEventListener('resize', debounce(() => this.renderCurrentView(), 200));
    },

    /** 切换主Tab */
    switchTab(tabName) {
        this.currentTab = tabName;
        localStorage.setItem('ct-active-tab', tabName);
        document.querySelectorAll('.main-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + tabName));
        this.onTabSwitch(tabName);
    },

    /** Tab切换时加载对应数据 */
    async onTabSwitch(tabName) {
        if (!this.currentProject) return;
        switch (tabName) {
            case 'calendar': this.renderCurrentView(); break;
            case 'baseline': await Charts.loadBaselineTable(); break;
            case 'waterfall': await Charts.loadWaterfall(); break;
            case 'swimmer': await Charts.loadSwimmer(); break;
            case 'spider': await Charts.loadSpider(); break;
            case 'tumorMarker': await Charts.loadTumorMarkerTrend(); break;
            case 'config': await ConfigPanel.load(); break;
        }
    },

    /** 刷新日历数据 - 完整时间轴 */
    async refresh() {
        if (!this.currentProject) return;
        const data = await api.getGanttFullData(this.currentProject);
        this.patients = data.patients || [];
        this.events = data.events || [];
        this.dateRange = data.date_range || {};
        this.doseColors = data.dose_colors || {};
        this.dltDays = (data.dlt_days != null) ? data.dlt_days : 21;
        this._buildEventIndex();
        this.renderCurrentView();
    },

    /** 构建事件索引：按 patient_id 分组，避免全量扫描 */
    _buildEventIndex() {
        this._eventIndex = {};
        for (const e of this.events) {
            const pid = e.patient_id;
            if (!this._eventIndex[pid]) this._eventIndex[pid] = [];
            this._eventIndex[pid].push(e);
        }
    },

    renderCurrentView() {
        this.renderGantt();
    },

    /** 缩放列宽 - 5级离散切换 */
    zoomIn() {
        if (this.zoomLevelIdx < this.zoomLevels.length - 1) {
            this.zoomLevelIdx++;
            this.colWidth = this.zoomLevels[this.zoomLevelIdx];
            this.updateZoomUI();
            this.renderGantt();
        }
    },
    zoomOut() {
        if (this.zoomLevelIdx > 0) {
            this.zoomLevelIdx--;
            this.colWidth = this.zoomLevels[this.zoomLevelIdx];
            this.updateZoomUI();
            this.renderGantt();
        }
    },
    updateZoomUI() {
        const labels = ['小', '中', '大'];
        document.getElementById('zoomLabel').textContent = labels[this.zoomLevelIdx] || '中';
        document.getElementById('zoomInBtn').disabled = this.zoomLevelIdx >= this.zoomLevels.length - 1;
        document.getElementById('zoomOutBtn').disabled = this.zoomLevelIdx <= 0;
    },

    /** 滚动到今天 - 居中显示 */
    goToday() {
        const now = new Date();
        const yy = now.getFullYear(), mm = String(now.getMonth() + 1).padStart(2, '0'), dd = String(now.getDate()).padStart(2, '0');
        const today = yy + '-' + mm + '-' + dd;
        // 直接用 scrollToToday 逻辑，但需要重建 dateList
        if (!this.dateRange || !this.dateRange.start || !this.dateRange.days) return;
        const startParts = this.dateRange.start.split('-');
        const startDateObj = new Date(parseInt(startParts[0]), parseInt(startParts[1]) - 1, parseInt(startParts[2]));
        const dateList = [];
        for (let i = 0; i < this.dateRange.days; i++) {
            const d = new Date(startDateObj); d.setDate(d.getDate() + i);
            const y = d.getFullYear(), mo = String(d.getMonth() + 1).padStart(2, '0'), day = String(d.getDate()).padStart(2, '0');
            dateList.push(y + '-' + mo + '-' + day);
        }
        this.scrollToToday(dateList, today);
    },

    /** 事件过滤：判断事件是否应显示 */
    isEventVisible(event) {
        const type = event.type;
        // 患者状态事件始终显示（在患者信息列）
        if (type === 'status') return true;
        return this.eventFilters[type] !== false;
    },

    /** 排序患者 */
    getSortedPatients() {
        let list = [...this.patients];
        list.sort((a, b) => {
            let va = a[this.sortBy] || '';
            let vb = b[this.sortBy] || '';
            if (typeof va === 'string') va = va.toLowerCase();
            if (typeof vb === 'string') vb = vb.toLowerCase();
            if (va < vb) return this.sortOrder === 'asc' ? -1 : 1;
            if (va > vb) return this.sortOrder === 'asc' ? 1 : -1;
            return 0;
        });
        this.sortedPatients = list;
        return list;
    },

    getEventsForDay(patientId, dateStr) {
        // 使用患者索引，仅扫描该患者事件，避免 O(n) 全量扫描
        const patientEvents = this._eventIndex[patientId] || [];
        return patientEvents.filter(e => {
            if (e.type === 'ae' && e.end_date) {
                return dateStr >= e.date && dateStr <= e.end_date;
            }
            return e.date === dateStr;
        }).filter(e => this.isEventVisible(e));
    },

    /** ============= 甘特图渲染 - 完整时间轴 ============= */
    renderGantt() {
        const container = document.getElementById('ganttContainer');
        if (!this.dateRange || !this.dateRange.days) {
            container.innerHTML = '<div class="empty-state"><p>暂无数据</p></div>';
            return;
        }

        const patients = this.getSortedPatients();
        const days = this.dateRange.days;
        const labels = this.dateRange.labels || [];
        const weekdays = this.dateRange.weekdays || [];
        const startDate = this.dateRange.start;
        const monthLabels = this.dateRange.month_labels || [];

        const dateList = [];
        const startParts = startDate.split('-');
        const startDateObj = new Date(parseInt(startParts[0]), parseInt(startParts[1]) - 1, parseInt(startParts[2]));
        for (let i = 0; i < days; i++) {
            const d = new Date(startDateObj); d.setDate(d.getDate() + i);
            // 用本地日期格式化，避免toISOString()的UTC时区偏移导致日期-1
            const yy = d.getFullYear(), mm = String(d.getMonth() + 1).padStart(2, '0'), dd = String(d.getDate()).padStart(2, '0');
            dateList.push(yy + '-' + mm + '-' + dd);
        }

        const today = new Date().toISOString().slice(0, 10);
        const todayIdx = dateList.indexOf(today);
        const cw = this.colWidth;  // 当前列宽
        const showWeekday = cw >= 60;  // 列宽>=60px时显示星期（原阈值30的2倍）
        const showLabel = cw >= 12;     // 列宽>=12px时显示日号（原阈值6的2倍）

        let html = '<div class="gantt-scroll-area">';

        html += '<table class="gantt-table">';
        html += '<colgroup><col style="width:120px;min-width:120px"></col>';
        for (let i = 0; i < days; i++) html += '<col style="width:' + cw + 'px;min-width:' + cw + 'px">';
        html += '</colgroup>';

        html += '<thead>';
        // 月份合并行
        if (monthLabels && monthLabels.length > 0) {
            html += '<tr class="month-header-row">';
            html += '<th class="col-fixed month-cell-fixed" style="width:120px;min-width:120px"></th>';
            monthLabels.forEach(m => {
                html += '<th class="month-cell" colspan="' + m.span + '">' + m.label + '</th>';
            });
            html += '</tr>';
        }
        // 日期行
        html += '<tr>';
        html += '<th class="col-fixed" style="min-width:120px"><span>患者信息</span> <button class="btn btn-primary enroll-btn" onclick="Calendar.showPatientModal()" title="新增患者">+ 入组</button></th>';
        for (let i = 0; i < days; i++) {
            const dateStr = dateList[i];
            const isToday = dateStr === today;
            const isWeekend = weekdays[i] === '六' || weekdays[i] === '日';
            let cls = 'col-day';
            if (isWeekend) cls += ' weekend';
            html += '<th class="' + cls + '" style="width:' + cw + 'px;max-width:' + cw + 'px;overflow:hidden"' + (isToday ? ' data-today="1"' : '') + '>';
            if (showLabel) html += '<div class="day-num">' + labels[i] + '</div>';
            if (showWeekday) html += '<div class="weekday">' + weekdays[i] + '</div>';
            // 今日：红色竖线覆盖
            if (isToday) html += '<div class="today-vline-header"></div>';
            html += '</th>';
        }
        html += '</tr>';
        html += '</thead>';

        html += '<tbody>';
        if (patients.length === 0) {
            html += '<tr><td colspan="' + (days + 1) + '" style="text-align:center;padding:40px;color:#6b7280;">暂无患者数据</td></tr>';
        }

        const dltDays = this.dltDays || 21;

        patients.forEach(p => {
            const subText = [p.dose_group, p.cancer_type].filter(Boolean).join(' / ') || '-';
            const doseColor = this.doseColors ? this.doseColors[p.dose_group] : '';
            // 获取该患者实际用药事件的首末日期（仅用actual_date）
            const patientDrugEvents = this.events.filter(e => e.patient_id === p.id && e.type === 'drug' && this.isEventVisible(e));
            let firstActualDrugIdx = -1, lastActualDrugIdx = -1;
            // 实际用药日期
            const actualDrugDates = patientDrugEvents.map(e => e.actual_date).filter(Boolean).sort();
            if (actualDrugDates.length > 0) {
                firstActualDrugIdx = dateList.indexOf(actualDrugDates[0]);
                lastActualDrugIdx = dateList.indexOf(actualDrugDates[actualDrugDates.length - 1]);
            }
            // 用药绿色填充终止日期：在组治疗中→今日；其他状态→末次实际用药
            const isInTreatment = !p.status || p.status === 'treatment';
            let drugFillEndIdx;
            if (isInTreatment) {
                drugFillEndIdx = todayIdx >= 0 ? todayIdx : lastActualDrugIdx;
            } else {
                drugFillEndIdx = lastActualDrugIdx;
            }
            // 事件日期（含计划）用于显示事件卡片
            let firstDrugIdx = -1, lastDrugIdx = -1;
            if (patientDrugEvents.length > 0) {
                const drugDates = patientDrugEvents.map(e => e.date).filter(Boolean).sort();
                if (drugDates.length > 0) {
                    firstDrugIdx = dateList.indexOf(drugDates[0]);
                    lastDrugIdx = dateList.indexOf(drugDates[drugDates.length - 1]);
                }
            }
            // DLT观察期：仅当该患者开启了DLT观察，且首次实际用药存在时
            const pDltObservation = (p.dlt_observation === undefined || p.dlt_observation === null) ? true : !!p.dlt_observation;
            const dltStart = (firstActualDrugIdx >= 0 && pDltObservation) ? firstActualDrugIdx : -1;
            const dltEnd = dltStart >= 0 ? dltStart + dltDays - 1 : -1;

            html += '<tr class="patient-row" data-patient-id="' + p.id + '" data-first-drug="' + firstActualDrugIdx + '" data-last-drug="' + drugFillEndIdx + '" data-dose-color="' + (doseColor || '#378ADD') + '">';
            html += '<td class="col-fixed">';
            if (doseColor) html += '<div class="dose-color-bar" style="background:' + doseColor + '"></div>';
            html += '<div class="patient-info" onclick="SlidePanel.open(' + p.id + ')">';
            html += '<div class="patient-meta"><div class="patient-id">' + (p.patient_id || '-') + this.statusIcon(p.status) + '</div><div class="patient-sub">' + subText + '</div></div>';
            html += '</div>';
            html += '<button class="patient-delete-btn" onclick="event.stopPropagation();Calendar.deletePatient(' + p.id + ')" title="删除">&times;</button>';
            html += '</td>';

            for (let i = 0; i < days; i++) {
                const dateStr = dateList[i];
                const isToday = dateStr === today;
                const isWeekend = weekdays[i] === '六' || weekdays[i] === '日';
                const isDLT = dltStart >= 0 && i >= dltStart && i <= dltEnd;
                const isDrugPeriod = firstActualDrugIdx >= 0 && drugFillEndIdx >= 0 && i >= firstActualDrugIdx && i <= drugFillEndIdx;
                const events = this.getEventsForDay(p.id, dateStr);
                let cls = 'day-cell';
                if (isWeekend) cls += ' weekend-col';
                // DLT红色优先于用药绿色
                if (isDLT) cls += ' dlt-period';
                else if (isDrugPeriod) cls += ' drug-period';
                let cellStyle = 'width:' + cw + 'px;max-width:' + cw + 'px;overflow:hidden;';
                if (isToday) cellStyle += 'position:relative;';
                html += '<td class="' + cls + '" style="' + cellStyle + '" onclick="SlidePanel.open(' + p.id + ')">';
                if (events.length > 0) {
                    if (cw < 60) {
                        // 窄列：只显示色点
                        if (events.length <= 3) {
                            html += '<div class="event-dots-row">';
                            events.forEach(e => {
                                html += '<span class="event-dot" style="background:' + this.getEventColor(e) + '" title="' + this.escapeHtml(e.label) + '"></span>';
                            });
                            html += '</div>';
                        } else {
                            html += '<div class="event-dots-row">';
                            html += '<span class="event-dot" style="background:' + this.typeColors.multi.bg + '"></span>';
                            html += '</div>';
                        }
                    } else {
                        // 宽列：显示事件卡片
                        events.forEach(e => {
                            html += '<div class="event-card ' + e.type + '" title="' + this.escapeHtml(e.detail || e.label) + '">' + this.escapeHtml(e.label) + '</div>';
                        });
                    }
                }
                // 今日：红色竖线
                if (isToday) html += '<div class="today-vline"></div>';
                html += '</td>';
            }
            html += '</tr>';
        });
        html += '</tbody></table></div>';

        container.innerHTML = html;

        this.setupHoverPanels(patients);
        this.scrollToToday(dateList, today);
    },

    getEventColor(event) {
        if (event.type === 'ae' && event.grade) return this.aeGradeColors[event.grade] || this.typeColors.ae.bg;
        if (event.type === 'assessment') {
            for (const key of ['CR', 'PR', 'SD', 'PD', 'NE']) {
                if (event.label && event.label.includes(key)) return this.assessColors[key];
            }
        }
        return this.typeColors[event.type]?.bg || '#999';
    },

    /** 患者状态图标 */
    statusIcon(s) {
        const icons = {
            treatment:  '<span title="在组治疗中" style="color:#374151;font-size:10px;margin-left:3px">▶</span>',
            followup:   '<span title="结束治疗随访中" style="color:#374151;font-size:10px;margin-left:3px">●</span>',
            off_study:  '<span title="死亡/失访" style="color:#374151;font-size:10px;margin-left:3px">×</span>'
        };
        return icons[s] || '';
    },

    setupHoverPanels(patients) {
        const container = document.getElementById('ganttContainer');
        let hoverEl = document.getElementById('globalHoverPanel');
        if (!hoverEl) {
            hoverEl = document.createElement('div');
            hoverEl.id = 'globalHoverPanel';
            hoverEl.className = 'hover-panel';
            document.body.appendChild(hoverEl);
        }
        // 移除旧监听
        container.onmouseover = (e) => {
            const row = e.target.closest('.patient-row');
            if (row) {
                const fixedCell = row.querySelector('.col-fixed');
                const onclickAttr = fixedCell?.querySelector('.patient-info')?.getAttribute('onclick');
                if (onclickAttr) {
                    const match = onclickAttr.match(/SlidePanel\.open\((\d+)\)/);
                    if (match) {
                        const pid = parseInt(match[1]);
                        const p = this.patients.find(pt => pt.id === pid);
                        if (p) this.showHoverPanel(hoverEl, p, fixedCell);
                    }
                }
            }
        };
        container.onmouseout = (e) => {
            const row = e.target.closest('.patient-row');
            if (row && !row.contains(e.relatedTarget)) hoverEl.style.display = 'none';
        };
    },

    showHoverPanel(hoverEl, patient, anchorEl) {
        const p = patient;
        const patientEvents = this.events.filter(e => e.patient_id === p.id);

        let html = '<h4>' + this.escapeHtml(p.patient_id || '-') + '</h4>';
        html += '<div class="info-row"><span>癌肿</span><span>' + this.escapeHtml(p.cancer_type || '-') + '</span></div>';
        html += '<div class="info-row"><span>ECOG</span><span>' + (p.ecog_score ?? '-') + '</span></div>';
        html += '<div class="info-row"><span>剂量组</span><span>' + this.escapeHtml(p.dose_group || '-') + '</span></div>';
        html += '<div class="info-row"><span>入组日期</span><span>' + this.escapeHtml(p.enroll_date || '-') + '</span></div>';
        html += '<div class="info-row"><span>状态</span><span>' + this.statusLabel(p.status) + '</span></div>';

        if (patientEvents.length > 0) {
            html += '<div class="event-list">';
            const showEvents = patientEvents.slice(0, 5);
            showEvents.forEach(e => {
                const color = this.getEventColor(e);
                const label = this.typeColors[e.type]?.label || '';
                html += '<div class="event-item"><span class="event-tag" style="background:' + color + '">' + label + '</span><span>' + this.escapeHtml(e.label) + ' ' + e.date + '</span></div>';
            });
            if (patientEvents.length > 5) html += '<div class="event-item" style="color:#6b7280">...还有' + (patientEvents.length - 5) + '个事件</div>';
            html += '</div>';
        }

        hoverEl.innerHTML = html;
        hoverEl.style.display = 'block';
        const rect = anchorEl.getBoundingClientRect();
        let left = rect.right + 8, top = rect.top;
        if (left + 280 > window.innerWidth) left = rect.left - 288;
        if (top + 300 > window.innerHeight) top = window.innerHeight - 310;
        if (top < 60) top = 60;
        hoverEl.style.left = left + 'px';
        hoverEl.style.top = top + 'px';
    },

    scrollToToday(dateList, today) {
        const todayIdx = dateList.indexOf(today);
        if (todayIdx < 0) return;
        // 多层 rAF：等待 DOM 变更（zoom/colWidth 切换后表格列宽生效）
        const cw = this.colWidth;
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                const scrollArea = document.querySelector('.gantt-scroll-area');
                if (scrollArea) {
                    const viewWidth = scrollArea.clientWidth;
                    // 今日列置于可视区正中央
                    scrollArea.scrollLeft = Math.max(0, todayIdx * cw + cw / 2 - viewWidth / 2);
                }
            });
        });
    },

    loadECharts() {
        // 优先复用 Charts 模块的加载逻辑（多CDN回退），避免重复加载
        if (typeof Charts !== 'undefined' && Charts.ensureECharts) {
            return Charts.ensureECharts();
        }
        return new Promise((resolve) => {
            if (window.echarts) { resolve(); return; }
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js';
            script.onload = () => resolve();
            document.head.appendChild(script);
        });
    },

    statusLabel(s) {
        const map = { treatment: '在组治疗中', followup: '结束治疗随访中', off_study: '死亡/失访' };
        return map[s] || s || '-';
    },

    async deletePatient(pid) {
        const p = this.patients.find(pt => pt.id === pid);
        const name = p ? p.patient_id : '';
        if (!confirm('确认删除患者 ' + name + '？此操作不可恢复！')) return;
        await api.deletePatient(pid);
        await this.refresh();
    },

    showEmpty() {
        document.getElementById('ganttContainer').innerHTML = '<div class="empty-state"><h3>还没有项目</h3><p>点击"+"创建你的第一个临床研究项目</p><button class="btn btn-primary" onclick="Calendar.showProjectModal()">新增项目</button></div>';
    },

    showProjectModal(project) {
        const isEdit = !!project;
        const p = project || { name: '', code: '', description: '' };
        document.getElementById('projectModalTitle').textContent = isEdit ? '编辑项目' : '新增项目';
        document.getElementById('projName').value = p.name || '';
        document.getElementById('projCode').value = p.code || '';
        document.getElementById('projDesc').value = p.description || '';
        document.getElementById('projectModal').dataset.editId = isEdit ? project.id : '';
        // Demo按钮仅在新建模式显示
        document.getElementById('demoDataBtn').style.display = isEdit ? 'none' : 'inline-flex';
        document.getElementById('projectModal').classList.remove('hidden');
    },

    async saveProject() {
        const btn = document.querySelector('#projectModal .modal-footer .btn-primary');
        await withBtnLoading(btn, async () => {
            const data = { name: document.getElementById('projName').value, code: document.getElementById('projCode').value, description: document.getElementById('projDesc').value };
            const editId = document.getElementById('projectModal').dataset.editId;
            if (editId) await api.updateProject(parseInt(editId), data);
            else await api.createProject(data);
            document.getElementById('projectModal').classList.add('hidden');
            await this.loadProjects();
            if (!this.currentProject && this.projects.length > 0) this.currentProject = this.projects[0].id;
            await this.refresh();
        }, '保存中...');
    },

    async saveProjectWithDemo() {
        const name = document.getElementById('projName').value.trim();
        if (!name) { showWarning('请先填写项目名称'); return; }
        const btn = document.getElementById('demoDataBtn');
        await withBtnLoading(btn, async () => {
            const data = { name: name, code: document.getElementById('projCode').value, description: document.getElementById('projDesc').value };
            // 1. 创建项目
            const result = await api.createProject(data);
            const newProjectId = result.id;
            if (!newProjectId) { showError('创建项目失败'); return; }
            // 2. 生成Demo数据
            try {
                const demoResult = await api.generateDemoData(newProjectId);
                if (demoResult.ok) {
                    document.getElementById('projectModal').classList.add('hidden');
                    this.currentProject = newProjectId;
                    await this.loadProjects();
                    await this.refresh();
                    const s = demoResult.stats;
                    alert(`Demo数据已生成！\n剂量组: ${s.dose_groups}个 | 癌肿类型: ${s.cancer_types}个 | 患者: ${s.patients}例`);
                } else {
                    alert('生成Demo数据失败: ' + (demoResult.error || '未知错误'));
                }
            } catch (e) {
                alert('生成Demo数据失败: ' + (e.error || e.message || '未知错误'));
            }
        }, '生成中...');
    },

    showPatientModal() {
        if (!this.currentProject) { alert('请先选择一个项目'); return; }
        document.getElementById('patientModal').classList.remove('hidden');
        ['ptId','ptAge','ptEnroll'].forEach(id => document.getElementById(id).value = '');
        document.getElementById('ptSex').value = '';
        document.getElementById('ptEcog').value = '';
        document.getElementById('ptCancer').value = '';
        document.getElementById('ptGroup').value = '';
        // 动态加载癌肿类型和剂量组选项
        this._loadPatientFormOptions();
    },

    async _loadPatientFormOptions() {
        try {
            const cancerTypes = await api.getCancerTypes(this.currentProject);
            const doseGroups = await api.getDoseGroups(this.currentProject);
            const ctSel = document.getElementById('ptCancer');
            const dgSel = document.getElementById('ptGroup');
            ctSel.innerHTML = '<option value="">--</option>' + cancerTypes.map(ct => `<option value="${ct.id}">${ct.name}</option>`).join('');
            dgSel.innerHTML = '<option value="">--</option>' + doseGroups.map(dg => `<option value="${dg.id}">${dg.name}</option>`).join('');
        } catch(e) {
            console.error('加载表单选项失败:', e);
        }
    },

    async savePatient() {
        const btn = document.querySelector('#patientModal .modal-footer .btn-primary');
        await withBtnLoading(btn, async () => {
            const cancerSel = document.getElementById('ptCancer');
            const groupSel = document.getElementById('ptGroup');
            const data = {
                project_id: this.currentProject,
                patient_id: document.getElementById('ptId').value,
                age: document.getElementById('ptAge').value || null,
                sex: document.getElementById('ptSex').value || null,
                cancer_type_id: cancerSel.value || null,
                ecog_score: document.getElementById('ptEcog').value || null,
                dose_group_id: groupSel.value || null,
                enroll_date: document.getElementById('ptEnroll').value || null
            };
            await api.createPatient(data);
            document.getElementById('patientModal').classList.add('hidden');
            await this.refresh();
        }, '保存中...');
    },

    closeModal(id) { document.getElementById(id).classList.add('hidden'); },

    escapeHtml: escapeHtml  // 统一使用 utils.js 中的全局函数
};

document.addEventListener('DOMContentLoaded', () => {
    Calendar.init();
    Calendar.updateZoomUI();
});

// 显式暴露到全局作用域，确保其他脚本可访问
window.Calendar = Calendar;
