/**
 * 右侧滑出患者编辑面板
 * 520px宽，6个子Tab（基线/用药/疗评/AE/PK/指标）
 * 所有字段即时保存（onChange → API）
 */

const SlidePanel = {
    patientId: null,
    patient: null,
    medications: [],
    assessments: [],
    aes: [],
    pkData: [],
    markers: [],
    _cancerTypes: [],   // 缓存项目癌肿类型选项
    _doseGroups: [],    // 缓存项目剂量组选项

    // 状态映射：英文值 → 中文标签（全局统一为3种）
    statusOptions: [
        { value: 'treatment', label: '在组治疗中' },
        { value: 'followup', label: '结束治疗随访中' },
        { value: 'off_study', label: '死亡/失访' }
    ],

    /** 打开面板 */
    async open(pid) {
        this.patientId = pid;
        document.getElementById('slidePanel').classList.remove('hidden');
        document.getElementById('slidePanelOverlay').classList.remove('hidden');
        this.switchSubTab('baseline');
        await this.loadAll();
    },

    /** 关闭面板 */
    close() {
        document.getElementById('slidePanel').classList.add('hidden');
        document.getElementById('slidePanelOverlay').classList.add('hidden');
        if (Calendar.currentProject) Calendar.refresh();
    },

    /** 切换子Tab */
    switchSubTab(tabName) {
        document.querySelectorAll('.slide-tab').forEach(t => t.classList.toggle('active', t.dataset.stab === tabName));
        document.querySelectorAll('.slide-tab-content').forEach(c => c.classList.toggle('active', c.id === 'stab-' + tabName));
    },

    /** 加载所有数据（并行加载，显著提升编辑面板响应速度） */
    async loadAll() {
        this.patient = await api.getPatient(this.patientId);
        document.getElementById('slidePanelTitle').textContent = this.patient.patient_id || '';
        // 加载项目配置的癌肿类型和剂量组选项
        await this._loadConfigOptions();
        // 先渲染基线（不依赖子数据），再并行加载其余5个模块
        this.renderBaseline();
        const [medications, assessments, aes, pkData, markers] = await Promise.all([
            api.getMedications(this.patientId),
            api.getTumorAssessments(this.patientId),
            api.getAdverseEvents(this.patientId),
            api.getPkData(this.patientId),
            api.getTumorMarkers(this.patientId)
        ]);
        this.medications = medications;
        this.assessments = assessments;
        this.aes = aes;
        this.pkData = pkData;
        this.markers = markers;
        this.renderMedications();
        this.renderAssessments();
        this.renderAEs();
        this.renderPK();
        this.renderMarkers();
    },

    /** 加载项目配置选项 */
    async _loadConfigOptions() {
        try {
            const projectId = this.patient.project_id;
            if (projectId) {
                this._cancerTypes = await api.getCancerTypes(projectId);
                this._doseGroups = await api.getDoseGroups(projectId);
            }
        } catch(e) {
            console.error('加载配置选项失败:', e);
            this._cancerTypes = [];
            this._doseGroups = [];
        }
    },

    /** 即时保存提示 */
    _saveHint(el) {
        if (!el) return;
        const orig = el.style.borderColor;
        el.style.borderColor = '#22c55e';
        setTimeout(() => { el.style.borderColor = orig; }, 800);
    },

    // ============ 基线数据（即时保存，无姓名） ============
    renderBaseline() {
        const p = this.patient;
        const grid = document.getElementById('spBaseline');
        const fields = [
            { key: 'patient_id', label: '患者编号', value: p.patient_id, type: 'text' },
            { key: 'age', label: '年龄', value: p.age, type: 'number' },
            { key: 'sex', label: '性别', value: p.sex, type: 'select', options: ['男', '女'] },
            { key: 'cancer_type_id', label: '癌肿', value: p.cancer_type_id, type: 'config_select', options: this._cancerTypes },
            { key: 'ecog_score', label: 'ECOG评分', value: p.ecog_score, type: 'select', options: ['0','1','2','3','4'] },
            { key: 'dose_group_id', label: '剂量组', value: p.dose_group_id, type: 'config_select', options: this._doseGroups },
            { key: 'enroll_date', label: '入组日期', value: p.enroll_date, type: 'date' },
            { key: 'dlt_observation', label: '进行DLT观察？', value: p.dlt_observation, type: 'checkbox', checkboxLabel: '是' },
            { key: 'status', label: '状态', value: p.status, type: 'status_select' },
            { key: 'off_study_date', label: '出组日期', value: p.off_study_date, type: 'date' },
        ];
        grid.innerHTML = '<div class="sp-baseline-grid">' +
            fields.map(f => {
                let input;
                if (f.type === 'checkbox') {
                    const checked = f.value !== 0 && f.value !== '0' && f.value !== null && f.value !== undefined;
                    input = '<label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">' +
                        '<input type="checkbox" id="sp_' + f.key + '" ' + (checked ? 'checked' : '') +
                        ' onchange="SlidePanel.onBaselineChange(\'' + f.key + '\',this.checked?1:0,this)">' +
                        (f.checkboxLabel || '') + '</label>';
                } else if (f.type === 'status_select') {
                    // 状态：显示中文标签，存英文值
                    input = '<select id="sp_status" class="form-input" onchange="SlidePanel.onStatusChange(this)">' +
                        '<option value="">--</option>' +
                        this.statusOptions.map(o => '<option value="' + o.value + '" ' + (f.value === o.value ? 'selected' : '') + '>' + o.label + '</option>').join('') +
                        '</select>';
                } else if (f.type === 'config_select') {
                    // 从项目配置加载的下拉选项（value=ID, label=name）
                    input = '<select id="sp_' + f.key + '" class="form-input" onchange="SlidePanel.onBaselineChange(\'' + f.key + '\',this.value,this)">' +
                        '<option value="">--</option>' +
                        f.options.map(o => '<option value="' + o.id + '" ' + (String(f.value) === String(o.id) ? 'selected' : '') + '>' + o.name + '</option>').join('') +
                        '</select>';
                } else if (f.type === 'select') {
                    input = '<select id="sp_' + f.key + '" class="form-input" onchange="SlidePanel.onBaselineChange(\'' + f.key + '\',this.value,this)"><option value="">--</option>' +
                        f.options.map(o => '<option value="' + o + '" ' + (f.value == o ? 'selected' : '') + '>' + o + '</option>').join('') + '</select>';
                } else {
                    input = '<input type="' + f.type + '" id="sp_' + f.key + '" class="form-input" value="' + escapeHtml(f.value || '') + '" onchange="SlidePanel.onBaselineChange(\'' + f.key + '\',this.value,this)">';
                }
                const isOffStudyDate = f.key === 'off_study_date';
                const hiddenStyle = isOffStudyDate && p.status !== 'off_study' ? 'display:none' : '';
                return '<div class="sp-field" id="sp_field_' + f.key + '" style="' + hiddenStyle + '"><label>' + f.label + '</label>' + input + '</div>';
            }).join('') +
            '</div>' +
            '<div style="margin-top:8px;font-size:11px;color:#6b7280;text-align:right">✓ 修改即时保存</div>';
    },

    /** 状态变更时显示/隐藏出组日期 */
    onStatusChange(el) {
        this.onBaselineChange('status', el.value, el);
        const offStudyField = document.getElementById('sp_field_off_study_date');
        if (offStudyField) {
            offStudyField.style.display = el.value === 'off_study' ? '' : 'none';
        }
    },

    /** 基线字段即时保存 */
    async onBaselineChange(field, value, el) {
        // dlt_observation 为 0/false 时不应转换为 null
        const data = { [field]: (field === 'dlt_observation' ? (value ? 1 : 0) : (value || null)) };
        // 如果修改了 cancer_type_id 或 dose_group_id，后端会自动更新文本名称
        await api.updatePatient(this.patientId, data);
        this._saveHint(el);
        // 如果改了编号，更新面板标题
        if (field === 'patient_id') {
            document.getElementById('slidePanelTitle').textContent = value || '';
        }
        // 如果改了 cancer_type_id 或 dose_group_id，更新 patient 对象的文本缓存
        if (field === 'cancer_type_id' && value) {
            const ct = this._cancerTypes.find(c => String(c.id) === String(value));
            if (ct) this.patient.cancer_type = ct.name;
            this.patient.cancer_type_id = value;
        } else if (field === 'cancer_type_id' && !value) {
            this.patient.cancer_type = null;
            this.patient.cancer_type_id = null;
        }
        if (field === 'dose_group_id' && value) {
            const dg = this._doseGroups.find(d => String(d.id) === String(value));
            if (dg) this.patient.dose_group = dg.name;
            this.patient.dose_group_id = value;
        } else if (field === 'dose_group_id' && !value) {
            this.patient.dose_group = null;
            this.patient.dose_group_id = null;
        }
        // 更新本地缓存并刷新日历（用于 dlt_observation 和 status 变更）
        if (field === 'dlt_observation' || field === 'status') {
            this.patient[field] = field === 'dlt_observation' ? (value ? 1 : 0) : value;
            // 通知日历刷新（如果日历对象存在）
            if (typeof Calendar !== 'undefined' && Calendar.refresh) {
                Calendar.refresh();
            }
        }
    },

    // ============ 用药（周期改文字，剂量+单位合并） ============
    renderMedications() {
        const body = document.getElementById('spMedBody');
        body.innerHTML = this.medications.map(m => '<tr>' +
            '<td><input class="inline-edit" value="' + escapeHtml(m.drug_name||'') + '" onchange="SlidePanel.updateMed(' + m.id + ',\'drug_name\',this.value,this)"></td>' +
            '<td><input class="inline-edit" type="date" value="' + escapeHtml(m.planned_date||'') + '" onchange="SlidePanel.updateMed(' + m.id + ',\'planned_date\',this.value,this)"></td>' +
            '<td><input class="inline-edit" type="date" value="' + escapeHtml(m.actual_date||'') + '" onchange="SlidePanel.updateMed(' + m.id + ',\'actual_date\',this.value,this)"></td>' +
            '<td><input class="inline-edit" value="' + escapeHtml(m.dose||'') + '" onchange="SlidePanel.updateMedDose(' + m.id + ',this.value,this)" placeholder="如200mg" style="width:80px"></td>' +
            '<td><input class="inline-edit" value="' + escapeHtml(m.cycle||'') + '" onchange="SlidePanel.updateMed(' + m.id + ',\'cycle\',this.value,this)" placeholder="C1D1" style="width:60px"></td>' +
            '<td><button class="btn btn-sm" onclick="SlidePanel.deleteMed(' + m.id + ')" style="color:#D85A30">删</button></td>' +
            '</tr>').join('');
    },
    /** 剂量输入：解析"200mg"→dose=200, dose_unit=mg */
    async updateMedDose(id, rawValue, el) {
        const match = rawValue.match(/^([\d.]+)\s*(.*)$/);
        if (match) {
            await api.updateMedication(id, { dose: parseFloat(match[1]), dose_unit: match[2] || '' });
        } else {
            await api.updateMedication(id, { dose: rawValue, dose_unit: '' });
        }
        this._saveHint(el);
    },
    async addMedication() {
        await api.createMedication(this.patientId, { drug_name: '新药物' });
        this.medications = await api.getMedications(this.patientId);
        this.renderMedications();
    },
    async updateMed(id, field, value, el) {
        await api.updateMedication(id, { [field]: value });
        this._saveHint(el);
    },
    async deleteMed(id) {
        if (!confirm('确定删除此用药记录？')) return;
        await api.deleteMedication(id);
        this.medications = await api.getMedications(this.patientId);
        this.renderMedications();
    },

    // ============ 肿瘤评估（基线无最佳疗评，SOD基于基线计算，仅CR/PR可确认） ============
    renderAssessments() {
        const body = document.getElementById('spAssessBody');
        // 找到基线评估（最早的评估，用于SOD自动计算）
        const sorted = [...this.assessments].sort((a, b) => (a.eval_date || '').localeCompare(b.eval_date || ''));
        const baselineSod = sorted.length > 0 ? (parseFloat(sorted[0].target_sod) || 0) : 0;
        const baselineDate = sorted.length > 0 ? sorted[0].eval_date : '';
        const isBaseline = (a) => a.eval_date === baselineDate && this.assessments.length > 0;

        body.innerHTML = this.assessments.map(a => {
            const isBase = isBaseline(a);
            // 自动计算SOD变化
            const currentSod = parseFloat(a.target_sod) || 0;
            let sodPercent = '';
            if (isBase) {
                sodPercent = '0%';
            } else if (baselineSod > 0) {
                sodPercent = ((currentSod - baselineSod) / baselineSod * 100).toFixed(1) + '%';
            }

            // 基线行：最佳疗评和确认CR/PR均不可编辑
            const bestRespHtml = isBase
                ? '<span style="color:#aaa;font-size:11px">-</span>'
                : '<select class="inline-edit" onchange="SlidePanel.onAssessResponseChange(' + a.id + ',this.value,this)"><option value="">--</option>' +
                  ['CR','PR','SD','PD','NE'].map(r => '<option value="' + r + '" ' + (a.best_response===r?'selected':'') + '>' + r + '</option>').join('') +
                  '</select>';

            // 仅非基线+CR/PR时显示确认勾选
            const isCrPr = !isBase && (a.best_response === 'CR' || a.best_response === 'PR');
            const confirmCheckbox = isCrPr
                ? '<input class="inline-edit" type="checkbox" ' + (a.confirmed_crpr ? 'checked' : '') + ' onchange="SlidePanel.updateAssess(' + a.id + ',\'confirmed_crpr\',this.checked?1:0,this)">'
                : '<span style="color:#ccc">-</span>';

            return '<tr' + (isBase ? ' style="background:#f0f7ff"' : '') + '>' +
                '<td><input class="inline-edit" type="date" value="' + (a.eval_date||'') + '" onchange="SlidePanel.updateAssess(' + a.id + ',\'eval_date\',this.value,this)"></td>' +
                '<td>' + (isBase ?
                    '<span style="font-size:11px;color:#378ADD;font-weight:600">基线</span>' :
                    '<input class="inline-edit" value="' + (a.eval_type||'') + '" onchange="SlidePanel.updateAssess(' + a.id + ',\'eval_type\',this.value,this)" placeholder="V1/V2/..." style="width:50px">'
                ) + '</td>' +
                '<td><input class="inline-edit" type="number" step="0.1" value="' + (a.target_sod||'') + '" onchange="SlidePanel.updateAssess(' + a.id + ',\'target_sod\',this.value,this)" style="width:60px" placeholder="mm"></td>' +
                '<td style="font-size:11px;color:#378ADD;min-width:40px">' + sodPercent + '</td>' +
                '<td>' + bestRespHtml + '</td>' +
                '<td>' + confirmCheckbox + '</td>' +
                '<td><button class="btn btn-sm" onclick="SlidePanel.deleteAssess(' + a.id + ')" style="color:#D85A30">删</button></td>' +
                '</tr>';
        }).join('');
    },

    /** 疗评结果变化时：如果改为非CR/PR，自动清除confirmed_crpr */
    async onAssessResponseChange(id, value, el) {
        const data = { best_response: value };
        if (value !== 'CR' && value !== 'PR') {
            data.confirmed_crpr = 0;
        }
        await api.updateTumorAssessment(id, data);
        this._saveHint(el);
        // 重新渲染以更新确认勾选状态
        this.assessments = await api.getTumorAssessments(this.patientId);
        this.renderAssessments();
    },

    /** 更新疗评字段（target_sod/eval_date变化需重算SOD并保存） */
    async updateAssess(id, field, value, el) {
        const data = { [field]: value };

        // 如果修改了target_sod，自动计算sod_change
        if (field === 'target_sod') {
            const sorted = [...this.assessments].sort((a, b) => (a.eval_date || '').localeCompare(b.eval_date || ''));
            const baselineSod = parseFloat(sorted[0]?.target_sod) || 0;
            const currentSod = parseFloat(value) || 0;
            if (baselineSod > 0) {
                data.sod_change = parseFloat(((currentSod - baselineSod) / baselineSod * 100).toFixed(1));
            } else {
                data.sod_change = 0;
            }
        }

        await api.updateTumorAssessment(id, data);
        this._saveHint(el);
        // target_sod或eval_date变化需重新渲染（基线可能改变，SOD%需重算）
        if (field === 'target_sod' || field === 'eval_date') {
            this.assessments = await api.getTumorAssessments(this.patientId);
            this.renderAssessments();
        }
    },

    async addAssessment() {
        // 新增评估：如果还没有基线评估，标记为基线；否则自动标记V1/V2/V3
        const isFirst = this.assessments.length === 0;
        const defaultData = { eval_date: new Date().toISOString().slice(0, 10) };
        if (isFirst) {
            defaultData.eval_type = '基线';
            defaultData.sod_change = 0;
        } else {
            // 按日期排序，统计已有非基线评估数量来确定V编号
            const sorted = [...this.assessments].sort((a, b) => (a.eval_date || '').localeCompare(b.eval_date || ''));
            const nonBaselineCount = sorted.filter((a, i) => i > 0).length;
            defaultData.eval_type = 'V' + (nonBaselineCount + 1);
        }
        await api.createTumorAssessment(this.patientId, defaultData);
        this.assessments = await api.getTumorAssessments(this.patientId);
        this.renderAssessments();
    },

    async deleteAssess(id) {
        if (!confirm('确定删除此评估记录？')) return;
        await api.deleteTumorAssessment(id);
        this.assessments = await api.getTumorAssessments(this.patientId);
        this.renderAssessments();
    },

    // ============ 不良事件（AE关系5级标准） ============
    renderAEs() {
        const body = document.getElementById('spAeBody');
        body.innerHTML = this.aes.map(a => '<tr>' +
            '<td><input class="inline-edit" value="' + escapeHtml(a.ae_term||'') + '" onchange="SlidePanel.updateAE(' + a.id + ',\'ae_term\',this.value,this)"></td>' +
            '<td><input class="inline-edit" type="date" value="' + escapeHtml(a.onset_date||'') + '" onchange="SlidePanel.updateAE(' + a.id + ',\'onset_date\',this.value,this)"></td>' +
            '<td><input class="inline-edit" type="date" value="' + escapeHtml(a.end_date||'') + '" onchange="SlidePanel.updateAE(' + a.id + ',\'end_date\',this.value,this)"></td>' +
            '<td><select class="inline-edit" onchange="SlidePanel.updateAE(' + a.id + ',\'grade\',this.value,this)">' +
                [1,2,3,4,5].map(g => '<option value="' + g + '" ' + (a.grade==g?'selected':'') + '>' + g + '</option>').join('') +
            '</select></td>' +
            '<td><select class="inline-edit" onchange="SlidePanel.updateAE(' + a.id + ',\'outcome\',this.value)"><option value="">--</option>' +
                ['恢复','恢复伴后遗症','持续','死亡','未知'].map(o => '<option value="' + o + '" ' + (a.outcome===o?'selected':'') + '>' + o + '</option>').join('') +
            '</select></td>' +
            '<td><select class="inline-edit" onchange="SlidePanel.updateAE(' + a.id + ',\'drug_relation\',this.value,this)"><option value="">--</option>' +
                ['肯定有关','很可能有关','可能有关','可能无关','无关'].map(o => '<option value="' + o + '" ' + (a.drug_relation===o?'selected':'') + '>' + o + '</option>').join('') +
            '</select></td>' +
            '<td><button class="btn btn-sm" onclick="SlidePanel.deleteAE(' + a.id + ')" style="color:#D85A30">删</button></td>' +
            '</tr>').join('');
    },
    async addAE() {
        await api.createAdverseEvent(this.patientId, { ae_term: '新AE', onset_date: new Date().toISOString().slice(0,10), grade: 1 });
        this.aes = await api.getAdverseEvents(this.patientId);
        this.renderAEs();
    },
    async updateAE(id, field, value, el) {
        await api.updateAdverseEvent(id, { [field]: value });
        this._saveHint(el);
    },
    async deleteAE(id) {
        if (!confirm('确定删除此不良事件？')) return;
        await api.deleteAdverseEvent(id);
        this.aes = await api.getAdverseEvents(this.patientId);
        this.renderAEs();
    },

    // ============ PK数据（周期改文字） ============
    renderPK() {
        const body = document.getElementById('spPkBody');
        body.innerHTML = this.pkData.map(p => '<tr>' +
            '<td><input class="inline-edit" type="date" value="' + escapeHtml(p.sample_date||'') + '" onchange="SlidePanel.updatePK(' + p.id + ',\'sample_date\',this.value,this)"></td>' +
            '<td><input class="inline-edit" value="' + escapeHtml(p.time_point||'') + '" onchange="SlidePanel.updatePK(' + p.id + ',\'time_point\',this.value,this)"></td>' +
            '<td><input class="inline-edit" type="number" step="0.01" value="' + escapeHtml(p.concentration||'') + '" onchange="SlidePanel.updatePK(' + p.id + ',\'concentration\',this.value,this)" style="width:70px"></td>' +
            '<td><input class="inline-edit" value="' + escapeHtml(p.unit||'ng/mL') + '" onchange="SlidePanel.updatePK(' + p.id + ',\'unit\',this.value,this)" style="width:50px"></td>' +
            '<td><input class="inline-edit" value="' + escapeHtml(p.cycle||'') + '" onchange="SlidePanel.updatePK(' + p.id + ',\'cycle\',this.value,this)" placeholder="C1" style="width:50px"></td>' +
            '<td><button class="btn btn-sm" onclick="SlidePanel.deletePK(' + p.id + ')" style="color:#D85A30">删</button></td>' +
            '</tr>').join('');
    },
    async addPK() {
        await api.createPkData(this.patientId, { sample_date: new Date().toISOString().slice(0,10) });
        this.pkData = await api.getPkData(this.patientId);
        this.renderPK();
    },
    async updatePK(id, field, value, el) {
        await api.updatePkData(id, { [field]: value });
        this._saveHint(el);
    },
    async deletePK(id) {
        if (!confirm('确定删除此PK数据？')) return;
        await api.deletePkData(id);
        this.pkData = await api.getPkData(this.patientId);
        this.renderPK();
    },

    // ============ 肿瘤指标 ============
    renderMarkers() {
        const body = document.getElementById('spMarkerBody');
        body.innerHTML = this.markers.map(m => '<tr>' +
            '<td><input class="inline-edit" type="date" value="' + escapeHtml(m.test_date||'') + '" onchange="SlidePanel.updateMarker(' + m.id + ',\'test_date\',this.value,this)"></td>' +
            '<td><input class="inline-edit" value="' + escapeHtml(m.marker_name||'') + '" onchange="SlidePanel.updateMarker(' + m.id + ',\'marker_name\',this.value,this)" placeholder="CEA/CA125/..."></td>' +
            '<td><input class="inline-edit" type="number" step="0.01" value="' + escapeHtml(m.value||'') + '" onchange="SlidePanel.updateMarker(' + m.id + ',\'value\',this.value,this)" style="width:60px"></td>' +
            '<td><input class="inline-edit" value="' + escapeHtml(m.unit||'') + '" onchange="SlidePanel.updateMarker(' + m.id + ',\'unit\',this.value,this)" style="width:50px"></td>' +
            '<td><input class="inline-edit" type="number" step="0.01" value="' + escapeHtml(m.upper_limit||'') + '" onchange="SlidePanel.updateMarker(' + m.id + ',\'upper_limit\',this.value,this)" style="width:60px"></td>' +
            '<td><button class="btn btn-sm" onclick="SlidePanel.deleteMarker(' + m.id + ')" style="color:#D85A30">删</button></td>' +
            '</tr>').join('');
    },
    async addMarker() {
        await api.createTumorMarker(this.patientId, { test_date: new Date().toISOString().slice(0,10), marker_name: 'CEA' });
        this.markers = await api.getTumorMarkers(this.patientId);
        this.renderMarkers();
    },
    async updateMarker(id, field, value, el) {
        await api.updateTumorMarker(id, { [field]: value });
        this._saveHint(el);
    },
    async deleteMarker(id) {
        if (!confirm('确定删除此指标记录？')) return;
        await api.deleteTumorMarker(id);
        this.markers = await api.getTumorMarkers(this.patientId);
        this.renderMarkers();
    }
};

// 初始化面板事件
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('slidePanelClose').addEventListener('click', () => SlidePanel.close());
    document.getElementById('slidePanelOverlay').addEventListener('click', () => SlidePanel.close());
    document.querySelectorAll('.slide-tab').forEach(tab => {
        tab.addEventListener('click', () => SlidePanel.switchSubTab(tab.dataset.stab));
    });
});
