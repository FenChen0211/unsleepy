# coding: utf-8

from logging import getLogger
import json
from types import SimpleNamespace
from urllib.request import Request, urlopen

import plugin as pl

l = getLogger(__name__)

p = pl.Plugin(
    name='llm_analysis',
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
)

def _get_uc():
    from data import _UserConfig
    import flask
    with flask.current_app.app_context():
        uc = _UserConfig.query.first()
    if uc and uc.llm_enabled:
        uc.llm_privacy_mode = _get_privacy_mode(False)
        return uc

    cfg = p.config or {}
    api_key = cfg.get('api_key') or cfg.get('llm_api_key') or ''
    if not api_key or cfg.get('enabled', True) is False:
        return uc

    return SimpleNamespace(
        llm_enabled=True,
        llm_api_key=api_key,
        llm_base_url=cfg.get('base_url') or cfg.get('llm_base_url') or 'https://api.openai.com/v1',
        llm_model=cfg.get('model') or cfg.get('llm_model') or 'gpt-3.5-turbo',
        llm_system_prompt=cfg.get('system_prompt') or cfg.get('llm_system_prompt') or '',
        llm_cache_minutes=int(cfg.get('cache_minutes') or cfg.get('llm_cache_minutes') or 60),
        llm_max_analysis_days=int(cfg.get('max_analysis_days') or cfg.get('llm_max_analysis_days') or 14),
        llm_rate_limit_minutes=int(cfg.get('rate_limit_minutes') or cfg.get('llm_rate_limit_minutes') or 0),
        llm_privacy_mode=bool(cfg.get('privacy_mode') or cfg.get('llm_privacy_mode') or False)
    )


def _get_privacy_mode(default=False) -> bool:
    try:
        from data import _PluginData
        import flask
        with flask.current_app.app_context():
            row = _PluginData.query.filter_by(id='llm_analysis').first()
            if row and row.data:
                return bool(row.data.get('privacy_mode', default))
    except Exception:
        pass
    return bool(default)


@p.index_card('llm-insight')
def llm_insight_card():
    import flask
    try:
        from data import _DisplayToggle
        with flask.current_app.app_context():
            t = _DisplayToggle.query.first()
            if t and not t.show_llm_insight:
                return ''
    except Exception:
        pass
    try:
        uc = _get_uc()
        if not uc or not uc.llm_enabled:
            return ''
    except Exception:
        return ''
    if not uc.llm_api_key:
        return '''
        <h2>AI 洞察</h2>
        <div class="llm-insight-box" style="font-size: 0.9em; line-height: 1.7; text-align: left; min-height: 40px; color: var(--text-secondary);">
            <p>LLM 分析已开启，但还没有配置 API Key 和 API Base URL。</p>
            <p>请到后台「用户配置 / LLM 分析 / API 配置」填写后再使用。</p>
            <a class="btn btn-primary" href="/panel" style="display: inline-flex; width: auto; margin-top: 10px;">去后台配置</a>
        </div>
        '''
    return '''
    <div class="llm-insight-card" data-llm-insight-card>
        <h2>AI 洞察</h2>
        <div data-llm-content style="font-size: 0.9em; line-height: 1.7; text-align: left; min-height: 40px; color: var(--text-secondary);">
            <p>正在请求 AI 分析...</p>
        </div>
        <button class="btn btn-secondary" data-llm-refresh style="width: auto; margin-top: 10px;">刷新分析</button>
    </div>
    <script>
    (function(){
        var script = document.currentScript;
        var card = script ? script.previousElementSibling : document.querySelector('[data-llm-insight-card]');
        if (!card) return;
        var content = card.querySelector('[data-llm-content]');
        var refresh = card.querySelector('[data-llm-refresh]');
        function setText(text) {
            if (content) content.textContent = text || '暂无可展示的 AI 分析结果';
        }
        function loadInsight(force) {
            if (!content) return;
            content.textContent = force ? '正在刷新 AI 分析...' : '正在请求 AI 分析...';
            fetch('/api/plugin/llm_analysis/insight' + (force ? '?refresh=1' : ''))
                .then(function(r){ return r.json(); })
                .then(function(d){
                    if (d.success === false) {
                        setText(d.message || d.insight || 'AI 分析暂时不可用，请检查后台 API Key、Base URL 和模型名称。');
                    } else {
                        setText(d.insight || '暂无可分析数据。请等待客户端上报使用记录，或稍后刷新。');
                    }
                })
                .catch(function(){
                    setText('AI 分析暂时不可用，请检查网络、后台 API 配置或服务日志。');
                });
        }
        if (refresh) refresh.addEventListener('click', function(){ loadInsight(true); });
        loadInsight(false);
    })();
    </script>
    '''


@p.global_route('/api/plugin/llm_analysis/insight')
def llm_insight_api():
    import flask
    import time

    uc = _get_uc()
    if not uc or not uc.llm_enabled or not uc.llm_api_key:
        return flask.jsonify({'success': False, 'message': 'LLM not configured'})

    # 冷却时间检查
    if uc.llm_rate_limit_minutes > 0:
        last_call = p.get_data('llm_last_call_time') or 0
        elapsed = time.time() - last_call
        if elapsed < uc.llm_rate_limit_minutes * 60:
            remain = int(uc.llm_rate_limit_minutes * 60 - elapsed)
            cached = p.get_data('llm_insight')
            if cached:
                return flask.jsonify({'success': True, 'insight': cached + f'\n\n(冷却中，{remain}秒后可刷新)'})
            return flask.jsonify({'success': True, 'insight': f'冷却中，{remain // 60}分{remain % 60}秒后可请求分析'})

    if flask.request.args.get('refresh') == '1':
        if uc.llm_rate_limit_minutes > 0:
            last_call = p.get_data('llm_last_call_time') or 0
            if time.time() - last_call < uc.llm_rate_limit_minutes * 60:
                return flask.jsonify({'success': False, 'message': '冷却中，请稍后再试'})
        p.data.pop('llm_insight', None)
        p.data.pop('llm_insight_time', None)

    cached = p.get_data('llm_insight')
    cache_time = p.get_data('llm_insight_time') or 0
    cache_minutes = uc.llm_cache_minutes if uc else 60
    if cached and (time.time() - cache_time < cache_minutes * 60):
        return flask.jsonify({'success': True, 'insight': cached})

    try:
        insight = _get_insight(uc)
    except Exception as e:
        l.warning(f'[llm_analysis] failed: {e}')
        return flask.jsonify({
            'success': False,
            'message': 'AI 分析暂时不可用，请检查后台 API Key、Base URL、模型名称或服务日志。'
        })
    if not insight:
        return flask.jsonify({'success': True, 'insight': '暂无可分析数据。请等待客户端上报使用记录，或稍后刷新。'})
    p.set_data('llm_insight', insight)
    p.set_data('llm_insight_time', time.time())
    p.set_data('llm_last_call_time', time.time())
    return flask.jsonify({'success': True, 'insight': insight})


def _get_insight(uc) -> str | None:
    from data import _UsageLog, _DeviceStatusData, _AppCategory
    from datetime import datetime, timedelta
    from collections import defaultdict
    import flask
    app = flask.current_app
    with app.app_context():
        max_days = uc.llm_max_analysis_days if uc else 14
        max_days = max(1, min(max_days, 90))
        privacy_mode = bool(getattr(uc, 'llm_privacy_mode', _get_privacy_mode(False)))

        end = datetime.utcnow()
        start = end - timedelta(days=max_days)
        logs = _UsageLog.query.filter(
            _UsageLog.timestamp >= start,
            _UsageLog.timestamp <= end
        ).order_by(_UsageLog.timestamp).all()

        categories = _AppCategory.query.all() if privacy_mode else []
        dd: dict[str, int] = defaultdict(int)
        for i in range(len(logs)):
            if i < len(logs) - 1:
                dur = int((logs[i + 1].timestamp - logs[i].timestamp).total_seconds())
            else:
                dur = logs[i].duration or 0
            if 0 < dur < 7200:
                name = _category_for(logs[i].app_name, categories) if privacy_mode else logs[i].app_name
                dd[name] += dur

        top_apps = sorted(dd.items(), key=lambda x: -x[1])[:20]
        if not top_apps:
            top_apps = _aggregated_fallback(max_days, privacy_mode)
        if not top_apps:
            return None

        devices = _DeviceStatusData.query.all()
        device_names = [dev.show_name or dev.id for dev in devices if dev.using]

        stats_text = _format_stats(top_apps, device_names, max_days, privacy_mode)

    return _call_llm(uc, stats_text)


def _aggregated_fallback(max_days: int, privacy_mode: bool) -> list:
    period = 'today'
    if max_days > 31:
        period = 'year'
    elif max_days > 7:
        period = 'month'
    elif max_days > 1:
        period = 'week'
    apps = pl.PluginInit.instance.d.get_aggregated_usage(period)
    dd: dict[str, int] = {}
    for app in apps:
        key = app.get('category') if privacy_mode else app.get('app_name')
        if not key:
            key = '未分类' if privacy_mode else '未知应用'
        dd[key] = dd.get(key, 0) + int(app.get('seconds') or 0)
    return sorted(dd.items(), key=lambda x: -x[1])[:20]


def _category_for(app_name: str, categories: list) -> str:
    app_lower = (app_name or '').lower()
    for cat in categories:
        pattern = (cat.pattern or '').lower()
        if pattern and pattern in app_lower:
            return cat.category or '未分类'
    return '未分类'


def _format_stats(top_apps: list, devices: list[str], days: int, privacy_mode: bool = False) -> str:
    if privacy_mode:
        lines = [f'最近{days}天使用统计（隐私分析模式：数据已按分类汇总，未包含具体应用名或设备名）：']
    else:
        lines = [f'最近{days}天使用统计：']
    total = sum(a[1] for a in top_apps)
    if total > 0:
        lines.append(f'总使用时长：{total // 3600}小时{(total % 3600) // 60}分钟')
    for name, secs in top_apps[:8]:
        h = secs // 3600
        m = (secs % 3600) // 60
        lines.append(f'- {name}: {h}小时{m}分钟')
    if devices:
        if privacy_mode:
            lines.append(f'活跃设备数量：{len(devices)}')
        else:
            lines.append(f'活跃设备：{", ".join(devices)}')
    return '\n'.join(lines)


def _call_llm(uc, prompt: str) -> str | None:
    api_key = uc.llm_api_key if uc else ''
    base_url = (uc.llm_base_url or 'https://api.openai.com/v1').rstrip('/')
    model = uc.llm_model or 'gpt-3.5-turbo'
    system_prompt = uc.llm_system_prompt or '你是一个使用数据分析助手。根据用户提供的使用统计数据，给出简短、有洞察力的分析（不超过150字，不使用 markdown 格式）。'

    if '/v1' in base_url:
        url = base_url + '/chat/completions'
    else:
        url = base_url + '/v1/chat/completions'

    body = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 200,
        'temperature': 0.7
    }
    headers = {'Content-Type': 'application/json'}
    if api_key and api_key != 'ollama':
        headers['Authorization'] = f'Bearer {api_key}'
    req = Request(
        url,
        data=json.dumps(body).encode('utf-8'),
        headers=headers
    )
    resp = urlopen(req, timeout=15)
    data = json.loads(resp.read().decode('utf-8'))
    return data['choices'][0]['message']['content'].strip()
