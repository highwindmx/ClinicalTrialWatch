/**
 * 项目配置面板 - 剂量组管理 + 癌肿类型管理 + DLT观察期
 */

const ConfigPanel = {
    doseGroups: [],
    cancerTypes: [],
    currentProjectData: null,

    async load() {
        if (!Calendar.currentProject) return;
        // 五个 API 并行加载，显著缩短配置面板打开延迟
        const [doseGroups, cancerTypes, projectData, syncCfg, ocrInfo] = await Promise.all([
            api.getDoseGroups(Calendar.currentProject),
            api.getCancerTypes(Calendar.currentProject),
            api.getProject(Calendar.currentProject).catch(e => { console.warn('加载项目信息失败', e); return null; }),
            api.getEnrollmentSync(Calendar.currentProject).catch(e => { console.warn('加载入组同步配置失败', e); return null; }),
            api.getOcrVisits(Calendar.currentProject).catch(e => { console.warn('加载OCR访视信息失败', e); return null; })
        ]);
        this.doseGroups = doseGroups;
        this.cancerTypes = cancerTypes;
        this.currentProjectData = projectData;
        this.enrollSyncConfig = syncCfg;
        if (projectData) {
            const nameInput = document.getElementById('configProjName');
            if (nameInput) nameInput.value = projectData.name || '';
            const codeInput = document.getElementById('configProjCode');
            if (codeInput) codeInput.value = projectData.code || '';
            const drugInput = document.getElementById('configDefaultDrug');
            if (drugInput) drugInput.value = projectData.default_drug_name || '';
            const dltInput = document.getElementById('dltDaysInput');
            if (dltInput) dltInput.value = projectData.dlt_days ?? 21;
            const calcBaseSelect = document.getElementById('assessmentCalcBase');
            if (calcBaseSelect) calcBaseSelect.value = projectData.assessment_calc_base || 'baseline';
            const ocrDirInput = document.getElementById('ocrDirInput');
            if (ocrDirInput) ocrDirInput.value = projectData.ocr_dir || '';
        }
        this.renderDoseGroups();
        this.renderCancerTypes();
        this.renderEnrollSync();
        this.renderOcrDir(ocrInfo);
        this.bindEvents();
    },

    bindEvents() {
        // 避免重复绑定
        if (this._bound) return;
        this._bound = true;

        document.getElementById('addDoseGroupBtn').addEventListener('click', () => this.addDoseGroup());
        document.getElementById('addCancerTypeBtn').addEventListener('click', () => this.addCancerType());
        document.getElementById('enrollSaveBtn').addEventListener('click', () => this.saveEnrollmentConfig());
        document.getElementById('enrollDryRunBtn').addEventListener('click', () => this.scanEnrollment(true));
    },

    // ============ 项目基本信息 ============
    async saveProjectName(value) {
        await api.updateProject(Calendar.currentProject, { name: value });
        // 同步更新项目下拉选择器
        await Calendar.loadProjects();
    },
    async saveProjectCode(value) {
        await api.updateProject(Calendar.currentProject, { code: value });
    },
    async saveDefaultDrugName(value) {
        await api.updateProject(Calendar.currentProject, { default_drug_name: value.trim() || null });
    },

    // ============ minerUOCR 资料目录（只读标记） ============
    async saveOcrDir(value) {
        const dir = (value || '').trim();
        const status = document.getElementById('ocrDirStatus');
        try {
            await api.updateProject(Calendar.currentProject, { ocr_dir: dir || null });
            const info = await api.getOcrVisits(Calendar.currentProject);
            this.renderOcrDir(info);
            await Calendar.refresh();
        } catch (e) {
            if (status) {
                status.textContent = '保存失败：' + this.esc(e.message || '未知错误');
                status.style.color = '#dc2626';
            }
        }
    },
    renderOcrDir(info) {
        const status = document.getElementById('ocrDirStatus');
        if (!status) return;
        if (!info || !info.configured) {
            status.textContent = '未配置：填写 minerUOCR 参与者目录后，日历自动显示访视标记（只读，不修改资料）';
            status.style.color = '#6b7280';
            return;
        }
        const unmatched = (info.unmatched || []).length;
        status.textContent = '已扫描 ' + info.total_dirs + ' 个目录，其中 ' + info.dated_dirs +
            ' 个有访视日期；匹配本项目 ' + Object.keys(info.mapped || {}).length +
            ' 例，未匹配 ' + unmatched + ' 个（预筛/缩写目录，已忽略）';
        status.style.color = '#6b7280';
    },

    // ============ DLT观察期 ============
    async saveDLTDays() {
        const input = document.getElementById('dltDaysInput');
        const days = parseInt(input.value);
        if (isNaN(days) || days < 1) { alert('请输入有效天数（正整数）'); return; }
        await api.updateProject(Calendar.currentProject, { dlt_days: days });
        // 更新本地缓存
        Calendar.dltDays = days;
        // 提示
        const msg = document.getElementById('dltSaveMsg');
        if (msg) { msg.style.display = 'inline'; setTimeout(() => msg.style.display = 'none', 2000); }
        // 刷新日历
        Calendar.refresh();
    },

    // ============ 预计下次影像计算方式 ============
    async saveAssessmentCalcBase(value) {
        await api.updateProject(Calendar.currentProject, { assessment_calc_base: value });
        // 提示
        const msg = document.getElementById('calcBaseSaveMsg');
        if (msg) { msg.style.display = 'inline'; setTimeout(() => msg.style.display = 'none', 2000); }
        // 刷新日历
        Calendar.refresh();
    },

    // ============ 剂量组 ============
    renderDoseGroups() {
        const body = document.getElementById('doseGroupBody');
        if (!body) { console.warn('renderDoseGroups: doseGroupBody not found in DOM'); return; }
        const len = this.doseGroups.length;
        if (len === 0) {
            body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#6b7280;padding:20px">暂无剂量组，请添加</td></tr>';
            return;
        }
        body.innerHTML = this.doseGroups.map((dg, i) => {
            let arrows = '';
            if (i > 0) {
                arrows += '<button class="sort-arrow-btn" onclick="ConfigPanel.moveDoseGroup(' + dg.id + ',-1)" title="上移">▲</button>';
            } else {
                arrows += '<span class="sort-arrow-placeholder"></span>';
            }
            if (i < len - 1) {
                arrows += '<button class="sort-arrow-btn" onclick="ConfigPanel.moveDoseGroup(' + dg.id + ',1)" title="下移">▼</button>';
            } else {
                arrows += '<span class="sort-arrow-placeholder"></span>';
            }
            return '<tr>' +
                '<td><input class="inline-edit" value="' + this.esc(dg.name) + '" onchange="ConfigPanel.updateDoseGroup(' + dg.id + ',\'name\',this.value)"></td>' +
                '<td><input type="color" value="' + (dg.color || '#378ADD') + '" onchange="ConfigPanel.updateDoseGroup(' + dg.id + ',\'color\',this.value)" style="width:36px;height:24px;border:1px solid #ddd;border-radius:3px;cursor:pointer"></td>' +
                '<td><input type="number" value="' + (dg.medication_interval ?? '') + '" placeholder="天" min="1" max="365" style="width:60px;font-size:12px;padding:2px 4px;border:1px solid #d1d5db;border-radius:4px" onchange="ConfigPanel.updateDoseGroup(' + dg.id + ',\'medication_interval\',this.value?parseInt(this.value):null)"></td>' +
                '<td><input type="number" value="' + (dg.assessment_interval ?? '') + '" placeholder="天" min="7" max="365" style="width:60px;font-size:12px;padding:2px 4px;border:1px solid #d1d5db;border-radius:4px" onchange="ConfigPanel.updateDoseGroup(' + dg.id + ',\'assessment_interval\',this.value?parseInt(this.value):null)"></td>' +
                '<td class="sort-arrow-cell">' + arrows + '</td>' +
                '<td><button class="btn btn-sm" onclick="ConfigPanel.deleteDoseGroup(' + dg.id + ')" style="color:#D85A30">删除</button></td>' +
                '</tr>';
        }).join('');
    },
    async moveDoseGroup(id, direction) {
        const arr = this.doseGroups;
        const idx = arr.findIndex(d => d.id === id);
        if (idx < 0) return;
        const swapIdx = idx + direction;
        if (swapIdx < 0 || swapIdx >= arr.length) return;
        // 本地交换
        [arr[idx], arr[swapIdx]] = [arr[swapIdx], arr[idx]];
        // 重新赋 sort_order 并渲染
        arr.forEach((d, i) => d.sort_order = i);
        this.renderDoseGroups();
        // 持久化
        try {
            await Promise.all([
                api.updateDoseGroup(arr[idx].id, { sort_order: arr[idx].sort_order }),
                api.updateDoseGroup(arr[swapIdx].id, { sort_order: arr[swapIdx].sort_order })
            ]);
        } catch (e) {
            this.doseGroups = await api.getDoseGroups(Calendar.currentProject);
            this.renderDoseGroups();
        }
    },
    async addDoseGroup() {
        await api.createDoseGroup(Calendar.currentProject, { name: '新剂量组', color: '#378ADD', sort_order: this.doseGroups.length });
        this.doseGroups = await api.getDoseGroups(Calendar.currentProject);
        this.renderDoseGroups();
    },
    async updateDoseGroup(id, field, value) {
        await api.updateDoseGroup(id, { [field]: field === 'sort_order' ? parseInt(value) : value });
        const item = this.doseGroups.find(d => d.id === id);
        if (item) item[field] = field === 'sort_order' ? parseInt(value) : value;
    },
    async deleteDoseGroup(id) {
        if (!confirm('确定删除此剂量组？')) return;
        await api.deleteDoseGroup(id);
        this.doseGroups = await api.getDoseGroups(Calendar.currentProject);
        this.renderDoseGroups();
    },

    // ============ 癌肿类型 ============
    renderCancerTypes() {
        const body = document.getElementById('cancerTypeBody');
        if (!body) { console.warn('renderCancerTypes: cancerTypeBody not found in DOM'); return; }
        const len = this.cancerTypes.length;
        if (len === 0) {
            body.innerHTML = '<tr><td colspan="3" style="text-align:center;color:#6b7280;padding:20px">暂无癌肿类型，请添加</td></tr>';
            return;
        }
        body.innerHTML = this.cancerTypes.map((ct, i) => {
            let arrows = '';
            if (i > 0) {
                arrows += '<button class="sort-arrow-btn" onclick="ConfigPanel.moveCancerType(' + ct.id + ',-1)" title="上移">▲</button>';
            } else {
                arrows += '<span class="sort-arrow-placeholder"></span>';
            }
            if (i < len - 1) {
                arrows += '<button class="sort-arrow-btn" onclick="ConfigPanel.moveCancerType(' + ct.id + ',1)" title="下移">▼</button>';
            } else {
                arrows += '<span class="sort-arrow-placeholder"></span>';
            }
            return '<tr>' +
                '<td><input class="inline-edit" value="' + this.esc(ct.name) + '" onchange="ConfigPanel.updateCancerType(' + ct.id + ',\'name\',this.value)"></td>' +
                '<td class="sort-arrow-cell">' + arrows + '</td>' +
                '<td><button class="btn btn-sm" onclick="ConfigPanel.deleteCancerType(' + ct.id + ')" style="color:#D85A30">删除</button></td>' +
                '</tr>';
        }).join('');
    },
    async moveCancerType(id, direction) {
        const arr = this.cancerTypes;
        const idx = arr.findIndex(c => c.id === id);
        if (idx < 0) return;
        const swapIdx = idx + direction;
        if (swapIdx < 0 || swapIdx >= arr.length) return;
        [arr[idx], arr[swapIdx]] = [arr[swapIdx], arr[idx]];
        arr.forEach((d, i) => d.sort_order = i);
        this.renderCancerTypes();
        try {
            await Promise.all([
                api.updateCancerType(arr[idx].id, { sort_order: arr[idx].sort_order }),
                api.updateCancerType(arr[swapIdx].id, { sort_order: arr[swapIdx].sort_order })
            ]);
        } catch (e) {
            this.cancerTypes = await api.getCancerTypes(Calendar.currentProject);
            this.renderCancerTypes();
        }
    },
    async addCancerType() {
        await api.createCancerType(Calendar.currentProject, { name: '新癌肿类型', sort_order: this.cancerTypes.length });
        this.cancerTypes = await api.getCancerTypes(Calendar.currentProject);
        this.renderCancerTypes();
    },
    async updateCancerType(id, field, value) {
        await api.updateCancerType(id, { [field]: field === 'sort_order' ? parseInt(value) : value });
        const item = this.cancerTypes.find(c => c.id === id);
        if (item) item[field] = field === 'sort_order' ? parseInt(value) : value;
    },
    async deleteCancerType(id) {
        if (!confirm('确定删除此癌肿类型？')) return;
        await api.deleteCancerType(id);
        this.cancerTypes = await api.getCancerTypes(Calendar.currentProject);
        this.renderCancerTypes();
    },

    // ============ 入组表自动同步 ============
    renderEnrollSync() {
        const cfg = this.enrollSyncConfig;
        if (!cfg) return;
        const pathInput = document.getElementById('enrollXlsxPath');
        const sheetInput = document.getElementById('enrollSheetName');
        const enabledInput = document.getElementById('enrollWatchEnabled');
        const status = document.getElementById('enrollSyncStatus');
        const preview = document.getElementById('enrollSyncPreview');
        if (pathInput) pathInput.value = cfg.xlsx_path || '';
        if (sheetInput) sheetInput.value = cfg.sheet_name || '入组';
        if (enabledInput) enabledInput.checked = !!cfg.enabled;

        if (status) {
            if (cfg.last_scan_at && cfg.last_result) {
                const r = cfg.last_result;
                const createdNames = r.created_screenings || [];
                status.innerHTML = '上次扫描：' + this.esc(cfg.last_scan_at) +
                    ' ｜ 新增参与者 ' + (r.created || 0) +
                    (createdNames.length ? '（' + this.esc(createdNames.join('、')) + '）' : '') +
                    ' ｜ EOT ' + (r.eot_updated || 0) +
                    ' ｜ C1D1 ' + (r.medications || 0) +
                    ' ｜ 基线肿评 ' + (r.assessments || 0) +
                    ' ｜ 错误 ' + ((r.errors || []).length) +
                    ((r.warnings || []).length ? ' ｜ 提示：' + this.esc(r.warnings.join('；')) : '');
                status.style.color = (r.errors || []).length ? '#dc2626' : '#6b7280';
            } else {
                status.textContent = '尚未扫描。启动时不自动扫描；保存配置后监听文件变化，或点日历页「扫描入组表」。';
                status.style.color = '#6b7280';
            }
        }
        if (preview) {
            if (cfg.preview_error) {
                preview.textContent = '预览失败：' + cfg.preview_error;
                preview.style.color = '#dc2626';
            } else if (cfg.preview) {
                const cols = Object.keys(cfg.preview.columns || {});
                preview.textContent = '识别到 ' + cfg.preview.row_count + ' 条有效记录；已识别列：' +
                    (cols.length ? cols.join('、') : '无');
                preview.style.color = '#6b7280';
            } else {
                preview.textContent = '';
            }
        }
    },

    async saveEnrollmentConfig() {
        const path = (document.getElementById('enrollXlsxPath').value || '').trim();
        const sheet = (document.getElementById('enrollSheetName').value || '').trim() || '入组';
        const enabled = !!document.getElementById('enrollWatchEnabled').checked;
        const status = document.getElementById('enrollSyncStatus');
        try {
            await api.saveEnrollmentSync(Calendar.currentProject, {
                xlsx_path: path, sheet_name: sheet, enabled: enabled
            });
            status.textContent = '配置已保存' + (enabled ? '，监听已生效' : '，监听已关闭');
            status.style.color = '#16a34a';
            this.enrollSyncConfig = await api.getEnrollmentSync(Calendar.currentProject);
            this.renderEnrollSync();
            status.textContent = '配置已保存' + (enabled ? '，监听已生效' : '，监听已关闭');
            status.style.color = '#16a34a';
        } catch (e) {
            status.textContent = '保存失败：' + (e.message || '未知错误');
            status.style.color = '#dc2626';
        }
    },

    async scanEnrollment(dryRun) {
        const btn = document.getElementById(dryRun ? 'enrollDryRunBtn' : 'enrollScanBtn');
        const status = document.getElementById('enrollSyncStatus');
        const original = btn ? btn.textContent : '';
        if (btn) { btn.disabled = true; btn.textContent = '扫描中…'; }
        status.textContent = '正在读取入组表…';
        status.style.color = '#6b7280';
        try {
            const r = await api.scanEnrollment(Calendar.currentProject, { dry_run: !!dryRun });
            const prefix = dryRun ? '【试扫】' : '';
            const names = dryRun ? (r.would_create_screenings || []) : (r.created_screenings || []);
            const createdLabel = dryRun ? '预计新增 ' + (r.would_create || 0) : '新增参与者 ' + r.created;
            status.textContent = prefix + '有效记录 ' + r.rows + ' 条；' + createdLabel +
                (names.length ? '（' + names.join('、') + '）' : '') +
                ' ｜ EOT ' + (dryRun ? r.eot_rows + ' 条待回填' : r.eot_updated) +
                ' ｜ C1D1 ' + r.medications + ' ｜ 基线肿评 ' + r.assessments +
                ' ｜ 库中已存在 ' + r.existing +
                (r.skipped ? ' ｜ ' + r.reason : '') +
                (r.warnings && r.warnings.length ? ' ｜ 提示：' + r.warnings.join('；') : '') +
                (r.errors && r.errors.length ? ' ｜ 错误：' + r.errors.join('；') : '');
            status.style.color = (r.errors && r.errors.length) ? '#dc2626' : '#16a34a';
            if (!dryRun) {
                this.enrollSyncConfig = await api.getEnrollmentSync(Calendar.currentProject);
                this.renderEnrollSync();
                status.style.color = (r.errors && r.errors.length) ? '#dc2626' : '#16a34a';
                await Calendar.refresh();
            }
        } catch (e) {
            status.textContent = '扫描失败：' + (e.message || '未知错误');
            status.style.color = '#dc2626';
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = original; }
        }
    },

    // ============ 删除项目 ============
    async deleteProject() {
        const proj = this.currentProjectData;
        const name = proj ? proj.name : '此项目';
        if (!confirm('⚠️ 确认删除项目「' + this.esc(name) + '」？\n\n将同时删除该项目下所有患者及临床数据，此操作不可恢复！')) return;
        // 二次确认
        if (!confirm('再次确认：删除项目「' + this.esc(name) + '」及所有关联数据？')) return;
        try {
            await api.deleteProject(Calendar.currentProject);
            Calendar.currentProject = null;
            // 切回日历Tab
            Calendar.switchTab('calendar');
            // 重新加载项目列表
            await Calendar.loadProjects();
            if (Calendar.projects && Calendar.projects.length > 0) {
                Calendar.currentProject = Calendar.projects[0].id;
                document.getElementById('projectSelect').value = Calendar.currentProject;
                await Calendar.refresh();
            } else {
                Calendar.showEmpty();
            }
        } catch(e) {
            alert('删除项目失败: ' + this.esc(e.message || '未知错误'));
        }
    },

    esc: escapeHtml  // 统一使用 utils.js 中的全局函数
};

