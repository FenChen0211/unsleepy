let statusList = [];
let currentStatusId = -1;
let deviceData = {};
let privateMode = false;

// ========== Init ==========

async function init() {
    const resp = await fetch('/api/status/query');
    const data = await resp.json();
    currentStatusId = data.status.id;
    deviceData = data.device || {};
    privateMode = data.private_mode || false;

    const sl = await fetch('/api/status/list');
    const sld = await sl.json();
    statusList = sld.status_list || [];

    updateOverview();
    renderStatusSelector();

    if (document.getElementById('metrics-container')) fetchMetrics();
}

function updateOverview() {
    document.getElementById('ov-status').textContent = statusList[currentStatusId]
        ? statusList[currentStatusId].name : '未知';
    document.getElementById('ov-private').textContent = privateMode ? '已开启' : '已关闭';
    document.getElementById('ov-device-count').textContent = Object.keys(deviceData).length;
    fetch('/api/export/usage?per_page=1').then(r => r.json()).then(d => {
        document.getElementById('ov-log-count').textContent = d.total || 0;
    }).catch(() => {});
}

// ========== Tab Switching ==========

document.addEventListener('DOMContentLoaded', function () {
    const nav = document.getElementById('sidebar-nav');
    nav.querySelectorAll('li').forEach(li => {
        li.addEventListener('click', function () {
            nav.querySelectorAll('li').forEach(l => l.classList.remove('active'));
            this.classList.add('active');
            const tab = this.dataset.tab;
            document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
            const el = document.getElementById('tab-' + tab);
            if (el) el.classList.add('active');
            loadTab(tab);
        });
    });

    document.getElementById('logout-btn').addEventListener('click', function () {
        localStorage.removeItem('sleepy_secret');
        window.location.href = '/panel/logout';
    });

    document.getElementById('clear-devices-btn').addEventListener('click', clearDevices);
    document.getElementById('refresh-devices-btn').addEventListener('click', loadDevices);

    document.getElementById('private-mode-toggle').addEventListener('change', function () {
        togglePrivateMode(this.checked);
    });

    document.getElementById('toggles-save-btn').addEventListener('click', saveToggles);
    document.getElementById('config-save-btn').addEventListener('click', saveConfig);
    document.getElementById('cat-add-btn').addEventListener('click', addCategory);
    document.getElementById('logs-refresh-btn').addEventListener('click', loadLogs);
    document.getElementById('logs-clear-btn').addEventListener('click', clearLogs);

    init();
});

function loadTab(tab) {
    switch (tab) {
        case 'devices': loadDevices(); break;
        case 'toggles': loadToggles(); break;
        case 'config': loadConfig(); break;
        case 'categories': loadCategories(); break;
        case 'logs': loadLogs(); break;
    }
}

// ========== Status ==========

function renderStatusSelector() {
    const c = document.getElementById('status-selector');
    c.innerHTML = '';
    statusList.forEach(function (s, i) {
        const d = document.createElement('div');
        d.className = 'status-item' + (i === currentStatusId ? ' active' : '');
        d.style.backgroundColor = s.color === 'awake' ? 'rgba(0,200,0,0.2)'
            : s.color === 'error' ? 'rgba(255,0,0,0.2)' : 'rgba(128,128,128,0.2)';
        d.textContent = s.name;
        d.addEventListener('click', function () { setStatus(i); });
        c.appendChild(d);
    });
}

async function setStatus(idx) {
    const r = await fetch('/api/status/set?status=' + idx);
    const d = await r.json();
    if (d.success) { currentStatusId = idx; renderStatusSelector(); updateOverview(); }
}

// ========== Devices ==========

async function loadDevices() {
    const r = await fetch('/api/status/query');
    const d = await r.json();
    deviceData = d.device || {};
    privateMode = d.private_mode || false;
    updateOverview();
    renderDeviceTable();
    document.getElementById('private-mode-toggle').checked = privateMode;
}

function renderDeviceTable() {
    const tbody = document.getElementById('device-list-body');
    const keys = Object.keys(deviceData);
    if (keys.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading-text">暂无设备</td></tr>';
        return;
    }
    tbody.innerHTML = keys.map(function (id) {
        const dev = deviceData[id];
        return '<tr>' +
            '<td>' + esc(id) + '</td>' +
            '<td>' + esc(dev.show_name || id) + '</td>' +
            '<td>' + esc(dev.status || '-') + '</td>' +
            '<td>' + (dev.using ? '<span style="color:#40c463;">使用中</span>' : '<span style="color:var(--text-muted);">空闲</span>') + '</td>' +
            '<td><button class="btn btn-danger" style="font-size:0.8em;padding:2px 8px;" onclick="panelRemoveDevice(\'' + esc(id) + '\')">删除</button></td>' +
            '</tr>';
    }).join('');
}

window.panelRemoveDevice = async function (id) {
    if (!confirm('确定删除设备 "' + id + '" 吗？')) return;
    await fetch('/api/device/remove?id=' + encodeURIComponent(id));
    loadDevices();
};

async function clearDevices() {
    if (!confirm('确定清除所有设备？此操作不可撤销！')) return;
    await fetch('/api/device/clear');
    loadDevices();
}

async function togglePrivateMode(on) {
    await fetch('/api/device/private?private=' + (on ? '1' : '0'));
    loadDevices();
}

// ========== Display Toggles ==========

async function loadToggles() {
    const r = await fetch('/api/settings/toggles');
    const d = await r.json();
    const t = d.toggles || {};
    const list = document.getElementById('toggle-list');
    list.innerHTML = [
        { key: 'show_current_status', name: '当前状态卡片', desc: '显示设备实时状态和支持的状态切换（核心功能，建议始终开启）' },
        { key: 'show_today_usage', name: '使用时长列表', desc: '显示今日/本周/本月各应用使用时长排行和百分比' },
        { key: 'show_category_chart', name: '分类占比饼图', desc: '在统计卡片中展示应用类型占比的环形图' },
        { key: 'show_heatmap', name: '活跃热力图', desc: '以 GitHub 贡献图风格的日历热力图展示过去 N 天的活跃程度。需后台配置且需有使用数据才会出现颜色格子' },
        { key: 'show_focus_mode', name: '专注模式', desc: '显示番茄钟计时器，可开始/结束专注会话，记录专注时长' },
        { key: 'show_llm_insight', name: 'AI 分析洞察', desc: '调用 LLM 对使用数据给出简短分析建议。需先在 config.yaml 中配置 api_key 才能启用' },
    ].map(function (item) {
        return '<div class="toggle-row">' +
            '<label class="toggle-switch">' +
            '<input type="checkbox" data-key="' + item.key + '"' + (t[item.key] ? ' checked' : '') + ' />' +
            '<span class="toggle-slider"></span>' +
            '</label>' +
            '<div>' +
            '<span style="font-weight: 600;">' + item.name + '</span>' +
            '<div class="toggle-desc">' + item.desc + '</div>' +
            '</div>' +
            '</div>';
    }).join('');
}

async function saveToggles() {
    const payload = {};
    document.querySelectorAll('#toggle-list input[type=checkbox]').forEach(function (cb) {
        payload[cb.dataset.key] = cb.checked;
    });
    const r = await fetch('/api/settings/toggles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const d = await r.json();
    const msg = document.getElementById('toggles-save-msg');
    msg.textContent = d.success ? '已保存' : '保存失败';
    msg.style.color = d.success ? 'var(--accent)' : 'var(--color-error)';
    setTimeout(function () { msg.textContent = ''; }, 2000);
}

// ========== User Config ==========

async function loadConfig() {
    const r = await fetch('/api/settings/user_config');
    const d = await r.json();
    const c = d.config || {};
    const list = document.getElementById('config-list');
    list.innerHTML = [
        { key: 'focus_default_minutes', name: '专注默认时长（分钟）', desc: '点击"开始专注"时的默认番茄钟时长，范围 1-120', val: c.focus_default_minutes || 25, min: 1, max: 120 },
        { key: 'heatmap_default_days', name: '热力图默认展示天数', desc: '打开热力图时默认展示最近多少天的数据，范围 7-365', val: c.heatmap_default_days || 90, min: 7, max: 365 },
        { key: 'llm_max_analysis_days', name: 'LLM 最大分析天数', desc: 'AI 分析最多回溯多少天的使用数据，防止超长 prompt 浪费 Token，范围 1-90', val: c.llm_max_analysis_days || 14, min: 1, max: 90 },
    ].map(function (item) {
        return '<div class="config-row">' +
            '<label>' + item.name + '</label>' +
            '<input type="number" data-key="' + item.key + '" value="' + item.val + '" min="' + item.min + '" max="' + item.max + '" />' +
            '<span class="config-desc">' + item.desc + '</span>' +
            '</div>';
    }).join('');
    list.innerHTML += '<div class="config-row">' +
        '<label>浏览器窗口标题合并</label>' +
        '<label class="toggle-switch">' +
        '<input type="checkbox" data-key="browser_normalize"' + (c.browser_normalize ? ' checked' : '') + ' />' +
        '<span class="toggle-slider"></span>' +
        '</label>' +
        '<span class="config-desc">开启后，"GitHub - Microsoft Edge" 之类带标签页标题的浏览器名会自动合并为 "Microsoft Edge"</span>' +
        '</div>';
}

async function saveConfig() {
    const payload = {};
    document.querySelectorAll('#config-list input[type=number]').forEach(function (inp) {
        payload[inp.dataset.key] = parseInt(inp.value) || 0;
    });
    document.querySelectorAll('#config-list input[type=checkbox]').forEach(function (cb) {
        payload[cb.dataset.key] = cb.checked;
    });
    const r = await fetch('/api/settings/user_config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const msg = document.getElementById('config-save-msg');
    if (r.ok) {
        msg.textContent = '已保存';
        msg.style.color = 'var(--accent)';
    } else {
        msg.textContent = '保存失败';
        msg.style.color = 'var(--color-error)';
    }
    setTimeout(function () { msg.textContent = ''; }, 2000);
}

// ========== App Categories ==========

async function loadCategories() {
    try {
        const r = await fetch('/panel/categories/list');
        const d = await r.json();
        renderCatTable(d.categories || []);
    } catch (e) {
        renderCatTable([]);
    }
}

function renderCatTable(cats) {
    const tbody = document.getElementById('cat-list-body');
    if (!cats || cats.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="loading-text">暂无分类规则。添加第一条规则后即可生效</td></tr>';
        return;
    }
    tbody.innerHTML = cats.map(function (c) {
        return '<tr>' +
            '<td>' + esc(c.pattern) + '</td>' +
            '<td>' + esc(c.category) + '</td>' +
            '<td><span style="display:inline-block;width:16px;height:16px;background:' + (c.color || '#5470c6') + ';border-radius:4px;vertical-align:middle;"></span> ' + esc(c.color) + '</td>' +
            '<td><button class="btn btn-danger" style="font-size:0.8em;padding:2px 8px;" onclick="panelDeleteCat(' + c.id + ')">删除</button></td>' +
            '</tr>';
    }).join('');
}

window.panelDeleteCat = async function (id) {
    if (!confirm('确定删除此分类规则？')) return;
    await fetch('/panel/category/delete?id=' + id, { method: 'POST' });
    loadCategories();
};

async function addCategory() {
    const pattern = document.getElementById('cat-pattern').value.trim();
    const label = document.getElementById('cat-label').value.trim();
    const color = document.getElementById('cat-color').value;
    if (!pattern || !label) { alert('请填写关键词和分类标签'); return; }
    const r = await fetch('/panel/category/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pattern: pattern, category: label, color: color })
    });
    const d = await r.json();
    const msg = document.getElementById('cat-add-msg');
    msg.textContent = d.success ? '已添加' : (d.message || '失败');
    msg.style.color = d.success ? 'var(--accent)' : 'var(--color-error)';
    if (d.success) {
        document.getElementById('cat-pattern').value = '';
        document.getElementById('cat-label').value = '';
        loadCategories();
    }
    setTimeout(function () { msg.textContent = ''; }, 2000);
}

// ========== Usage Logs ==========

async function loadLogs() {
    const r = await fetch('/api/export/usage?per_page=50');
    const d = await r.json();
    const records = d.records || [];
    document.getElementById('logs-count').textContent = '共 ' + d.total + ' 条记录';
    const tbody = document.getElementById('logs-list-body');
    if (records.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="loading-text">暂无使用记录。客户端开始推送状态后自动记录</td></tr>';
        return;
    }
    tbody.innerHTML = records.map(function (r) {
        var dur = '';
        if (r.duration) {
            var h = Math.floor(r.duration / 3600);
            var m = Math.floor((r.duration % 3600) / 60);
            dur = h > 0 ? h + 'h ' + m + 'm' : m + 'm';
        }
        return '<tr>' +
            '<td style="white-space:nowrap;font-size:0.85em;">' + (r.timestamp || '').replace('T', ' ').slice(0, 19) + '</td>' +
            '<td>' + esc(r.app_name) + '</td>' +
            '<td>' + esc(r.device_name) + '</td>' +
            '<td>' + (dur || '-') + '</td>' +
            '</tr>';
    }).join('');
}

async function clearLogs() {
    if (!confirm('确定清除所有使用记录？此操作不可撤销！')) return;
    await fetch('/panel/logs/clear', { method: 'POST' });
    loadLogs();
}

// ========== Metrics ==========

async function fetchMetrics() {
    try {
        const r = await fetch('/api/metrics');
        const d = await r.json();
        const c = document.getElementById('metrics-container');
        c.innerHTML = '';
        function card(label, val) {
            return '<div class="metric-card"><div class="metric-value">' + val + '</div><div class="metric-label">' + label + '</div></div>';
        }
        if (d.daily) c.innerHTML += card('今日首页', d.daily['/'] || 0);
        if (d.weekly) c.innerHTML += card('本周首页', d.weekly['/'] || 0);
        if (d.monthly) c.innerHTML += card('本月首页', d.monthly['/'] || 0);
        if (d.yearly) c.innerHTML += card('本年首页', d.yearly['/'] || 0);
        if (d.total) c.innerHTML += card('总访问', d.total['/'] || 0);
    } catch (e) {
        document.getElementById('metrics-container').innerHTML = '<p style="color:var(--text-muted);">获取统计数据失败</p>';
    }
}

// ========== Helpers ==========

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
