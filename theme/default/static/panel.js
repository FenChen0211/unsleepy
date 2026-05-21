let statusList = [];
let currentStatusId = -1;
let deviceData = {};
let privateMode = false;
const panelSecret = new URLSearchParams(window.location.search).get('secret') || localStorage.getItem('sleepy_secret') || '';

function protectedUrl(url) {
    if (!panelSecret) return url;
    const joiner = url.indexOf('?') === -1 ? '?' : '&';
    return url + joiner + 'secret=' + encodeURIComponent(panelSecret);
}

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
    fetch(protectedUrl('/api/export/usage?per_page=1')).then(r => r.json()).then(d => {
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
    document.getElementById('status-text-save-btn').addEventListener('click', saveStatusTexts);
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
        case 'status-texts': loadStatusTexts(); break;
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
    const r = await fetch(protectedUrl('/api/status/set?status=' + idx));
    const d = await r.json();
    if (d.success) { currentStatusId = idx; renderStatusSelector(); updateOverview(); }
}

// ========== Status Texts ==========

async function loadStatusTexts() {
    const r = await fetch(protectedUrl('/panel/status-texts'));
    const d = await r.json();
    const list = document.getElementById('status-text-list');
    const statuses = d.status_list || [];
    if (!statuses.length) {
        list.innerHTML = '<div class="loading-text">暂无可编辑状态</div>';
        return;
    }

    list.innerHTML = statuses.map(function (s) {
        return '<div class="status-text-editor" data-status-id="' + s.id + '">' +
            '<div class="status-text-head">' +
            '<span class="status-dot ' + statusColorClass(s.color) + '"></span>' +
            '<strong>#' + s.id + '</strong>' +
            '<select class="status-color form-input" data-field="color">' +
            statusColorOption('awake', '在线', s.color) +
            statusColorOption('sleeping', '离线', s.color) +
            statusColorOption('error', '异常', s.color) +
            '</select>' +
            '</div>' +
            '<label>状态名称</label>' +
            '<input class="form-input form-input-wide" data-field="name" maxlength="64" value="' + escAttr(s.name || '') + '" />' +
            '<label>状态描述</label>' +
            '<textarea class="form-input form-textarea" data-field="desc" maxlength="512">' + esc(s.desc || '') + '</textarea>' +
            '</div>';
    }).join('');
}

function statusColorOption(value, label, current) {
    return '<option value="' + value + '"' + (current === value ? ' selected' : '') + '>' + label + '</option>';
}

function statusColorClass(color) {
    return ['awake', 'sleeping', 'error'].includes(color) ? color : 'awake';
}

async function saveStatusTexts() {
    const status_list = [];
    document.querySelectorAll('.status-text-editor').forEach(function (row) {
        status_list.push({
            id: parseInt(row.dataset.statusId),
            name: row.querySelector('[data-field=name]').value,
            desc: row.querySelector('[data-field=desc]').value,
            color: row.querySelector('[data-field=color]').value
        });
    });

    const r = await fetch(protectedUrl('/panel/status-texts'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status_list: status_list })
    });
    const d = await r.json();
    const msg = document.getElementById('status-text-save-msg');
    msg.textContent = d.success ? '已保存' : '保存失败';
    msg.style.color = d.success ? 'var(--accent)' : 'var(--color-error)';
    if (d.success) {
        statusList = d.status_list || statusList;
        renderStatusSelector();
        updateOverview();
    }
    setTimeout(function () { msg.textContent = ''; }, 2000);
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
            '<td><button class="btn btn-danger btn-compact" data-remove-device="' + escAttr(id) + '">删除</button></td>' +
            '</tr>';
    }).join('');
}

document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-remove-device]');
    if (btn) panelRemoveDevice(btn.dataset.removeDevice);
});

async function panelRemoveDevice(id) {
    if (!confirm('确定删除设备 "' + id + '" 吗？')) return;
    await fetch(protectedUrl('/api/device/remove?id=' + encodeURIComponent(id)));
    loadDevices();
}

async function clearDevices() {
    if (!confirm('确定清除所有设备？此操作不可撤销！')) return;
    await fetch(protectedUrl('/api/device/clear'));
    loadDevices();
}

async function togglePrivateMode(on) {
    await fetch(protectedUrl('/api/device/private?private=' + (on ? '1' : '0')));
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
    const r = await fetch(protectedUrl('/api/settings/toggles'), {
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

    // 获取完整 api_key（需要认证）
    let apiKey = c.llm_api_key || '';
    try {
        const ar = await fetch(protectedUrl('/api/settings/user_config/admin'));
        const ad = await ar.json();
        if (ad.config && ad.config.api_key) apiKey = ad.config.api_key;
    } catch (e) {}

    const sections = [
        { title: '页面个性化', items: [
            { type: 'text', key: 'page_name', name: '用户昵称',
              desc: '显示在首页卡片和页面标题中的名字。留空则使用配置文件默认值', val: c.page_name || '', placeholder: 'User', max: 64 },
            { type: 'text', key: 'page_favicon', name: '站点图标URL',
              desc: '浏览器标签页上显示的小图标。留空则使用默认图标', val: c.page_favicon || '', placeholder: 'https://...' },
            { type: 'text', key: 'learn_more_text', name: '了解更多-文字',
              desc: '首页More Info卡片底部的自定义链接文字。留空则使用默认值', val: c.learn_more_text || '', placeholder: 'GitHub Repo', max: 64 },
            { type: 'text', key: 'learn_more_link', name: '了解更多-链接',
              desc: '首页More Info卡片底部的自定义链接地址', val: c.learn_more_link || '', placeholder: 'https://...' }
        ]},
        { title: '设备列表', items: [
            { type: 'bool', key: 'sorted_devices', name: '设备名A-Z排序',
              desc: '开启后设备列表按名称字母顺序排列' },
            { type: 'bool', key: 'using_first', name: '使用中设备优先',
              desc: '开启后正在使用的设备排在列表最前面（优先级高于A-Z排序）' },
            { type: 'text', key: 'not_using_text', name: '未在使用时显示文字',
              desc: '当设备状态为"未在使用"时替换显示的文字。留空则显示设备原始状态', val: c.not_using_text || '', placeholder: '未在使用', max: 64 }
        ]},
        { title: '外观', items: [
            { type: 'text', key: 'page_background_url', name: '背景图片URL',
              desc: '设置后前台和后台页面使用该图片作为背景。留空则使用纯黑背景。填写完整URL如 https://img.example.com/bg.jpg',
              val: c.page_background_url || '', placeholder: 'https://...', max: 512 }
        ]},
        { title: '专注模式', items: [
            { type: 'number', key: 'focus_default_minutes', name: '默认时长（分钟）',
              desc: '点击开始专注时的默认番茄钟时长', val: c.focus_default_minutes || 25, min: 1, max: 120 },
            { type: 'number', key: 'focus_rest_minutes', name: '完成后休息（分钟）',
              desc: '专注时间结束后自动进入休息模式的时长。设为0则不自动休息', val: c.focus_rest_minutes || 5, min: 0, max: 30 }
        ]},
        { title: '热力图', items: [
            { type: 'number', key: 'heatmap_default_days', name: '默认展示天数',
              desc: '打开热力图时默认展示最近多少天的活跃数据', val: c.heatmap_default_days || 90, min: 7, max: 365 }
        ]},
        { title: 'LLM 分析', items: [
            { type: 'bool', key: 'llm_enabled', name: '启用LLM分析',
              desc: '开启后前台会出现AI洞察卡片。需同时填写下方API Key' },
            { type: 'password', key: 'llm_api_key', name: 'API Key',
              desc: 'OpenAI或兼容API的密钥。以sk-开头。Ollama本地部署可填ollama',
              val: apiKey, placeholder: 'sk-...', max: 256 },
            { type: 'text', key: 'llm_base_url', name: 'API 地址',
              desc: 'OpenAI填 https://api.openai.com/v1，Ollama填 http://localhost:11434',
              val: c.llm_base_url || '', placeholder: 'https://api.openai.com/v1', max: 256 },
            { type: 'text', key: 'llm_model', name: '模型名称',
              desc: '如 gpt-4o-mini、gpt-3.5-turbo、llama3 等',
              val: c.llm_model || '', placeholder: 'gpt-3.5-turbo', max: 128 },
            { type: 'textarea', key: 'llm_system_prompt', name: '系统提示词',
              desc: '自定义AI分析的行为指令。可指定语气、分析角度、字数限制等',
              val: c.llm_system_prompt || '', placeholder: '你是一个使用数据分析助手...', max: 1024 },
            { type: 'number', key: 'llm_cache_minutes', name: '缓存时间（分钟）',
              desc: '同一份分析结果缓存多久。避免短时间内重复调用API浪费Token',
              val: c.llm_cache_minutes || 60, min: 5, max: 1440 },
            { type: 'number', key: 'llm_max_analysis_days', name: '最大分析天数',
              desc: 'AI最多回溯多少天的使用数据。天数越大消耗Token越多',
              val: c.llm_max_analysis_days || 14, min: 1, max: 90 },
            { type: 'number', key: 'llm_rate_limit_minutes', name: '调用冷却（分钟）',
              desc: '两次LLM调用之间的最小间隔。设为0则不限制。建议30分钟以上防止恶意刷Token',
              val: c.llm_rate_limit_minutes || 0, min: 0, max: 1440 }
        ]},
        { title: '数据管理', items: [
            { type: 'bool', key: 'browser_normalize', name: '浏览器窗口标题合并',
              desc: '开启后Edge/Chrome等带标签页标题的窗口名会被合并为浏览器名' },
            { type: 'number', key: 'log_retention_days', name: '日志保留天数',
              desc: '超过此天数的使用记录将被自动清理。设为0表示永久保留',
              val: c.log_retention_days || 0, min: 0, max: 365 }
        ]}
    ];

    let html = '';
    sections.forEach(function(sec) {
        html += '<h3 class="config-section-title">// ' + sec.title + '</h3>';
        sec.items.forEach(function(item) {
            if (item.type === 'bool') {
                html += '<div class="config-row">' +
                    '<label>' + item.name + '</label>' +
                    '<label class="toggle-switch">' +
                    '<input type="checkbox" data-key="' + item.key + '"' + (c[item.key] ? ' checked' : '') + ' />' +
                    '<span class="toggle-slider"></span>' +
                    '</label>' +
                    '<span class="config-desc">' + item.desc + '</span>' +
                    '</div>';
            } else if (item.type === 'textarea') {
                html += '<div class="config-row config-row-stack">' +
                    '<label>' + item.name + '</label>' +
                    '<textarea class="form-input form-textarea" data-key="' + item.key + '" placeholder="' + escAttr(item.placeholder || '') + '" maxlength="' + (item.max || 1024) + '">' + esc(item.val || '') + '</textarea>' +
                    '<span class="config-desc">' + item.desc + '</span>' +
                    '</div>';
            } else if (item.type === 'password') {
                html += '<div class="config-row">' +
                    '<label>' + item.name + '</label>' +
                    '<input class="form-input form-input-wide" type="password" data-key="' + item.key + '" value="' + escAttr(item.val || '') + '" placeholder="' + escAttr(item.placeholder || '') + '" />' +
                    '<span class="config-desc">' + item.desc + '</span>' +
                    '</div>';
            } else {
                html += '<div class="config-row">' +
                    '<label>' + item.name + '</label>' +
                    '<input class="form-input' + (item.type === 'text' ? ' form-input-wide' : '') + '" type="' + (item.type || 'text') + '" data-key="' + item.key + '" value="' + escAttr(item.val || '') + '" placeholder="' + escAttr(item.placeholder || '') + '"' +
                    (item.min !== undefined ? ' min="' + item.min + '"' : '') +
                    (item.max !== undefined && item.type === 'number' ? ' max="' + item.max + '"' : '') +
                    (item.type === 'text' ? ' maxlength="' + (item.max || 512) + '"' : '') +
                    ' />' +
                    '<span class="config-desc">' + item.desc + '</span>' +
                    '</div>';
            }
        });
    });
    list.innerHTML = html;
}

async function saveConfig() {
    const payload = {};
    document.querySelectorAll('#config-list input[type=number]').forEach(function (inp) {
        payload[inp.dataset.key] = parseInt(inp.value) || 0;
    });
    document.querySelectorAll('#config-list input[type=text], #config-list input[type=password]').forEach(function (inp) {
        payload[inp.dataset.key] = inp.value || '';
    });
    document.querySelectorAll('#config-list textarea').forEach(function (ta) {
        payload[ta.dataset.key] = ta.value || '';
    });
    document.querySelectorAll('#config-list input[type=checkbox]').forEach(function (cb) {
        payload[cb.dataset.key] = cb.checked;
    });
    const r = await fetch(protectedUrl('/api/settings/user_config'), {
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
        const r = await fetch(protectedUrl('/panel/categories/list'));
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
    await fetch(protectedUrl('/panel/category/delete?id=' + id), { method: 'POST' });
    loadCategories();
};

async function addCategory() {
    const pattern = document.getElementById('cat-pattern').value.trim();
    const label = document.getElementById('cat-label').value.trim();
    const color = document.getElementById('cat-color').value;
    if (!pattern || !label) { alert('请填写关键词和分类标签'); return; }
    const r = await fetch(protectedUrl('/panel/category/add'), {
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
    const r = await fetch(protectedUrl('/api/export/usage?per_page=50'));
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
    await fetch(protectedUrl('/panel/logs/clear'), { method: 'POST' });
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

function escAttr(s) {
    return esc(s).replace(/'/g, '&#39;');
}
