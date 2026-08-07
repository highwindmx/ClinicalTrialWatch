/**
 * API 封装模块
 * 所有后端请求统一走这里
 */

const API_BASE = '/api';

/** 统一响应处理：检查HTTP状态码 + 响应体中的 error 字段 */
async function checkResponse(r) {
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
        throw new Error(data.error || `请求失败 (HTTP ${r.status})`);
    }
    if (data.error) {
        throw new Error(data.error);
    }
    return data;
}

const api = {
    // ==================== 项目 ====================
    getProjects() {
        return fetch(`${API_BASE}/projects`).then(checkResponse);
    },
    getProject(id) {
        return fetch(`${API_BASE}/projects/${id}`).then(checkResponse);
    },
    createProject(data) {
        return fetch(`${API_BASE}/projects`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    updateProject(id, data) {
        return fetch(`${API_BASE}/projects/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    deleteProject(id) {
        return fetch(`${API_BASE}/projects/${id}`, { method: 'DELETE' }).then(checkResponse);
    },

    // ==================== 患者 ====================
    getPatients(projectId) {
        return fetch(`${API_BASE}/patients?project_id=${projectId}`).then(checkResponse);
    },
    getPatient(id) {
        return fetch(`${API_BASE}/patients/${id}`).then(checkResponse);
    },
    createPatient(data) {
        return fetch(`${API_BASE}/patients`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    updatePatient(id, data) {
        return fetch(`${API_BASE}/patients/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    deletePatient(id) {
        return fetch(`${API_BASE}/patients/${id}`, { method: 'DELETE' }).then(checkResponse);
    },

    // ==================== 用药 ====================
    getMedications(patientId) {
        return fetch(`${API_BASE}/patients/${patientId}/medications`).then(checkResponse);
    },
    createMedication(patientId, data) {
        return fetch(`${API_BASE}/patients/${patientId}/medications`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    updateMedication(id, data) {
        return fetch(`${API_BASE}/medications/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    deleteMedication(id) {
        return fetch(`${API_BASE}/medications/${id}`, { method: 'DELETE' }).then(checkResponse);
    },

    // ==================== 肿瘤评估 ====================
    getTumorAssessments(patientId) {
        return fetch(`${API_BASE}/patients/${patientId}/tumor-assessments`).then(checkResponse);
    },
    createTumorAssessment(patientId, data) {
        return fetch(`${API_BASE}/patients/${patientId}/tumor-assessments`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    updateTumorAssessment(id, data) {
        return fetch(`${API_BASE}/tumor-assessments/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    deleteTumorAssessment(id) {
        return fetch(`${API_BASE}/tumor-assessments/${id}`, { method: 'DELETE' }).then(checkResponse);
    },

    // ==================== 不良事件 ====================
    getAdverseEvents(patientId) {
        return fetch(`${API_BASE}/patients/${patientId}/adverse-events`).then(checkResponse);
    },
    getProjectAdverseEvents(projectId) {
        return fetch(`${API_BASE}/projects/${projectId}/adverse-events`).then(checkResponse);
    },
    createAdverseEvent(patientId, data) {
        return fetch(`${API_BASE}/patients/${patientId}/adverse-events`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    updateAdverseEvent(id, data) {
        return fetch(`${API_BASE}/adverse-events/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    deleteAdverseEvent(id) {
        return fetch(`${API_BASE}/adverse-events/${id}`, { method: 'DELETE' }).then(checkResponse);
    },

    // ==================== PK数据 ====================
    getPkData(patientId) {
        return fetch(`${API_BASE}/patients/${patientId}/pk-data`).then(checkResponse);
    },
    createPkData(patientId, data) {
        return fetch(`${API_BASE}/patients/${patientId}/pk-data`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    updatePkData(id, data) {
        return fetch(`${API_BASE}/pk-data/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    deletePkData(id) {
        return fetch(`${API_BASE}/pk-data/${id}`, { method: 'DELETE' }).then(checkResponse);
    },

    // ==================== 肿瘤指标 ====================
    getTumorMarkers(patientId) {
        return fetch(`${API_BASE}/patients/${patientId}/tumor-markers`).then(checkResponse);
    },
    createTumorMarker(patientId, data) {
        return fetch(`${API_BASE}/patients/${patientId}/tumor-markers`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    updateTumorMarker(id, data) {
        return fetch(`${API_BASE}/tumor-markers/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    deleteTumorMarker(id) {
        return fetch(`${API_BASE}/tumor-markers/${id}`, { method: 'DELETE' }).then(checkResponse);
    },

    // ==================== 自定义列 ====================
    getCustomColumns(projectId, module) {
        const url = module ? `${API_BASE}/projects/${projectId}/custom-columns?module=${module}` : `${API_BASE}/projects/${projectId}/custom-columns`;
        return fetch(url).then(checkResponse);
    },
    createCustomColumn(projectId, data) {
        return fetch(`${API_BASE}/projects/${projectId}/custom-columns`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    deleteCustomColumn(id) {
        return fetch(`${API_BASE}/custom-columns/${id}`, { method: 'DELETE' }).then(checkResponse);
    },

    // ==================== 甘特图 ====================
    getGanttData(projectId, zoomLevel, dateStr) {
        return fetch(`${API_BASE}/gantt?project_id=${projectId}&zoom=${zoomLevel}&date=${dateStr}`).then(checkResponse);
    },
    getGanttFullData(projectId) {
        return fetch(`${API_BASE}/gantt-full?project_id=${projectId}`).then(checkResponse);
    },

    // ==================== 图表 ====================
    getChartBaseline(projectId) {
        return fetch(`${API_BASE}/charts/baseline/${projectId}`).then(checkResponse);
    },
    getChartWaterfall(projectId) {
        return fetch(`${API_BASE}/charts/waterfall/${projectId}`).then(checkResponse);
    },
    getChartSwimmer(projectId) {
        return fetch(`${API_BASE}/charts/swimmer/${projectId}`).then(checkResponse);
    },
    getChartSpider(projectId) {
        return fetch(`${API_BASE}/charts/spider/${projectId}`).then(checkResponse);
    },
    getChartTumorMarkers(projectId, marker) {
        return fetch(`${API_BASE}/charts/tumor-markers/${projectId}?marker=${marker || 'CEA'}`).then(checkResponse);
    },

    // ==================== 剂量组 ====================
    getDoseGroups(projectId) {
        return fetch(`${API_BASE}/projects/${projectId}/dose-groups`).then(checkResponse);
    },
    createDoseGroup(projectId, data) {
        return fetch(`${API_BASE}/projects/${projectId}/dose-groups`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    updateDoseGroup(id, data) {
        return fetch(`${API_BASE}/dose-groups/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    deleteDoseGroup(id) {
        return fetch(`${API_BASE}/dose-groups/${id}`, { method: 'DELETE' }).then(checkResponse);
    },

    // ==================== 癌肿类型 ====================
    getCancerTypes(projectId) {
        return fetch(`${API_BASE}/projects/${projectId}/cancer-types`).then(checkResponse);
    },
    createCancerType(projectId, data) {
        return fetch(`${API_BASE}/projects/${projectId}/cancer-types`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    updateCancerType(id, data) {
        return fetch(`${API_BASE}/cancer-types/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
        }).then(checkResponse);
    },
    deleteCancerType(id) {
        return fetch(`${API_BASE}/cancer-types/${id}`, { method: 'DELETE' }).then(checkResponse);
    },

    // ==================== Demo数据 ====================
    generateDemoData(projectId) {
        return fetch(`${API_BASE}/projects/${projectId}/demo-data`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}
        }).then(r => {
            if (!r.ok) return r.json().then(e => Promise.reject(e));
            return r.json();
        });
    },

    // ==================== 导入导出 ====================
    exportExcel(projectId) {
        window.open(`${API_BASE}/export/${projectId}`, '_blank');
    },
    async importExcel(projectId, file) {
        const formData = new FormData();
        formData.append('file', file);
        const resp = await fetch(`${API_BASE}/import/${projectId}`, {
            method: 'POST', body: formData
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error || `导入失败 (HTTP ${resp.status})`);
        if (data.error) throw new Error(data.error);
        return data;
    }
};
