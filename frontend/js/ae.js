/**
 * AE 汇总模块 - 不良事件明细列表 + 等级汇总 + AE名称×等级交叉透视表
 * 适配 SPA 单页模式：数据随 Tab 激活加载，筛选在客户端实时重渲染
 */

const AE = {
    allRows: [],     // 项目下全部 AE 记录（来自后端）
    filtered: [],    // 当前筛选后的记录
    _bound: false,   // 筛选事件是否已绑定

    /** 加载并渲染（由 Calendar.onTabSwitch 调用） */
    async loadAE() {
        const projectId = Calendar.currentProject;
        if (!projectId) return;
        try {
            this.allRows = await api.getProjectAdverseEvents(projectId);
        } catch (e) {
            const msg = '<div class="empty-state"><p>加载失败: ' + this.esc(e.message) + '</p>'
                + '<p style="color:#9ca3af;font-size:12px">请确认后端服务已重启（AE 汇总接口为近期新增），或刷新页面重试。</p></div>';
            document.getElementById('aeListTable').innerHTML = msg;
            document.getElementById('aePivotTable').innerHTML = msg;
            return;
        }
        this.populateDoseGroups();
        this.bindFilters();
        this.applyFilters();
    },

    /** 根据数据填充剂量组筛选下拉 */
    populateDoseGroups() {
        const sel = document.getElementById('aeDoseGroupFilter');
        if (!sel) return;
        const groups = [...new Set(this.allRows.map(r => r.dose_group).filter(g => g))].sort();
        sel.innerHTML = '<option value="">全部剂量组</option>' +
            groups.map(g => '<option value="' + this.esc(g) + '">' + this.esc(g) + '</option>').join('');
    },

    /** 筛选控件事件只绑定一次 */
    bindFilters() {
        if (this._bound) return;
        const handler = () => this.applyFilters();
        document.getElementById('aeSearch').addEventListener('input', handler);
        document.getElementById('aeGradeFilter').addEventListener('change', handler);
        document.getElementById('aeSeriousOnly').addEventListener('change', handler);
        document.getElementById('aeDoseGroupFilter').addEventListener('change', handler);
        this._bound = true;
    },

    /** 应用筛选并刷新三个表格 */
    applyFilters() {
        const q = (document.getElementById('aeSearch').value || '').trim().toLowerCase();
        const gf = document.getElementById('aeGradeFilter').value;
        const seriousOnly = document.getElementById('aeSeriousOnly').checked;
        const dgf = document.getElementById('aeDoseGroupFilter').value;

        this.filtered = this.allRows.filter(r => {
            if (q && !(r.ae_term || '').toLowerCase().includes(q)) return false;
            const g = r.grade;
            if (gf === '1' && g !== 1) return false;
            if (gf === '2' && g !== 2) return false;
            if (gf === '3' && g !== 3) return false;
            if (gf === '4' && g !== 4) return false;
            if (gf === '5' && g !== 5) return false;
            if (gf === 'ge3' && !(g >= 3)) return false;
            if (gf === 'sae' && !r.serious) return false;
            if (seriousOnly && !r.serious) return false;
            if (dgf && (r.dose_group || '') !== dgf) return false;
            return true;
        });

        this.renderList();
        this.renderPivot();

        const cnt = document.getElementById('aeCount');
        if (cnt) cnt.textContent = `共 ${this.filtered.length} 条 AE（总计 ${this.allRows.length}）`;
    },

    /** 等级对应的色值（与日历 AE 圆点一致） */
    gradeColor(g) {
        const map = { 1: '#fdba74', 2: '#fb923c', 3: '#f97316', 4: '#ea580c', 5: '#b91c1c' };
        return map[g] || '#D85A30';
    },

    esc(s) {
        if (s === null || s === undefined) return '';
        return String(s).replace(/[&<>"']/g, c => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    },

    /* ---------------- AE 明细列表 ---------------- */
    renderList() {
        const rows = this.filtered;
        const wrap = document.getElementById('aeListTable');
        if (!rows.length) {
            wrap.innerHTML = '<div class="empty-state"><p>无匹配的不良事件</p></div>';
            return;
        }
        let html = '<table class="config-table"><thead><tr>'
            + '<th>患者编号</th><th>剂量组</th><th>AE 名称</th><th>发生日期</th><th>结束日期</th>'
            + '<th>等级</th><th>转归</th><th>与药物关系</th><th>严重</th><th>采取措施</th>'
            + '</tr></thead><tbody>';
        for (const r of rows) {
            const g = r.grade;
            const bg = this.gradeColor(g);
            const fg = (g <= 2) ? '#7c2d12' : '#fff';
            const serious = r.serious
                ? '<span style="color:#b91c1c;font-weight:600">是</span>'
                : '<span style="color:#9ca3af">否</span>';
            html += '<tr>'
                + '<td>' + this.esc(r.pid_text) + '</td>'
                + '<td>' + this.esc(r.dose_group || '—') + '</td>'
                + '<td>' + this.esc(r.ae_term) + '</td>'
                + '<td>' + this.esc(r.onset_date) + '</td>'
                + '<td>' + this.esc(r.end_date) + '</td>'
                + '<td><span class="grade-badge" style="background:' + bg + ';color:' + fg + '">' + (g ? g + '级' : '—') + '</span></td>'
                + '<td>' + this.esc(r.outcome) + '</td>'
                + '<td>' + this.esc(r.drug_relation) + '</td>'
                + '<td>' + serious + '</td>'
                + '<td>' + this.esc(r.action_taken) + '</td>'
                + '</tr>';
        }
        html += '</tbody></table>';
        wrap.innerHTML = html;
    },

    /* ---------------- AE名称 × 等级 交叉透视表 ----------------
     * 计数规则：同名 AE 同一参与者合并为 1 例次，取其最高等级为该参与者等级；
     * 各等级列 = 该 AE 名称下达到该最高等级的参与者数；≥3级列 = 最高等级≥3 的参与者数。
     */
    renderPivot() {
        const rows = this.filtered;
        // 同名 AE × 参与者 → 最高等级
        const byTerm = {};   // term -> { pid -> maxGrade }
        for (const r of rows) {
            const t = r.ae_term || '(未命名)';
            const g = r.grade;
            if (!(g >= 1 && g <= 5)) continue;   // 无等级不计入交叉表
            if (!byTerm[t]) byTerm[t] = {};
            const pid = r.pid_text || ('_' + r.id);
            byTerm[t][pid] = Math.max(byTerm[t][pid] || 0, g);
        }
        const termList = Object.keys(byTerm).sort((a, b) => {
            const ca = Object.keys(byTerm[b]).length, cb = Object.keys(byTerm[a]).length;
            return ca - cb || a.localeCompare(b);
        });

        const cols = [1, 2, 3, 4, 5];
        let html = '<table class="config-table ae-pivot"><thead><tr>'
            + '<th>AE 名称</th><th>1级</th><th>2级</th><th>3级</th><th>4级</th><th>5级</th>'
            + '<th>≥3级</th>'
            + '</tr></thead><tbody>';

        const colTot = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, ge3: 0 };
        if (termList.length === 0) {
            html += '<tr><td colspan="7" style="text-align:center;color:#9ca3af">无数据</td></tr>';
        } else {
            for (const t of termList) {
                const subjMap = byTerm[t];
                const d = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, ge3: 0 };
                for (const pid in subjMap) {
                    const mg = subjMap[pid];
                    if (mg >= 1 && mg <= 5) d[mg]++;
                    if (mg >= 3) d.ge3++;
                }
                cols.forEach(g => colTot[g] += d[g]);
                colTot.ge3 += d.ge3;
                html += '<tr>'
                    + '<td>' + this.esc(t) + '</td>'
                    + cols.map(g => '<td class="ae-num">' + (d[g] || '') + '</td>').join('')
                    + '<td class="ae-num"><b>' + d.ge3 + '</b></td>'
                    + '</tr>';
            }
            html += '<tr class="ae-total-row"><td><b>合计</b></td>'
                + cols.map(g => '<td class="ae-num"><b>' + colTot[g] + '</b></td>').join('')
                + '<td class="ae-num"><b>' + colTot.ge3 + '</b></td>'
                + '</tr>';
        }
        html += '</tbody></table>';
        document.getElementById('aePivotTable').innerHTML = html;
    }
};
