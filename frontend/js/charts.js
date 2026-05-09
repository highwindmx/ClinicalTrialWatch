/**
 * 图表模块 - 基线统计/瀑布图/蜘蛛图/泳道图/肿瘤指标
 * 适配SPA单页模式，容器ID从index.html中获取
 */

const Charts = {
    echarts: null,
    _resizeHandler: null,  // 统一管理resize监听器，避免累积

    /** 集中管理的状态 */
    state: {
        _colorScheme: 'default',
        // 瀑布图
        waterfallAllData: null,
        waterfallChart: null,
        waterfallEventsBound: false,
        // 蜘蛛图
        spiderAllData: null,
        spiderChart: null,
        spiderEventsBound: false,
        spiderSortBy: 'patient_id',  // 蜘蛛图排序字段
        // 泳道图
        swimmerChart: null,
        swimmerData: null,
        swimmerEventsBound: false,
        _swSortBy: 'patient_id',
        _swYAxisLabel: 'patient_id',
        _swBarColor: 'default',
        _swFilterDose: [],
        _swFilterCancer: [],
        // 肿瘤指标
        markerChart: null,
        markerEventsBound: false,
    },

    /** 科学期刊配色方案，参考 gg_sci (ggplot2) */
    colorSchemes: {
        default:   ['#378ADD', '#639922', '#D85A30', '#7F77DD', '#BA7517', '#22c55e', '#ec4899', '#14b8a6'],
        nature:    ['#2874A6', '#E74C3C', '#27AE60', '#F39C12', '#8E44AD', '#1ABC9C', '#E67E22', '#2C3E50'],
        lancet:    ['#00468B', '#EC0000', '#42B540', '#0099B4', '#925E9F', '#FDAF91', '#AD002A', '#370335'],
        jama:      ['#374D9E', '#E24B31', '#018571', '#C6A100', '#8471D1', '#D6497A', '#53A567', '#E57D34'],
        nejm:      ['#006400', '#FF4500', '#1E90FF', '#DAA520', '#9400D3', '#20B2AA', '#B22222', '#32CD32'],
        science:    ['#2874A6', '#E74C3C', '#27AE60', '#F39C12', '#8E44AD', '#1ABC9C', '#E67E22', '#2C3E50'],
        npg:       ['#E41A1C', '#377EB8', '#4DAF4A', '#984EA3', '#FF7F00', '#FFFF33', '#A65628', '#F781BF'],
        aaas:      ['#5F9ED1', '#C0504D', '#F6B300', '#58A55C', '#7F7F7F', '#985D82', '#357A8F', '#E88E2E']
    },

    /** 获取/设置当前配色方案 */
    get _colorScheme() { return this.state._colorScheme; },
    set _colorScheme(v) { this.state._colorScheme = v; },

    /** 获取当前配色数组 */
    getColorPalette() {
        return this.colorSchemes[this.state._colorScheme] || this.colorSchemes['default'];
    },

    /** RECIST 1.1 疗效评估颜色映射（全局复用） */
    responseColors: { CR: '#22c55e', PR: '#639922', SD: '#fbbf24', PD: '#D85A30', NE: '#9ca3af', '': '#9ca3af' },

    /** 患者状态颜色映射（全局复用） */
    statusColors: { '在组治疗中': '#374151', '结束治疗随访中': '#374151', '死亡/失访': '#6b7280' },

    /** 注册resize监听器（自动移除旧的，防止累积 + 200ms防抖） */
    _registerResize(chart) {
        if (this._resizeHandler) {
            window.removeEventListener('resize', this._resizeHandler);
        }
        this._resizeHandler = debounce(() => chart.resize(), 200);
        window.addEventListener('resize', this._resizeHandler);
    },

    /** 显示加载状态（带spinner动画） */
    _showLoading(container) {
        container.innerHTML = '<div class="chart-loading"><div class="chart-spinner"></div><div>加载中...</div></div>';
    },

    /** 显示空数据状态 */
    _showEmpty(container, message) {
        container.innerHTML = '<div class="chart-empty">' + (message || '暂无数据') + '</div>';
    },

    /** 显示错误信息（使用toast通知） */
    _showError(container, message) {
        showError(message);
        if (container) {
            container.innerHTML = '<div class="chart-empty">加载失败，请查看顶部错误提示</div>';
        }
    },

    /** 通用事件绑定：判断flag，绑定多个select的change事件到同一回调 */
    _bindSelectEvents(selectIds, callback, flagKey) {
        if (this.state[flagKey]) return;
        this.state[flagKey] = true;
        selectIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', callback);
        });
    },

    /** 通用筛选逻辑：按剂量组和癌肿筛选数据 */
    _applyFilters(data, filterGroupId, filterCancerId) {
        const filterGroup = document.getElementById(filterGroupId)?.value || '';
        const filterCancer = document.getElementById(filterCancerId)?.value || '';
        let result = data;
        if (filterGroup) result = result.filter(d => d.dose_group === filterGroup);
        if (filterCancer) result = result.filter(d => d.cancer_type === filterCancer);
        return result;
    },

    async ensureECharts() {
        if (window.echarts) { this.echarts = window.echarts; return; }
        const cdnUrls = [
            'https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js',
            'https://cdn.bootcdn.net/ajax/libs/echarts/5.5.0/echarts.min.js',
            'https://unpkg.com/echarts@5.5.0/dist/echarts.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js'
        ];
        for (const url of cdnUrls) {
            try {
                await new Promise((resolve, reject) => {
                    const script = document.createElement('script');
                    script.src = url;
                    script.onload = resolve;
                    script.onerror = reject;
                    document.head.appendChild(script);
                });
                if (window.echarts) {
                    this.echarts = window.echarts;
                    return;
                }
            } catch(e) {
                console.warn('ECharts CDN加载失败:', url, e);
            }
        }
        console.error('所有ECharts CDN均加载失败');
    },

    median(arr) {
        const sorted = [...arr].sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 !== 0 ? sorted[mid] : ((sorted[mid - 1] + sorted[mid]) / 2).toFixed(1);
    },

    // ============ 1. 基线统计表 - Table One 格式（按剂量组分列） ============
    /** 计算一组患者的基线统计量 */
    _calcGroupStats(patients) {
        const n = patients.length;
        if (n === 0) {
            return { n: 0, ageMean: '-', ageStd: '-', ageMedian: '-', ageMin: '-', ageMax: '-',
                     sexDist: {}, ecogDist: {}, cancerDist: {}, groupDist: {} };
        }
        let ageSum = 0, ageCount = 0, ages = [];
        const sexDist = {}, cancerDist = {}, ecogDist = {}, groupDist = {};
        patients.forEach(p => {
            const sex = p.sex || '未知'; sexDist[sex] = (sexDist[sex] || 0) + 1;
            const cancer = p.cancer_type || '未知'; cancerDist[cancer] = (cancerDist[cancer] || 0) + 1;
            const ecog = p.ecog_score != null ? String(p.ecog_score) : '未知'; ecogDist[ecog] = (ecogDist[ecog] || 0) + 1;
            const group = p.dose_group || '未分组'; groupDist[group] = (groupDist[group] || 0) + 1;
            if (p.age) { const age = parseInt(p.age); ageSum += age; ageCount++; ages.push(age); }
        });
        const ageMean = ageCount > 0 ? (ageSum / ageCount).toFixed(1) : '-';
        const ageStd = ageCount > 1 ? Math.sqrt(ages.reduce((s, a) => s + (a - ageSum/ageCount)**2, 0) / (ageCount - 1)).toFixed(1) : '-';
        const ageMedian = ageCount > 0 ? this.median(ages) : '-';
        const ageMin = ageCount > 0 ? Math.min(...ages) : '-';
        const ageMax = ageCount > 0 ? Math.max(...ages) : '-';
        return { n: n, ageMean: ageMean, ageStd: ageStd, ageMedian: ageMedian, ageMin: ageMin, ageMax: ageMax, sexDist: sexDist, ecogDist: ecogDist, cancerDist: cancerDist, groupDist: groupDist };
    },

    /** 格式化 N(%) */
    _fmtNPct(count, total) {
        if (total === 0) return '-';
        return count + ' (' + (count / total * 100).toFixed(1) + '%)';
    },

    async loadBaselineTable() {
        const projectId = Calendar.currentProject;
        if (!projectId) return;
        const container = document.getElementById('chartBaseline');
        this._showLoading(container);
        try {
            const patients = await api.getChartBaseline(projectId);
            if (!patients.length) { this._showEmpty(container); return; }

            // 获取所有剂量组（按配置排序）
            const doseGroups = await this._sortByConfigOrder([...new Set(patients.map(p => p.dose_group || '未分组'))], 'doseGroup');
            const groups = ['总体', ...doseGroups];

            // 按组分组患者
            const groupData = {};
            groups.forEach(g => {
                groupData[g] = g === '总体' ? patients : patients.filter(p => (p.dose_group || '未分组') === g);
            });

            // 计算每组统计量
            const stats = {};
            groups.forEach(g => { stats[g] = this._calcGroupStats(groupData[g]); });

            // 渲染表格
            const totalN = patients.length;
            let html = '<h4 style="margin-bottom:12px;font-size:15px">基线特征 (N=' + totalN + ')</h4>';
            html += '<div style="overflow-x:auto"><table class="table-one"><thead><tr>';
            html += '<th style="min-width:100px">特征</th>';
            groups.forEach(g => { html += '<th style="min-width:110px">' + g + ' (N=' + stats[g].n + ')</th>'; });
            html += '</tr></thead><tbody>';

            // 年龄
            html += '<tr class="category-row"><td>年龄(岁)</td>' + groups.map(() => '<td></td>').join('') + '</tr>';
            html += '<tr class="subcategory-row"><td>均值(SD)</td>';
            groups.forEach(g => { html += '<td>' + stats[g].ageMean + ' (' + stats[g].ageStd + ')</td>'; });
            html += '</tr>';
            html += '<tr class="subcategory-row"><td>中位数</td>';
            groups.forEach(g => { html += '<td>' + stats[g].ageMedian + '</td>'; });
            html += '</tr>';
            html += '<tr class="subcategory-row"><td>范围</td>';
            groups.forEach(g => { html += '<td>' + stats[g].ageMin + ' - ' + stats[g].ageMax + '</td>'; });
            html += '</tr>';

            // 性别
            html += '<tr class="category-row"><td>性别</td>' + groups.map(() => '<td></td>').join('') + '</tr>';
            const allSexKeys = [...new Set(groups.flatMap(g => Object.keys(stats[g].sexDist)))];
            allSexKeys.forEach(k => {
                html += '<tr class="subcategory-row"><td>' + k + '</td>';
                groups.forEach(g => {
                    const n = stats[g].sexDist[k] || 0;
                    html += '<td>' + this._fmtNPct(n, stats[g].n) + '</td>';
                });
                html += '</tr>';
            });

            // ECOG评分
            html += '<tr class="category-row"><td>ECOG评分</td>' + groups.map(() => '<td></td>').join('') + '</tr>';
            const ecogOrder = ['0', '1', '2', '3', '4', '未知'];
            const allEcogKeys = [...new Set(groups.flatMap(g => Object.keys(stats[g].ecogDist)))];
            const sortedEcog = ecogOrder.filter(k => allEcogKeys.includes(k)).concat(allEcogKeys.filter(k => !ecogOrder.includes(k)));
            sortedEcog.forEach(k => {
                const label = k === '未知' ? '未知' : k;
                html += '<tr class="subcategory-row"><td>' + label + '</td>';
                groups.forEach(g => {
                    const n = stats[g].ecogDist[k] || 0;
                    html += '<td>' + this._fmtNPct(n, stats[g].n) + '</td>';
                });
                html += '</tr>';
            });

            // 癌肿类型
            html += '<tr class="category-row"><td>癌肿类型</td>' + groups.map(() => '<td></td>').join('') + '</tr>';
            const allCancerKeys = [...new Set(groups.flatMap(g => Object.keys(stats[g].cancerDist)))];
            allCancerKeys.forEach(k => {
                html += '<tr class="subcategory-row"><td>' + k + '</td>';
                groups.forEach(g => {
                    const n = stats[g].cancerDist[k] || 0;
                    html += '<td>' + this._fmtNPct(n, stats[g].n) + '</td>';
                });
                html += '</tr>';
            });

            html += '</tbody></table></div>';
            container.innerHTML = html;
        } catch (e) {
            this._showError(container, '加载失败: ' + (e.message || e));
        }
    },

    // ============ 2. 瀑布图 ============
    async loadWaterfall() {
        const projectId = Calendar.currentProject;
        if (!projectId) return;
        const container = document.getElementById('chartWaterfall');
        // 销毁旧图表，防止内存泄漏
        if (this.state.waterfallChart) { this.state.waterfallChart.dispose(); this.state.waterfallChart = null; }
        this._showLoading(container);
        await this.ensureECharts();
        if (!this.echarts) { this._showError(container, 'ECharts库加载失败<br><small>请检查网络连接后刷新页面</small>'); return; }
        try {
            const data = await api.getChartWaterfall(projectId);
            this.state.waterfallAllData = data;
            // 预加载排序配置供同步渲染使用
            try {
                const [dgList, ctList] = await Promise.all([api.getDoseGroups(projectId), api.getCancerTypes(projectId)]);
                this.state._configDoseGroups = dgList;
                this.state._configCancerTypes = ctList;
            } catch(e) {
                this.state._configDoseGroups = [];
                this.state._configCancerTypes = [];
            }
            await this._populateFilterSelects(data, 'wfFilterGroup', 'wfFilterCancer');
            this._bindSelectEvents(['wfColorBy', 'wfSortBy', 'wfFilterGroup', 'wfFilterCancer'],
                () => this._renderWaterfallChart(), 'waterfallEventsBound');
            requestAnimationFrame(() => this._renderWaterfallChart());
        } catch (e) {
            this._showError(container, '加载失败: ' + (e.message || e));
        }
    },

    _renderWaterfallChart() {
        let data = [...this.state.waterfallAllData];
        const container = document.getElementById('chartWaterfall');
        // 清理旧图例
        const oldLegend = container.parentElement.querySelector('.waterfall-legend');
        if (oldLegend) oldLegend.remove();
        if (!data || !data.length) { this._showEmpty(container); return; }

        // 筛选
        data = this._applyFilters(data, 'wfFilterGroup', 'wfFilterCancer');
        if (!data.length) { this._showEmpty(container, '筛选后无数据'); return; }

        // 排序
        const sortBy = document.getElementById('wfSortBy')?.value || 'sod_change';
        const _dgOrderMap = {}, _ctOrderMap = {};
        (this.state._configDoseGroups || []).forEach((c, i) => { _dgOrderMap[c.name] = i; });
        (this.state._configCancerTypes || []).forEach((c, i) => { _ctOrderMap[c.name] = i; });
        if (sortBy === 'sod_change') {
            data.sort((a, b) => b.sod_change - a.sod_change);
        } else if (sortBy === 'dose_group') {
            data.sort((a, b) => (_dgOrderMap[a.dose_group] ?? 999) - (_dgOrderMap[b.dose_group] ?? 999) || b.sod_change - a.sod_change);
        } else if (sortBy === 'cancer_type') {
            data.sort((a, b) => (_ctOrderMap[a.cancer_type] ?? 999) - (_ctOrderMap[b.cancer_type] ?? 999) || b.sod_change - a.sod_change);
        }

        // 销毁旧图表，防止内存泄漏
        if (this.state.waterfallChart) { this.state.waterfallChart.dispose(); this.state.waterfallChart = null; }
        const chart = this.echarts.init(container);
        this.state.waterfallChart = chart;

        // 着色方式
        const colorBy = document.getElementById('wfColorBy')?.value || 'best_response';
        const responseColors = this.responseColors;
        const colorPalette = this.getColorPalette();

        let colorMap = {};
        let colorLabel = '最佳疗评';
        if (colorBy === 'dose_group') {
            colorLabel = '剂量组';
            const groups = [...new Set(data.map(d => d.dose_group).filter(Boolean))];
            groups.forEach((g, i) => { colorMap[g] = colorPalette[i % colorPalette.length]; });
        } else if (colorBy === 'cancer_type') {
            colorLabel = '癌肿';
            const cancers = [...new Set(data.map(d => d.cancer_type).filter(Boolean))];
            cancers.forEach((c, i) => { colorMap[c] = colorPalette[i % colorPalette.length]; });
        } else {
            colorMap = responseColors;
        }

        const getBarColor = (d) => {
            if (colorBy === 'dose_group') return colorMap[d.dose_group] || '#9ca3af';
            if (colorBy === 'cancer_type') return colorMap[d.cancer_type] || '#9ca3af';
            return colorMap[d.best_response] || '#9ca3af';
        };

        const statusSymbols = { '在组治疗中': 'path://M0,0 L10,5 L0,10 Z', '结束治疗随访中': 'circle', '死亡/失访': 'path://M2,2 L10,10 M10,2 L2,10' };
        const statusColors = this.statusColors;

        const sodValues = data.map(d => d.sod_change);
        const yMin = Math.min(0, ...sodValues);
        const yMax = Math.max(0, ...sodValues);
        const yRange = yMax - yMin || 1;
        const statusOffset = yRange * 0.10; // 增大偏移量，让状态图标和数值标签平行不重叠
        const confirmedOffset = yRange * 0.12;

        const barData = data.map(d => ({
            value: parseFloat(d.sod_change.toFixed(1)),
            itemStyle: { color: getBarColor(d) },
            label: { show: true, position: d.sod_change >= 0 ? 'top' : 'bottom', formatter: d.sod_change.toFixed(1) + '%', fontSize: 9 }
        }));

        const statusData = data.map(d => {
            const val = parseFloat(d.sod_change.toFixed(1));
            const offsetVal = d.sod_change >= 0 ? val + statusOffset : val - statusOffset;
            return {
                value: offsetVal,
                symbol: statusSymbols[d.patient_status] || 'circle',
                symbolSize: 12,
                itemStyle: { color: statusColors[d.patient_status] || '#6b7280' }
            };
        });

        chart.setOption({
            title: { text: '瀑布图 - 靶病灶SOD变化' + (data.length < this.state.waterfallAllData.length ? ' (已筛选)' : ''), left: 'center', textStyle: { fontSize: 14 } },
            tooltip: {
                trigger: 'axis',
                formatter: function(params) {
                    const barParam = params.find(p => p.seriesName === 'SOD变化');
                    if (!barParam) return '';
                    const d = data[barParam.dataIndex];
                    if (!d) return '';
                    let tip = '<b>' + d.patient_id + '</b><br/>SOD变化: ' + d.sod_change.toFixed(1) + '%';
                    if (d.best_response) tip += '<br/>最佳疗评: ' + d.best_response;
                    if (d.patient_status) tip += '<br/>状态: ' + d.patient_status;
                    if (d.dose_group) tip += '<br/>剂量组: ' + d.dose_group;
                    if (d.cancer_type) tip += '<br/>癌肿: ' + d.cancer_type;
                    if (d.confirmed_crpr) tip += '<br/>确认CR/PR: 是';
                    return tip;
                }
            },
            grid: { top: 50, bottom: 80, left: 80, right: 30 },
            xAxis: { type: 'category', data: data.map(d => d.patient_id), axisLabel: { rotate: 45, fontSize: 10 } },
            yAxis: { type: 'value', name: 'SOD变化(%)', axisLabel: { formatter: '{value}%' } },
            series: [
                {
                    name: 'SOD变化', type: 'bar', data: barData,
                    markPoint: {
                        data: data.map((d, idx) => {
                            if (!d.confirmed_crpr) return null;
                            const pinOffset = Math.abs(yRange * 0.02);
                            const pinY = d.sod_change < 0 ? pinOffset : -pinOffset;
                            return {
                                coord: [idx, pinY], symbol: 'pin', symbolSize: 18,
                                itemStyle: { color: '#22c55e' },
                                label: { show: true, formatter: '✓', position: 'inside', fontSize: 11, color: '#fff', fontWeight: 'bold' }
                            };
                        }).filter(Boolean),
                        tooltip: { show: false }, z: 10
                    },
                    markLine: {
                        silent: true, symbol: 'none',
                        data: [
                            { yAxis: -30, name: 'PR线(-30%)', lineStyle: { color: '#639922', type: 'dashed' } },
                            { yAxis: 20, name: 'PD线(+20%)', lineStyle: { color: '#D85A30', type: 'dashed' } }
                        ]
                    }
                },
                { name: '患者状态', type: 'scatter', data: statusData, z: 5, tooltip: { show: false } }
            ]
        });

        // 自定义图例
        let legendHtml = '<div class="waterfall-legend" style="display:flex;flex-wrap:wrap;gap:12px;padding:6px 10px;font-size:14px;color:#374151">';
        legendHtml += '<span style="font-weight:600;color:#374151">着色(' + colorLabel + '):</span>';
        Object.entries(colorMap).forEach(([k, v]) => {
            if (k) legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:12px;height:12px;border-radius:2px;background:' + v + '"></span>' + k + '</span>';
        });
        legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="color:#374151;font-size:14px">▶</span>在组治疗</span>';
        legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#374151"></span>随访中</span>';
        legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="font-size:14px;color:#6b7280">×</span>死亡/失访</span>';
        legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:12px;height:12px;background:#22c55e;border-radius:50%;text-align:center;line-height:12px;color:#fff;font-size:8px">✓</span>确认CR/PR</span>';
        legendHtml += '</div>';
        const legendEl = document.createElement('div');
        legendEl.innerHTML = legendHtml;
        container.parentElement.appendChild(legendEl);
        this._registerResize(chart);
    },

    // ============ 3. 蜘蛛图 ============
    async loadSpider() {
        const projectId = Calendar.currentProject;
        if (!projectId) return;
        const container = document.getElementById('chartSpider');
        if (this.state.spiderChart) { this.state.spiderChart.dispose(); this.state.spiderChart = null; }
        this._showLoading(container);
        await this.ensureECharts();
        if (!this.echarts) { this._showError(container, 'ECharts库加载失败<br><small>请检查网络连接后刷新页面</small>'); return; }
        try {
            const data = await api.getChartSpider(projectId);
            this.state.spiderAllData = data;
            // 预加载排序配置供同步渲染使用
            try {
                const [dgList, ctList] = await Promise.all([api.getDoseGroups(projectId), api.getCancerTypes(projectId)]);
                this.state._configDoseGroups = dgList;
                this.state._configCancerTypes = ctList;
            } catch(e) {
                this.state._configDoseGroups = [];
                this.state._configCancerTypes = [];
            }
            await this._populateFilterSelects(data, 'spFilterGroup', 'spFilterCancer');
            // 绑定筛选和着色事件（只绑一次）
            this._bindSelectEvents(['spColorBy', 'spFilterGroup', 'spFilterCancer'],
                () => this._renderSpiderChart(), 'spiderEventsBound');
            requestAnimationFrame(() => this._renderSpiderChart());
        } catch (e) {
            this._showError(container, '加载失败: ' + (e.message || e));
        }
    },

    _renderSpiderChart() {
        let data = [...this.state.spiderAllData];
        const container = document.getElementById('chartSpider');
        if (!data || !data.length) { this._showEmpty(container); return; }

        // 筛选
        data = this._applyFilters(data, 'spFilterGroup', 'spFilterCancer');
        if (!data.length) { this._showEmpty(container, '筛选后无数据'); return; }

        // 销毁旧图表，防止内存泄漏
        if (this.state.spiderChart) { this.state.spiderChart.dispose(); this.state.spiderChart = null; }
        const chart = this.echarts.init(container);
        this.state.spiderChart = chart;

        const colorPalette = this.getColorPalette();
        const colorBy = document.getElementById('spColorBy')?.value || 'dose_group';
        const colorKey = colorBy === 'cancer_type' ? 'cancer_type' : 'dose_group';
        const colorLabel = colorBy === 'cancer_type' ? '癌肿类型' : '剂量组';
        const groupColors = {};
        let colorIdx = 0;
        data.forEach(d => {
            if (!groupColors[d[colorKey]]) { groupColors[d[colorKey]] = colorPalette[colorIdx % colorPalette.length]; colorIdx++; }
        });

        chart.setOption({
            title: { text: '蜘蛛图 - SOD随时间变化' + (data.length < this.state.spiderAllData.length ? ' (已筛选)' : ''), left: 'center', textStyle: { fontSize: 14 } },
            tooltip: { trigger: 'item', formatter: function(p) { return p.seriesName + '<br/>第' + p.value[0] + '天<br/>SOD变化: ' + parseFloat(p.value[1]).toFixed(1) + '%'; } },
            legend: { show: false },
            grid: { top: 50, bottom: 60, left: 80, right: 30 },
            xAxis: { type: 'value', name: '距首次肿评天数', nameLocation: 'center', nameGap: 30, min: 0 },
            yAxis: { type: 'value', name: 'SOD变化(%)' },
            series: [
                { name: '_ref', type: 'line', data: [], markLine: { silent: true, symbol: 'none', data: [
                    { yAxis: -30, name: 'PR线(-30%)', lineStyle: { color: '#639922', type: 'dashed' } },
                    { yAxis: 20, name: 'PD线(+20%)', lineStyle: { color: '#D85A30', type: 'dashed' } }
                ]}},
                ...data.map(d => ({
                    name: d.patient_id, type: 'line',
                    data: d.points.map(p => [p.days, parseFloat(p.sod_change).toFixed(1)]),
                    smooth: false, symbol: 'circle', symbolSize: 6,
                    lineStyle: { color: groupColors[d[colorKey]] },
                    itemStyle: { color: groupColors[d[colorKey]] }
                }))
            ]
        });

        // 颜色图例
        const parent = container.parentElement;
        const oldLegend = parent.querySelector('.spider-legend');
        if (oldLegend) oldLegend.remove();
        let legendHtml = '<div class="spider-legend" style="display:flex;flex-wrap:wrap;gap:12px;padding:6px 10px;font-size:14px;color:#374151">';
        legendHtml += '<span style="font-weight:600">颜色图例(按' + colorLabel + '):</span>';
        Object.entries(groupColors).forEach(([name, color]) => {
            legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:20px;height:4px;background:' + color + ';border-radius:2px"></span>' + (name || '未分组') + '</span>';
        });
        legendHtml += '</div>';
        const legendEl = document.createElement('div');
        legendEl.innerHTML = legendHtml;
        parent.appendChild(legendEl);
        this._registerResize(chart);
    },

    // ============ 4. 泳道图（独立Tab） ============
    async loadSwimmer() {
        const projectId = Calendar.currentProject;
        if (!projectId) return;
        const container = document.getElementById('chartSwimmer');
        if (this.state.swimmerChart) { this.state.swimmerChart.dispose(); this.state.swimmerChart = null; }
        this._showLoading(container);
        await this.ensureECharts();
        if (!this.echarts) { this._showError(container, 'ECharts库加载失败<br><small>请检查网络连接后刷新页面</small>'); return; }
        try {
            const data = await api.getChartSwimmer(projectId);
            this.state.swimmerData = data;
            // 预加载排序配置供同步渲染使用
            try {
                const [dgList, ctList] = await Promise.all([api.getDoseGroups(projectId), api.getCancerTypes(projectId)]);
                this.state._configDoseGroups = dgList;
                this.state._configCancerTypes = ctList;
            } catch(e) {
                this.state._configDoseGroups = [];
                this.state._configCancerTypes = [];
            }
            await this._populateSwimmerFilters();
            // 等DOM渲染完成后再渲染图表，避免容器尺寸为0
            requestAnimationFrame(() => this._renderSwimmerChart(data));
            // 绑定事件（只绑定一次）
            if (!this.state.swimmerEventsBound) {
                this.state.swimmerEventsBound = true;
                ['swShowDrug','swShowAssess','swShowAE','swShowStatus'].forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.addEventListener('change', () => {
                        requestAnimationFrame(() => this._renderSwimmerChart(this.state.swimmerData));
                    });
                });
                ['swSortBy', 'swYAxisLabel', 'swBarColor'].forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.addEventListener('change', () => {
                        this.state._swSortBy = document.getElementById('swSortBy')?.value || 'patient_id';
                        this.state._swYAxisLabel = document.getElementById('swYAxisLabel')?.value || 'patient_id';
                        this.state._swBarColor = document.getElementById('swBarColor')?.value || 'default';
                        requestAnimationFrame(() => this._renderSwimmerChart(this.state.swimmerData));
                    });
                });
            }
        } catch (e) {
            this._showError(container, '加载失败: ' + (e.message || e));
        }
    },

    async _populateSwimmerFilters() {
        const doseFilters = document.getElementById('swDoseFilters');
        const cancerFilters = document.getElementById('swCancerFilters');
        if (!doseFilters || !cancerFilters) return;
        const groups = await this._sortByConfigOrder([...new Set(this.state.swimmerData.map(d => d.dose_group).filter(Boolean))], 'doseGroup');
        doseFilters.innerHTML = groups.map(g =>
            '<label style="display:flex;align-items:center;gap:3px;font-size:12px;cursor:pointer">' +
            '<input type="checkbox" value="' + g + '" checked onchange="Charts._onSwimmerControlChange()"> ' + g +
            '</label>').join('');
        const cancers = await this._sortByConfigOrder([...new Set(this.state.swimmerData.map(d => d.cancer_type).filter(Boolean))], 'cancerType');
        cancerFilters.innerHTML = cancers.map(c =>
            '<label style="display:flex;align-items:center;gap:3px;font-size:12px;cursor:pointer">' +
            '<input type="checkbox" value="' + c + '" checked onchange="Charts._onSwimmerControlChange()"> ' + c +
            '</label>').join('');
    },

    _onSwimmerControlChange() {
        this.state._swSortBy = document.getElementById('swSortBy')?.value || 'patient_id';
        this.state._swYAxisLabel = document.getElementById('swYAxisLabel')?.value || 'patient_id';
        this.state._swBarColor = document.getElementById('swBarColor')?.value || 'default';
        this.state._swFilterDose = [...document.querySelectorAll('#swDoseFilters input:checked')].map(cb => cb.value);
        this.state._swFilterCancer = [...document.querySelectorAll('#swCancerFilters input:checked')].map(cb => cb.value);
        requestAnimationFrame(() => this._renderSwimmerChart(this.state.swimmerData));
    },

    _renderSwimmerChart(rawData) {
        if (!rawData || !rawData.length) { document.getElementById('chartSwimmer').innerHTML = '<div class="chart-empty">暂无数据</div>'; return; }

        // —— 1. 筛选 ——
        let data = rawData.filter(d => {
            if (this.state._swFilterDose.length > 0 && !this.state._swFilterDose.includes(d.dose_group)) return false;
            if (this.state._swFilterCancer.length > 0 && !this.state._swFilterCancer.includes(d.cancer_type)) return false;
            return true;
        });
        if (!data.length) { document.getElementById('chartSwimmer').innerHTML = '<div class="chart-empty">筛选后无数据</div>'; return; }

        // —— 2. 排序 ——
        const sortBy = this.state._swSortBy;
        const _swDgOrderMap = {}, _swCtOrderMap = {};
        (this.state._configDoseGroups || []).forEach((c, i) => { _swDgOrderMap[c.name] = i; });
        (this.state._configCancerTypes || []).forEach((c, i) => { _swCtOrderMap[c.name] = i; });
        data.sort((a, b) => {
            if (sortBy === 'dose_group') {
                const cmp = (_swDgOrderMap[a.dose_group] ?? 999) - (_swDgOrderMap[b.dose_group] ?? 999);
                if (cmp !== 0) return cmp;
            } else if (sortBy === 'cancer_type') {
                const cmp = (_swCtOrderMap[a.cancer_type] ?? 999) - (_swCtOrderMap[b.cancer_type] ?? 999);
                if (cmp !== 0) return cmp;
            } else {
                const va = a[sortBy] || '', vb = b[sortBy] || '';
                if (va < vb) return -1;
                if (va > vb) return 1;
            }
            // 次级排序：研究天数从大到小
            if (b.study_days !== a.study_days) return b.study_days - a.study_days;
            if (a.patient_id < b.patient_id) return -1;
            if (a.patient_id > b.patient_id) return 1;
            return 0;
        });

        // —— 3. Y轴标签格式 ——
        const yAxisLabel = this.state._swYAxisLabel;
        const yData = data.map(d => {
            if (yAxisLabel === 'with_dose') {
                return d.patient_id + (d.dose_group ? ' (' + d.dose_group + ')' : '');
            } else if (yAxisLabel === 'with_cancer') {
                return d.patient_id + (d.cancer_type ? ' [' + d.cancer_type + ']' : '');
            } else if (yAxisLabel === 'with_both') {
                const parts = [d.patient_id];
                if (d.dose_group) parts.push('(' + d.dose_group + ')');
                if (d.cancer_type) parts.push('[' + d.cancer_type + ']');
                return parts.join(' ');
            }
            return d.patient_id;
        });

        const showDrug = document.getElementById('swShowDrug')?.checked !== false;
        const showAssess = document.getElementById('swShowAssess')?.checked !== false;
        const showAE = document.getElementById('swShowAE')?.checked !== false;
        const showStatus = document.getElementById('swShowStatus')?.checked !== false;

        data.forEach(d => {
            d.study_days = Math.max(0, d.study_days || 0);
            d.days = Math.max(0, d.days || 0);
            d.drug_start_offset = Math.max(0, d.drug_start_offset || 0);
            if (d.assessment_points) d.assessment_points.forEach(ap => { ap.days = Math.max(0, ap.days); });
            if (d.ae_periods) d.ae_periods.forEach(ae => { ae.start_days = Math.max(0, ae.start_days); ae.end_days = Math.max(0, ae.end_days); });
        });

        // 可配置的状态图示偏移量（默认3px）
        const statusOffset = parseInt(document.getElementById('swStatusOffset')?.value) || 3;

        // 销毁旧图表
        if (this.state.swimmerChart) { this.state.swimmerChart.dispose(); this.state.swimmerChart = null; }
        const container = document.getElementById('chartSwimmer');

        const n = data.length;
        let rowHeight, barW;
        if (n <= 10) { rowHeight = 50; barW = 20; }
        else if (n <= 20) { rowHeight = 36; barW = 16; }
        else if (n <= 40) { rowHeight = 28; barW = 12; }
        else if (n <= 60) { rowHeight = 22; barW = 9; }
        else { rowHeight = 18; barW = 7; }

        container.style.height = Math.max(400, n * rowHeight + 120) + 'px';
        const chart = this.echarts.init(container);
        this.state.swimmerChart = chart;

        const responseColors = this.responseColors;
        const aeGradeColors = { 1: '#fdba74', 2: '#fb923c', 3: '#f97316', 4: '#ea580c', 5: '#b91c1c' };
        const statusSymbols = { '在组治疗中': 'path://M0,0 L10,5 L0,10 Z', '结束治疗随访中': 'circle', '死亡/失访': 'path://M2,2 L10,10 M10,2 L2,10' };
        const statusColors = this.statusColors;

        const barColorMode = this.state._swBarColor;
        const barColorPalette = this.getColorPalette();
        const barColorMap = {};
        if (barColorMode === 'dose_group' || barColorMode === 'cancer_type') {
            const configList = barColorMode === 'dose_group' ? (this.state._configDoseGroups || []) : (this.state._configCancerTypes || []);
            const orderMap = {};
            configList.forEach((c, i) => { orderMap[c.name] = i; });
            const values = [...new Set(data.map(d => d[barColorMode]).filter(Boolean))].sort((a, b) => (orderMap[a] ?? 999) - (orderMap[b] ?? 999));
            values.forEach((v, i) => { barColorMap[v] = barColorPalette[i % barColorPalette.length]; });
        }
        const getBarColor = (d) => {
            if (barColorMode === 'dose_group') return barColorMap[d.dose_group] || '#93c5fd';
            if (barColorMode === 'cancer_type') return barColorMap[d.cancer_type] || '#93c5fd';
            return '#93c5fd';
        };

        // 横坐标最大值：基于研究状态天数（含状态图示偏移）
        const studyMaxDays = Math.max(...data.map(d => d.study_days), 50);
        const drugEndMax = Math.max(...data.map(d => d.drug_start_offset + d.days), 0);
        const maxDays = Math.max(studyMaxDays + statusOffset, drugEndMax, 50) + 60;
        const series = [];

        // —— 研究状态条形（从入组到终点/今天） ——
        series.push({
            name: '研究状态', type: 'bar',
            data: data.map(d => ({
                value: d.study_days,
                itemStyle: {
                    color: d.status_raw === 'off_study' ? '#d1d5db' : '#e5e7eb',
                    borderRadius: [3, 3, 0, 0]
                }
            })),
            barWidth: barW + 4, barGap: '10%', z: 0
        });

        // —— 治疗用药条形（透明叠在研究状态之上） ——
        if (showDrug) {
            series.push({
                name: '治疗用药', type: 'custom', z: 1,
                renderItem: function(params, api) {
                    const d = data[params.dataIndex];
                    if (!d || d.days <= 0) return null;
                    const xStart = api.coord([d.drug_start_offset, params.dataIndex]);
                    const xEnd = api.coord([d.drug_start_offset + d.days, params.dataIndex]);
                    if (!xStart || !xEnd) return null;
                    const y = api.coord([0, params.dataIndex]);
                    const cellH = api.size([0, 1])[1];
                    const h = Math.max(3, barW - 1);  // 比研究状态条(bw+4)略窄，补偿渲染差异
                    return {
                        type: 'rect',
                        shape: { x: xStart[0], y: y[1] - h / 2, width: xEnd[0] - xStart[0], height: h },
                        style: { fill: getBarColor(d), opacity: 0.30 }
                    };
                },
                data: data.map((_, i) => i)
            });
        }

        if (showAssess) {
            const allAssessPoints = [];
            data.forEach((d, idx) => {
                if (d.assessment_points && d.assessment_points.length > 0) {
                    d.assessment_points.forEach(ap => {
                        allAssessPoints.push({
                            value: [ap.days, idx],
                            itemStyle: { color: responseColors[ap.response] || '#9ca3af' },
                            symbol: 'diamond', symbolSize: Math.max(8, barW - 2),
                            label: { show: n <= 40, formatter: ap.response || '', position: 'top', fontSize: n <= 20 ? 9 : 7, color: responseColors[ap.response] || '#9ca3af' }
                        });
                    });
                }
            });
            if (allAssessPoints.length > 0) {
                series.push({ name: '疗评结果', type: 'scatter', data: allAssessPoints, z: 3 });
            }
        }

        if (showAE) {
            const aeData = [];
            data.forEach((d, idx) => {
                if (d.ae_periods && d.ae_periods.length > 0) {
                    d.ae_periods.forEach(ae => {
                        aeData.push({
                            rowIndex: idx,
                            startDay: Math.max(0, ae.start_days),
                            endDay: Math.max(0, ae.end_days),
                            maxGrade: ae.max_grade || 1,
                            aeTerm: ae.ae_term || 'AE'
                        });
                    });
                }
            });
            if (aeData.length > 0) {
                series.push({
                    name: 'AE', type: 'custom', z: 2,
                    renderItem: function(params, api) {
                        const item = aeData[params.dataIndex];
                        if (!item) return {};
                        const startPixel = api.coord([item.startDay, item.rowIndex]);
                        const endPixel = api.coord([item.endDay, item.rowIndex]);
                        if (!startPixel || !endPixel) return {};
                        const color = aeGradeColors[item.maxGrade] || '#f97316';
                        return {
                            type: 'line',
                            shape: { x1: startPixel[0], y1: startPixel[1], x2: endPixel[0], y2: endPixel[1] },
                            style: { stroke: color, lineWidth: n <= 20 ? 3 : n <= 40 ? 2 : 1.5, lineCap: 'round' }
                        };
                    },
                    data: aeData.map((_, i) => i),
                    tooltip: {
                        formatter: function(params) {
                            const item = aeData[params.dataIndex];
                            if (!item) return '';
                            return item.aeTerm + ' (G' + item.maxGrade + ')<br/>' + item.startDay + '天 - ' + item.endDay + '天';
                        }
                    }
                });
            }
        }

        // —— 患者状态图示（研究状态条形之后 + 可配置偏移） ——
        const statusSize = Math.max(6, barW - 4);
        if (showStatus) {
            series.push({
                name: '患者状态', type: 'scatter', symbolSize: statusSize, z: 4,
                data: data.map((d, idx) => ({
                    value: [d.study_days + statusOffset, idx],
                    symbol: statusSymbols[d.patient_status] || 'circle',
                    symbolSize: statusSize,
                    itemStyle: { color: statusColors[d.patient_status] || '#6b7280' }
                })),
                tooltip: { show: false }
            });
        }

        chart.setOption({
            title: { text: '泳道图 - 研究状态与治疗用药', left: 'center', textStyle: { fontSize: 14 } },
            tooltip: {
                trigger: 'item',
                formatter: function(params) {
                    if (params.seriesName === 'AE') {
                        const item = aeData ? aeData[params.dataIndex] : null;
                        return item ? item.aeTerm + ' (G' + item.maxGrade + ')<br/>' + item.startDay + '天 - ' + item.endDay + '天' : '';
                    }
                    if (params.seriesName === '患者状态') return '';
                    if (params.seriesName === '研究状态') {
                        const d = data[params.dataIndex];
                        if (!d) return '';
                        let tip = '<b>' + d.patient_id + '</b><br/>研究天数: ' + d.study_days + '天';
                        if (d.patient_status) tip += '<br/>状态: ' + d.patient_status;
                        if (d.status_raw === 'off_study' && d.off_study_date) tip += '<br/>出组日期: ' + d.off_study_date;
                        if (d.enroll_date) tip += '<br/>入组日期: ' + d.enroll_date;
                        return tip;
                    }
                    const idx = params.value && params.value[1] !== undefined ? params.value[1] : params.dataIndex;
                    const d = data[idx];
                    if (!d) return '';
                    if (params.seriesName === '治疗用药') {
                        let tip = '<b>' + d.patient_id + '</b><br/>治疗天数: ' + d.days + '天';
                        tip += '<br/>入组第' + d.drug_start_offset + '天起';
                        if (d.patient_status) tip += '<br/>状态: ' + d.patient_status;
                        if (d.dose_group) tip += '<br/>剂量组: ' + d.dose_group;
                        if (d.cancer_type) tip += '<br/>癌肿: ' + d.cancer_type;
                        return tip;
                    }
                    let tip = '<b>' + d.patient_id + '</b><br/>研究天数: ' + d.study_days + '天';
                    if (d.patient_status) tip += '<br/>状态: ' + d.patient_status;
                    if (d.dose_group) tip += '<br/>剂量组: ' + d.dose_group;
                    if (d.cancer_type) tip += '<br/>癌肿: ' + d.cancer_type;
                    if (params.seriesName === '疗评结果' && d.assessment_points) {
                        const ap = d.assessment_points.find(ap => ap.days === params.value[0]);
                        if (ap) tip += '<br/>疗评: ' + ap.response;
                    }
                    return tip;
                }
            },
            grid: { top: 60, bottom: 50, left: 240, right: 80 },
            xAxis: { type: 'value', name: '天数（入组=0）', nameLocation: 'center', nameGap: 30, min: -maxDays * 0.03, max: maxDays, splitLine: { show: false }, axisLabel: { formatter: function(v) { return v < 0 ? '' : v; } } },
            yAxis: { type: 'category', data: yData, inverse: true, axisLabel: { fontSize: n <= 20 ? 11 : n <= 40 ? 9 : 7 } },
            series: series
        });

        // 自定义图例
        const parentEl = container.parentElement;
        const oldLegend = parentEl.querySelector('.swimmer-legend');
        if (oldLegend) oldLegend.remove();

        let legendHtml = '<div class="swimmer-legend" style="display:flex;flex-wrap:wrap;gap:12px;padding:6px 10px;font-size:14px;color:#374151">';
        legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:20px;height:8px;background:#e5e7eb;border-radius:3px"></span>研究状态</span>';
        if (showDrug) {
            if (barColorMode === 'dose_group' || barColorMode === 'cancer_type') {
                const label = barColorMode === 'dose_group' ? '剂量组' : '癌肿类型';
                legendHtml += '<span style="font-weight:600">治疗(' + label + '):</span>';
                Object.entries(barColorMap).forEach(([k, v]) => {
                    legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:20px;height:5px;background:' + v + ';border-radius:2px"></span>' + k + '</span>';
                });
            } else {
                legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:20px;height:5px;background:#93c5fd;border-radius:2px"></span>治疗用药</span>';
            }
        }
        if (showAssess) {
            Object.entries(responseColors).forEach(([k, v]) => { if (k) legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:12px;height:12px;background:' + v + ';transform:rotate(45deg);border-radius:1px"></span>' + k + '</span>'; });
        }
        if (showAE) {
            legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:20px;height:4px;background:#f97316;border-radius:2px"></span>AE</span>';
        }
        if (showStatus) {
            legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="color:#374151;font-size:14px">▶</span>在组治疗</span>';
            legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#374151"></span>随访中</span>';
            legendHtml += '<span style="display:flex;align-items:center;gap:4px"><span style="font-size:14px;color:#6b7280">×</span>死亡/失访</span>';
        }
        legendHtml += '</div>';
        const legendEl = document.createElement('div');
        legendEl.innerHTML = legendHtml;
        parentEl.appendChild(legendEl);

        this._registerResize(chart);
    },

    // ============ 5. 肿瘤指标趋势图 ============
    async loadTumorMarkerTrend() {
        await this.ensureECharts();
        if (!this.echarts) {
            document.getElementById('chartMarker').innerHTML = '<div class="chart-error">ECharts库加载失败<br><small>请检查网络连接后刷新页面</small></div>';
            return;
        }
        const projectId = Calendar.currentProject;
        if (!projectId) return;
        const container = document.getElementById('chartMarker');
        this._showLoading(container);

        if (!this.state.markerEventsBound) {
            this.state.markerEventsBound = true;
            const markerSel = document.getElementById('markerSelect');
            if (markerSel) markerSel.addEventListener('change', () => this.loadTumorMarkerTrend());
        }

        const markerSel = document.getElementById('markerSelect');
        const markerName = markerSel ? markerSel.value : 'CEA';
        try {
            const data = await api.getChartTumorMarkers(projectId, markerName);
            if (!data.length) { this._showEmpty(container); return; }
            // 销毁旧实例，防止内存泄漏
            if (this.state.markerChart) { this.state.markerChart.dispose(); this.state.markerChart = null; }
            const chart = this.echarts.init(container);
            this.state.markerChart = chart;
            const colorPalette = this.getColorPalette();
            chart.setOption({
                title: { text: '肿瘤指标趋势 - ' + markerName, left: 'center', textStyle: { fontSize: 14 } },
                tooltip: { trigger: 'item', formatter: function(p) { return p.seriesName + '<br/>第' + p.value[0] + '天<br/>' + markerName + ': ' + p.value[1]; } },
                legend: { bottom: 0, data: data.map(d => d.patient_id) },
                grid: { top: 50, bottom: 80, left: 80, right: 30 },
                xAxis: { type: 'value', name: '距首次检测天数', nameLocation: 'center', nameGap: 30 },
                yAxis: { type: 'value', name: markerName + ' 值' },
                series: data.map((d, i) => ({
                    name: d.patient_id, type: 'line',
                    data: d.points.map(p => [p.days, p.value]),
                    smooth: false, symbol: 'circle', symbolSize: 6,
                    lineStyle: { color: colorPalette[i % colorPalette.length] },
                    itemStyle: { color: colorPalette[i % colorPalette.length] },
                    markLine: d.points[0]?.upper_limit ? { silent: true, symbol: 'none', data: [{ yAxis: d.points[0].upper_limit, name: '正常上限', lineStyle: { color: '#D85A30', type: 'dashed' } }] } : undefined
                }))
            });
            this._registerResize(chart);
        } catch (e) {
            this._showError(container, '加载失败: ' + (e.message || e));
        }
    },

    // ============ 公共工具方法 ============

    /** 按配置的sort_order排序字符串数组（不缓存，每次从API获取最新顺序） */
    async _sortByConfigOrder(values, type) {
        // type: 'doseGroup' 或 'cancerType'
        const apiFn = type === 'doseGroup' ? api.getDoseGroups : api.getCancerTypes;
        let configList = [];
        try {
            configList = await apiFn(Calendar.currentProject);
        } catch (e) {
            configList = [];
        }
        const orderMap = {};
        configList.forEach((c, i) => { orderMap[c.name] = i; });
        return [...values].sort((a, b) => {
            const oa = orderMap[a] !== undefined ? orderMap[a] : 999;
            const ob = orderMap[b] !== undefined ? orderMap[b] : 999;
            return oa - ob;
        });
    },

    /** 填充筛选下拉框（剂量组 + 癌肿类型） */
    async _populateFilterSelects(data, groupSelectId, cancerSelectId) {
        const groups = await this._sortByConfigOrder([...new Set(data.map(d => d.dose_group).filter(Boolean))], 'doseGroup');
        const cancers = await this._sortByConfigOrder([...new Set(data.map(d => d.cancer_type).filter(Boolean))], 'cancerType');

        const groupSel = document.getElementById(groupSelectId);
        if (groupSel) {
            const currentVal = groupSel.value;
            groupSel.innerHTML = '<option value="">全部剂量组</option>' +
                groups.map(g => '<option value="' + g + '">' + g + '</option>').join('');
            if (currentVal && groups.includes(currentVal)) groupSel.value = currentVal;
        }

        const cancerSel = document.getElementById(cancerSelectId);
        if (cancerSel) {
            const currentVal = cancerSel.value;
            cancerSel.innerHTML = '<option value="">全部癌肿</option>' +
                cancers.map(c => '<option value="' + c + '">' + c + '</option>').join('');
            if (currentVal && cancers.includes(currentVal)) cancerSel.value = currentVal;
        }
    }
};

// ============ 配色方案切换 ============
(function() {
    const schemeSel = document.getElementById('colorScheme');
    if (!schemeSel) return;
    schemeSel.addEventListener('change', function() {
        const scheme = this.value;
        Charts._colorScheme = scheme;
        // 重绘当前可见的图表（直接渲染，不重新加载）
        const activeTab = document.querySelector('.main-tab.active');
        if (!activeTab) return;
        const tabName = activeTab.getAttribute('data-tab');
        switch (tabName) {
            case 'waterfall': Charts._renderWaterfallChart(); break;
            case 'swimmer': Charts._renderSwimmerChart(Charts.state.swimmerData); break;
            case 'spider': Charts._renderSpiderChart(); break;
            case 'tumorMarker': Charts.loadTumorMarkerTrend(); break;
        }
    });
})();

// 显式暴露到全局作用域，确保其他脚本可访问
window.Charts = Charts;
