/* 计算工具页 —— 常见临床/药学计算
 * 首期实现：时间间隔计算（CXDY <-> 日期）
 * 设计上可扩展：后续可在 calcSubtabs 增加子项并注册对应渲染函数。
 */
window.CalcApp = (function () {
    'use strict';

    /* ---------- 解析与格式化 ---------- */
    function parseDate(str) {
        if (!str) return null;
        const m = String(str).trim().match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
        if (!m) return null;
        const y = +m[1], mo = +m[2], d = +m[3];
        const dt = new Date(y, mo - 1, d);
        if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
        return dt;
    }
    function fmtDate(dt) {
        const y = dt.getFullYear();
        const mo = String(dt.getMonth() + 1).padStart(2, '0');
        const d = String(dt.getDate()).padStart(2, '0');
        return y + '-' + mo + '-' + d;
    }
    function parseCxdy(str) {
        if (!str) return null;
        const m = String(str).trim().toUpperCase().match(/^C\s*(\d+)\s*D\s*(\d+)$/);
        if (!m) return null;
        return { cycle: +m[1], day: +m[2] };
    }
    function fmtCxdy(c, d) { return 'C' + c + 'D' + d; }

    /* ---------- 天数运算（按日历日，忽略时区） ---------- */
    function diffDays(a, b) {
        const ms = Date.UTC(b.getFullYear(), b.getMonth(), b.getDate())
                 - Date.UTC(a.getFullYear(), a.getMonth(), a.getDate());
        return Math.round(ms / 86400000);
    }
    function addDays(dt, n) {
        const r = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
        r.setDate(r.getDate() + n);
        return r;
    }
    /* CXDY -> 相对 C1D1 的天数偏移（含负数，支持跨周期归一） */
    function cxdyToOffset(cycle, day, L) {
        return (cycle - 1) * L + (day - 1);
    }
    function offsetToCxdy(offset, L) {
        const cycle = Math.floor(offset / L) + 1;
        const day = ((offset % L) + L) % L + 1; // 负数取模归一化
        return { cycle: cycle, day: day };
    }

    /* ---------- 共享输入读取 ---------- */
    function readShared() {
        const start = parseDate(document.getElementById('calcStart').value);
        const startC = parseCxdy(document.getElementById('calcStartC').value);
        const L = parseInt(document.getElementById('calcInterval').value, 10);
        const errs = [];
        if (!start) errs.push('起始日期格式不正确（应为 yyyy-mm-dd）');
        if (!startC) errs.push('起始周期格式不正确（应为 CXDY，如 C1D1）');
        if (!(L >= 1)) errs.push('周期间隔必须为正整数');
        return { start: start, startC: startC, L: L, errs: errs };
    }

    /* ---------- 模式A：日期 -> 周期号 ---------- */
    function calcA() {
        const box = document.getElementById('calcResultA');
        const s = readShared();
        if (s.errs.length) { box.innerHTML = '<span class="calc-err">' + s.errs.join('；') + '</span>'; return; }
        const target = parseDate(document.getElementById('calcTargetDate').value);
        if (!target) { box.innerHTML = '<span class="calc-err">期望日期格式不正确（应为 yyyy-mm-dd）</span>'; return; }
        const startOffset = cxdyToOffset(s.startC.cycle, s.startC.day, s.L);
        const delta = diffDays(s.start, target);
        const targetOffset = startOffset + delta;
        const cd = offsetToCxdy(targetOffset, s.L);
        const note = (targetOffset < 0) ? '（在起始周期之前）' : '';
        box.innerHTML = '<div class="calc-out"><span class="calc-big">' + fmtCxdy(cd.cycle, cd.day) + '</span>' +
            '<span class="calc-sub">距起始 ' + (delta >= 0 ? '+' : '') + delta + ' 天' + note + '</span></div>';
    }

    /* ---------- 模式B：周期号 -> 日期 ---------- */
    function calcB() {
        const box = document.getElementById('calcResultB');
        const s = readShared();
        if (s.errs.length) { box.innerHTML = '<span class="calc-err">' + s.errs.join('；') + '</span>'; return; }
        const targetC = parseCxdy(document.getElementById('calcTargetC').value);
        if (!targetC) { box.innerHTML = '<span class="calc-err">期望周期格式不正确（应为 CXDY，如 C4D8）</span>'; return; }
        const startOffset = cxdyToOffset(s.startC.cycle, s.startC.day, s.L);
        const targetOffset = cxdyToOffset(targetC.cycle, targetC.day, s.L);
        const delta = targetOffset - startOffset;
        const targetDate = addDays(s.start, delta);
        box.innerHTML = '<div class="calc-out"><span class="calc-big">' + fmtDate(targetDate) + '</span>' +
            '<span class="calc-sub">距起始 ' + (delta >= 0 ? '+' : '') + delta + ' 天</span></div>';
    }

    /* ---------- 模式C：间隔天数 -> 日期+周期号 ---------- */
    function calcC() {
        const box = document.getElementById('calcResultC');
        const s = readShared();
        if (s.errs.length) { box.innerHTML = '<span class="calc-err">' + s.errs.join('；') + '</span>'; return; }
        const gapRaw = document.getElementById('calcGap').value;
        const gap = parseInt(gapRaw, 10);
        if (isNaN(gap)) { box.innerHTML = '<span class="calc-err">间隔天数必须为整数</span>'; return; }
        const startOffset = cxdyToOffset(s.startC.cycle, s.startC.day, s.L);
        const targetOffset = startOffset + gap;
        const targetDate = addDays(s.start, gap);
        const cd = offsetToCxdy(targetOffset, s.L);
        const note = (gap < 0) ? '（在起始周期之前）' : '';
        box.innerHTML = '<div class="calc-out"><span class="calc-big">' + fmtDate(targetDate) + ' · ' + fmtCxdy(cd.cycle, cd.day) + '</span>' +
            '<span class="calc-sub">距起始 ' + (gap >= 0 ? '+' : '') + gap + ' 天' + note + '</span></div>';
    }

    /* ---------- 渲染 ---------- */
    function renderBody() {
        const body = document.getElementById('calcBody');
        if (!body) return;
        body.innerHTML =
            '<div class="calc-wrap">' +
                '<p class="calc-desc">以「起始日期 + 起始周期(CXDY)」为锚点，按周期间隔推算目标日期的周期号或反之。CXDY 形如 <b>C1D1</b>（第 1 周期第 1 天）；周期长度通常 21 天（Q3W）。输入的周期天数若超过间隔会自动跨周期归一。</p>' +
                '<div class="calc-shared">' +
                    '<div class="calc-field"><label>起始日期</label><input type="date" id="calcStart" class="form-input"></div>' +
                    '<div class="calc-field"><label>起始周期 (CXDY)</label><input type="text" id="calcStartC" class="form-input" placeholder="如 C1D1" style="width:120px"></div>' +
                    '<div class="calc-field"><label>周期间隔 (天)</label><input type="number" id="calcInterval" class="form-input" value="21" min="1" style="width:110px"></div>' +
                '</div>' +
                '<div class="calc-grid">' +
                    '<div class="calc-card">' +
                        '<h4 class="calc-card-title">① 日期 → 周期号</h4>' +
                        '<div class="calc-field"><label>期望日期</label><input type="date" id="calcTargetDate" class="form-input"></div>' +
                        '<button class="btn btn-primary btn-sm" id="calcBtnA">计算周期号</button>' +
                        '<div class="calc-result" id="calcResultA"></div>' +
                    '</div>' +
                    '<div class="calc-card">' +
                        '<h4 class="calc-card-title">② 周期号 → 日期</h4>' +
                        '<div class="calc-field"><label>期望周期 (CXDY)</label><input type="text" id="calcTargetC" class="form-input" placeholder="如 C4D8" style="width:120px"></div>' +
                        '<button class="btn btn-primary btn-sm" id="calcBtnB">计算日期</button>' +
                        '<div class="calc-result" id="calcResultB"></div>' +
                    '</div>' +
                    '<div class="calc-card">' +
                        '<h4 class="calc-card-title">③ 间隔天数 → 日期+周期</h4>' +
                        '<div class="calc-field"><label>间隔天数（可负）</label><input type="number" id="calcGap" class="form-input" placeholder="如 70" style="width:120px"></div>' +
                        '<button class="btn btn-primary btn-sm" id="calcBtnC">计算</button>' +
                        '<div class="calc-result" id="calcResultC"></div>' +
                    '</div>' +
                '</div>' +
            '</div>';
        document.getElementById('calcBtnA').onclick = calcA;
        document.getElementById('calcBtnB').onclick = calcB;
        document.getElementById('calcBtnC').onclick = calcC;
    }

    function bindSubtabs() {
        const tabs = document.getElementById('calcSubtabs');
        if (!tabs) return;
        tabs.querySelectorAll('.calc-subtab').forEach(function (btn) {
            btn.onclick = function () {
                tabs.querySelectorAll('.calc-subtab').forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                renderBody();
            };
        });
    }

    function render() {
        bindSubtabs();
        renderBody();
    }

    return { render: render };
})();
