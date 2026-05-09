/**
 * 项目配置面板 - 剂量组管理 + 癌肿类型管理 + DLT观察期
 */

const ConfigPanel = {
    doseGroups: [],
    cancerTypes: [],
    currentProjectData: null,

    async load() {
        if (!Calendar.currentProject) return;
        // 三个 API 并行加载，显著缩短配置面板打开延迟
        const [doseGroups, cancerTypes, projectData] = await Promise.all([
            api.getDoseGroups(Calendar.currentProject),
            api.getCancerTypes(Calendar.currentProject),
            api.getProject(Calendar.currentProject).catch(e => { console.warn('加载项目信息失败', e); return null; })
        ]);
        this.doseGroups = doseGroups;
        this.cancerTypes = cancerTypes;
        this.currentProjectData = projectData;
        if (projectData) {
            const nameInput = document.getElementById('configProjName');
            if (nameInput) nameInput.value = projectData.name || '';
            const codeInput = document.getElementById('configProjCode');
            if (codeInput) codeInput.value = projectData.code || '';
            const dltInput = document.getElementById('dltDaysInput');
            if (dltInput) dltInput.value = projectData.dlt_days ?? 21;
        }
        this.renderDoseGroups();
        this.renderCancerTypes();
        this.bindEvents();
    },

    bindEvents() {
        // 避免重复绑定
        if (this._bound) return;
        this._bound = true;

        document.getElementById('addDoseGroupBtn').addEventListener('click', () => this.addDoseGroup());
        document.getElementById('addCancerTypeBtn').addEventListener('click', () => this.addCancerType());
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

    // ============ 剂量组 ============
    renderDoseGroups() {
        const body = document.getElementById('doseGroupBody');
        const len = this.doseGroups.length;
        if (len === 0) {
            body.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#6b7280;padding:20px">暂无剂量组，请添加</td></tr>';
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

    // ============ 删除项目 ============
    async deleteProject() {
        const proj = this.currentProjectData;
        const name = proj ? proj.name : '此项目';
        if (!confirm('⚠️ 确认删除项目「' + name + '」？\n\n将同时删除该项目下所有患者及临床数据，此操作不可恢复！')) return;
        // 二次确认
        if (!confirm('再次确认：删除项目「' + name + '」及所有关联数据？')) return;
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
            alert('删除项目失败: ' + (e.message || '未知错误'));
        }
    },

    esc: escapeHtml  // 统一使用 utils.js 中的全局函数
};

