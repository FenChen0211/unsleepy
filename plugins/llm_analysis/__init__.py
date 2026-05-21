# coding: utf-8

from logging import getLogger
import json
from urllib.request import Request, urlopen

import plugin as pl

l = getLogger(__name__)

p = pl.Plugin(
    name='llm_analysis',
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
)

# 始终注册卡片和路由，启用检查在请求时进行


def _get_uc():
    from data import _UserConfig
    import flask
    with flask.current_app.app_context():
        return _UserConfig.query.first()


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
        if not uc or not uc.llm_enabled or not uc.llm_api_key:
            return ''
    except Exception:
        return ''
    return '''
    <h2>AI 洞察</h2>
    <div id="llm-content" style="font-size: 0.9em; line-height: 1.7; text-align: left; min-height: 40px; color: var(--text-secondary);">
        <p>加载中...</p>
    </div>
    <script>
    fetch('/api/plugin/llm_analysis/insight').then(function(r){ return r.json(); }).then(function(d){
        document.getElementById('llm-content').textContent = d.insight || '暂无分析数据';
    }).catch(function(){
        document.getElementById('llm-content').innerHTML = '<p style="color: var(--text-muted);">AI 分析暂时不可用</p>';
    });
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

    insight = _get_insight(uc)
    if insight:
        p.set_data('llm_insight', insight)
        p.set_data('llm_insight_time', time.time())
        p.set_data('llm_last_call_time', time.time())
    return flask.jsonify({'success': True, 'insight': insight or '暂无分析数据'})


def _get_insight(uc) -> str | None:
    from data import _UsageLog, _DeviceStatusData
    from datetime import datetime, timedelta
    from collections import defaultdict
    try:
        import flask
        app = flask.current_app
        with app.app_context():
            max_days = uc.llm_max_analysis_days if uc else 14
            max_days = max(1, min(max_days, 90))

            end = datetime.utcnow()
            start = end - timedelta(days=max_days)
            logs = _UsageLog.query.filter(
                _UsageLog.timestamp >= start,
                _UsageLog.timestamp <= end
            ).order_by(_UsageLog.timestamp).all()

            dd: dict[str, int] = defaultdict(int)
            for i in range(len(logs)):
                if i < len(logs) - 1:
                    dur = int((logs[i + 1].timestamp - logs[i].timestamp).total_seconds())
                else:
                    dur = logs[i].duration or 0
                if 0 < dur < 7200:
                    dd[logs[i].app_name] += dur

            top_apps = sorted(dd.items(), key=lambda x: -x[1])[:20]
            if not top_apps:
                return None

            devices = _DeviceStatusData.query.all()
            device_names = [dev.show_name or dev.id for dev in devices if dev.using]

            stats_text = _format_stats(top_apps, device_names, max_days)

        return _call_llm(uc, stats_text)
    except Exception as e:
        l.warning(f'[llm_analysis] failed: {e}')
        return None


def _format_stats(top_apps: list, devices: list[str], days: int) -> str:
    lines = [f'最近{days}天使用统计：']
    total = sum(a[1] for a in top_apps)
    if total > 0:
        lines.append(f'总使用时长：{total // 3600}小时{(total % 3600) // 60}分钟')
    for name, secs in top_apps[:8]:
        h = secs // 3600
        m = (secs % 3600) // 60
        lines.append(f'- {name}: {h}小时{m}分钟')
    if devices:
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
