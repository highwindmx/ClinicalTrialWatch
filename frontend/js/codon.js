/**
 * 遗传密码表（标准通用密码子表）
 * 静态数据，无需后端。DNA 编码链 = RNA 将 U 换 T。
 * 渲染到 index.html 的 #panel-codon 面板。
 */

// 氨基酸信息：单字母 -> {三字母, 英文名, 中文名}
const AA_INFO = {
    'F': { three: 'Phe', full: 'Phenylalanine', cn: '苯丙氨酸' },
    'L': { three: 'Leu', full: 'Leucine', cn: '亮氨酸' },
    'I': { three: 'Ile', full: 'Isoleucine', cn: '异亮氨酸' },
    'M': { three: 'Met', full: 'Methionine', cn: '甲硫氨酸' },
    'V': { three: 'Val', full: 'Valine', cn: '缬氨酸' },
    'S': { three: 'Ser', full: 'Serine', cn: '丝氨酸' },
    'P': { three: 'Pro', full: 'Proline', cn: '脯氨酸' },
    'T': { three: 'Thr', full: 'Threonine', cn: '苏氨酸' },
    'A': { three: 'Ala', full: 'Alanine', cn: '丙氨酸' },
    'Y': { three: 'Tyr', full: 'Tyrosine', cn: '酪氨酸' },
    '*': { three: 'Stop', full: 'Stop codon', cn: '终止' },
    'H': { three: 'His', full: 'Histidine', cn: '组氨酸' },
    'Q': { three: 'Gln', full: 'Glutamine', cn: '谷氨酰胺' },
    'N': { three: 'Asn', full: 'Asparagine', cn: '天冬酰胺' },
    'K': { three: 'Lys', full: 'Lysine', cn: '赖氨酸' },
    'D': { three: 'Asp', full: 'Aspartic acid', cn: '天冬氨酸' },
    'E': { three: 'Glu', full: 'Glutamic acid', cn: '谷氨酸' },
    'C': { three: 'Cys', full: 'Cysteine', cn: '半胱氨酸' },
    'W': { three: 'Trp', full: 'Tryptophan', cn: '色氨酸' },
    'R': { three: 'Arg', full: 'Arginine', cn: '精氨酸' },
    'G': { three: 'Gly', full: 'Glycine', cn: '甘氨酸' }
};

// 64 个标准密码子：[RNA三联体, 氨基酸单字母, 是否起始密码子]
const CODONS = [
    ['UUU', 'F', false], ['UUC', 'F', false], ['UUA', 'L', false], ['UUG', 'L', false],
    ['UCU', 'S', false], ['UCC', 'S', false], ['UCA', 'S', false], ['UCG', 'S', false],
    ['UAU', 'Y', false], ['UAC', 'Y', false], ['UAA', '*', false], ['UAG', '*', false],
    ['UGU', 'C', false], ['UGC', 'C', false], ['UGA', '*', false], ['UGG', 'W', false],
    ['CUU', 'L', false], ['CUC', 'L', false], ['CUA', 'L', false], ['CUG', 'L', false],
    ['CCU', 'P', false], ['CCC', 'P', false], ['CCA', 'P', false], ['CCG', 'P', false],
    ['CAU', 'H', false], ['CAC', 'H', false], ['CAA', 'Q', false], ['CAG', 'Q', false],
    ['CGU', 'R', false], ['CGC', 'R', false], ['CGA', 'R', false], ['CGG', 'R', false],
    ['AUU', 'I', false], ['AUC', 'I', false], ['AUA', 'I', false], ['AUG', 'M', true],
    ['ACU', 'T', false], ['ACC', 'T', false], ['ACA', 'T', false], ['ACG', 'T', false],
    ['AAU', 'N', false], ['AAC', 'N', false], ['AAA', 'K', false], ['AAG', 'K', false],
    ['AGU', 'S', false], ['AGC', 'S', false], ['AGA', 'R', false], ['AGG', 'R', false],
    ['GUU', 'V', false], ['GUC', 'V', false], ['GUA', 'V', false], ['GUG', 'V', false],
    ['GCU', 'A', false], ['GCC', 'A', false], ['GCA', 'A', false], ['GCG', 'A', false],
    ['GAU', 'D', false], ['GAC', 'D', false], ['GAA', 'E', false], ['GAG', 'E', false],
    ['GGU', 'G', false], ['GGC', 'G', false], ['GGA', 'G', false], ['GGG', 'G', false]
];

const CodonTable = {
    render() {
        const search = document.getElementById('codonSearch');
        const onlyStart = document.getElementById('codonOnlyStart');
        const onlyStop = document.getElementById('codonOnlyStop');
        if (search && !search._bound) {
            search.addEventListener('input', () => this.draw());
            onlyStart.addEventListener('change', () => this.draw());
            onlyStop.addEventListener('change', () => this.draw());
            search._bound = true;
        }
        this.draw();
    },

    draw() {
        const tbody = document.getElementById('codonTableBody');
        if (!tbody) return;
        const q = (document.getElementById('codonSearch').value || '').trim().toLowerCase();
        const onlyStart = document.getElementById('codonOnlyStart').checked;
        const onlyStop = document.getElementById('codonOnlyStop').checked;

        const rows = CODONS.filter(([rna, aa, isStart]) => {
            const isStop = aa === '*';
            if (onlyStart && !isStart) return false;
            if (onlyStop && !isStop) return false;
            if (q) {
                const dna = rna.replace(/U/g, 'T');
                const info = AA_INFO[aa];
                const hay = [rna, dna, aa, info.three, info.full, info.cn].join(' ').toLowerCase();
                if (!hay.includes(q)) return false;
            }
            return true;
        });

        tbody.innerHTML = rows.map(([rna, aa, isStart]) => {
            const isStop = aa === '*';
            const info = AA_INFO[aa];
            const dna = rna.replace(/U/g, 'T');
            const cls = isStart ? 'codon-row start' : (isStop ? 'codon-row stop' : 'codon-row');
            const note = isStart
                ? '<span class="codon-badge start">起始</span>'
                : (isStop ? '<span class="codon-badge stop">终止</span>' : '<span style="color:#9ca3af">—</span>');
            return '<tr class="' + cls + '">'
                + '<td class="dna">' + dna + '</td>'
                + '<td class="rna">' + rna + '</td>'
                + '<td><b>' + (aa === '*' ? '—' : aa) + '</b></td>'
                + '<td>' + info.three + '</td>'
                + '<td>' + info.cn + '</td>'
                + '<td>' + note + '</td>'
                + '</tr>';
        }).join('');

        const count = document.getElementById('codonCount');
        if (count) count.textContent = '共 ' + rows.length + ' / 64 个密码子';
    }
};

window.CodonTable = CodonTable;
