# coding: utf-8

from logging import getLogger
import json
from urllib.request import Request, urlopen

from pydantic import BaseModel

import plugin as pl

class LLMAnalysisConfig(BaseModel):
    enabled: bool = False
    api_key: str = ''
    base_url: str = 'https://api.openai.com/v1'
    model: str = 'gpt-3.5-turbo'
    system_prompt: str = '你是一个使用数据分析助手。根据用户提供的使用统计数据，给出简短、有洞察力的分析（不超过150字，不使用 markdown 格式）。'
    cache_minutes: int = 60

l = getLogger(__name__)

p = pl.Plugin(
    name='llm_analysis',
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=LLMAnalysisConfig
)

c: LLMAnalysisConfig = p.config

if not c.enabled or not c.api_key:
    l.info('[llm_analysis] not enabled or no api_key configured, plugin idle')
else:
    @p.index_card(name='llm-insight')
    def llm_insight_card():
        import flask
        # 检查展示开关
        try:
            from data import _DisplayToggle
            with flask.current_app.app_context():
                t = _DisplayToggle.query.first()
                if t and not t.show_llm_insight:
                    return ''
        except Exception:
            pass
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
        if flask.request.args.get('refresh') == '1':
            p.data.pop('llm_insight', None)
            p.data.pop('llm_insight_time', None)
        cached = p.get_data('llm_insight')
        cache_time = p.get_data('llm_insight_time') or 0
        import time
        if cached and (time.time() - cache_time < c.cache_minutes * 60):
            return flask.jsonify({'success': True, 'insight': cached})
        insight = _get_insight()
        if insight:
            p.set_data('llm_insight', insight)
            p.set_data('llm_insight_time', time.time())
        return flask.jsonify({'success': True, 'insight': insight or '暂无分析数据'})


    def _get_insight() -> str | None:
        from data import Data, _AggregatedUsage, _DeviceStatusData, _UsageLog, _UserConfig
        from datetime import datetime, timedelta
        try:
            import flask
            app = flask.current_app
            with app.app_context():
                from data import Data
                d = getattr(flask.g, '_data_instance', None)
                if not d:
                    from config import Config
                    import utils as u
                    d = Data(config=Config().config, app=app)
                    flask.g._data_instance = d

                # 读取用户配置的 LLM 最大分析天数（默认14天，防止恶意消耗Token）
                max_days = 14
                try:
                    uc = _UserConfig.query.first()
                    if uc:
                        max_days = max(1, min(uc.llm_max_analysis_days, 90))
                except Exception:
                    pass

                # 限制只分析最近 N 天的数据
                end = datetime.utcnow()
                start = end - timedelta(days=max_days)
                logs = _UsageLog.query.filter(
                    _UsageLog.timestamp >= start,
                    _UsageLog.timestamp <= end
                ).order_by(_UsageLog.timestamp).all()

                # 按应用聚合
                from collections import defaultdict
                dd: dict[str, int] = defaultdict(int)
                for i in range(len(logs)):
                    if i < len(logs) - 1:
                        dur = int((logs[i + 1].timestamp - logs[i].timestamp).total_seconds())
                    else:
                        dur = logs[i].duration or 0
                    if 0 < dur < 7200:
                        dd[logs[i].app_name] += dur

                # 取 Top 应用（限制最多20个，防止超长 prompt）
                top_apps = sorted(dd.items(), key=lambda x: -x[1])[:20]
                if not top_apps:
                    return None

                devices = _DeviceStatusData.query.all()
                device_names = [dev.show_name or dev.id for dev in devices if dev.using]

                stats_text = _format_stats(top_apps, device_names, max_days)

            return _call_llm(stats_text)
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


    def _call_llm(prompt: str) -> str | None:
        if '/v1' in c.base_url:
            url = c.base_url.rstrip('/') + '/chat/completions'
        else:
            url = c.base_url.rstrip('/') + '/v1/chat/completions'
        body = {
            'model': c.model,
            'messages': [
                {'role': 'system', 'content': c.system_prompt},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 200,
            'temperature': 0.7
        }
        req = Request(
            url,
            data=json.dumps(body).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {c.api_key}'
            }
        )
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read().decode('utf-8'))
        return data['choices'][0]['message']['content'].strip()
