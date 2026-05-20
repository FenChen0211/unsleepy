# coding: utf-8

from datetime import datetime, timezone as dt_timezone, timedelta
from logging import getLogger
from time import time
from typing import Any
from io import BytesIO

from werkzeug.security import safe_join
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, Integer, Float, String, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.exc import SQLAlchemyError
from objtyping import to_primitive
import pytz

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import utils as u
from models import ConfigModel, _StatusItemModel

l = getLogger(__name__)

db = SQLAlchemy()
LIMIT = 1024

# -----


class _MainData(db.Model):
    '''
    主程序数据
    '''
    __tablename__ = 'main'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    '''当前状态 id *(即 status_list 中的列表索引)*'''
    private_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    '''是否开启隐私模式 *(启用时 /query 返回中的 `device` 替换为空字典)*'''
    last_updated: Mapped[float] = mapped_column(Float, default=time, onupdate=time)
    '''数据最后更新时间 (utc timestamp)'''


class _DeviceStatusData(db.Model):
    '''
    设备状态
    '''
    __tablename__ = 'device_status'
    id: Mapped[str] = mapped_column(String(LIMIT), primary_key=True, unique=True, nullable=False)
    '''[必选] 设备唯一 id'''
    show_name: Mapped[str] = mapped_column(String(LIMIT), nullable=False)
    '''[必选] 设备显示名称'''
    using: Mapped[bool] = mapped_column(Boolean, nullable=True)
    '''[可选] 设备是否正在使用'''
    status: Mapped[str] = mapped_column(Text, nullable=True)
    '''[可选] 设备状态文本 (如打开的应用名)'''
    fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    '''[可选] 设备的扩展字段'''
    last_updated: Mapped[float] = mapped_column(Float, default=time, onupdate=time)
    '''(本设备) 数据最后更新时间 (utc timestamp)'''


class _MetricsMetaData(db.Model):
    '''
    访问统计元数据
    '''
    __tablename__ = 'metrics_meta'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    today: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default='')
    week: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default='')
    month: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default='')
    year: Mapped[str] = mapped_column(String(LIMIT), nullable=False, default='')


class _MetricsData(db.Model):
    '''
    访问统计数据
    '''
    __tablename__ = 'metrics'
    path: Mapped[str] = mapped_column(String(LIMIT), primary_key=True, unique=True, nullable=False)
    daily: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weekly: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    yearly: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class _PluginData(db.Model):
    '''
    插件数据
    '''
    __tablename__ = 'plugin'
    id: Mapped[str] = mapped_column(String(LIMIT), primary_key=True, unique=True, nullable=False)
    '''插件 id'''
    data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    '''插件数据'''


class _AppCategory(db.Model):
    '''
    应用分类标签
    '''
    __tablename__ = 'app_category'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(LIMIT), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(LIMIT), nullable=False)
    color: Mapped[str] = mapped_column(String(20), default='#5470c6')


class _AggregatedUsage(db.Model):
    '''
    聚合使用时长（定时预计算）
    '''
    __tablename__ = 'aggregated_usage'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    app_name: Mapped[str] = mapped_column(String(LIMIT), nullable=False)
    total_seconds: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(LIMIT), default='未分类')
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(dt_timezone.utc))


class _DisplayToggle(db.Model):
    '''
    前端展示开关
    '''
    __tablename__ = 'display_toggle'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    show_current_status: Mapped[bool] = mapped_column(Boolean, default=True)
    show_today_usage: Mapped[bool] = mapped_column(Boolean, default=True)
    show_category_chart: Mapped[bool] = mapped_column(Boolean, default=True)
    show_heatmap: Mapped[bool] = mapped_column(Boolean, default=False)


class _UsageLog(db.Model):
    '''
    使用记录日志
    '''
    __tablename__ = 'usage_log'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
    app_name: Mapped[str] = mapped_column(String(LIMIT), nullable=False)
    device_name: Mapped[str] = mapped_column(String(LIMIT), nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), nullable=False)


# -----


class Data:
    '''
    data 类, 定义 sql 数据表格式
    '''

    def __init__(self, config: ConfigModel, app: Flask):
        perf = u.perf_counter()
        self._app = app
        self._c = config
        # 配置数据库地址
        app.config['SQLALCHEMY_DATABASE_URI'] = self._c.main.database
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        # 初始化数据库
        db.init_app(app)
        with app.app_context():
            db.create_all()
            main_data = _MainData.query.first()
            if not main_data:
                l.debug(f'[data] main_data not exist, creating a new one')
                main_data = _MainData()
                db.session.add(main_data)
                db.session.commit()

            metrics_metadata = _MetricsMetaData.query.first()
            if self._c.metrics.enabled and not metrics_metadata:
                l.debug(f'[data] metrics_metadata not exist, creating a new one')
                metrics_metadata = _MetricsMetaData()
                db.session.add(metrics_metadata)
                db.session.commit()

            display_toggle = _DisplayToggle.query.first()
            if not display_toggle:
                display_toggle = _DisplayToggle()
                db.session.add(display_toggle)
                db.session.commit()

            # 启动 APScheduler
            self._setup_scheduler()

        l.debug(f'[data] init took {perf()}ms')

    def _throw(self, e: SQLAlchemyError):
        l.error(f'SQL Call Failed: {e}')
        raise u.APIUnsuccessful(500, 'Database Error')

    def _setup_scheduler(self):
        self._scheduler = BackgroundScheduler(timezone=self._c.main.timezone)

        if self._c.metrics.enabled:
            self._metrics_refresh()
            self._scheduler.add_job(
                self._metrics_refresh,
                CronTrigger(hour=0, minute=0),
                id='metrics_refresh',
                replace_existing=True
            )

        self._scheduler.add_job(
            self._clean_cache,
            IntervalTrigger(seconds=self._c.main.cache_age),
            id='clean_cache',
            replace_existing=True
        )

        self._scheduler.add_job(
            self.compute_all_aggregations,
            IntervalTrigger(minutes=5),
            id='aggregate_all',
            replace_existing=True
        )

        self._scheduler.start()
        l.info(f'[scheduler] APScheduler started with timezone={self._c.main.timezone}')

    # --- 主程序数据访问

    @property
    def status_id(self) -> int:
        '''
        当前的状态 id
        '''
        try:
            with self._app.app_context():
                maindata: _MainData = _MainData.query.first()  # type: ignore
                return maindata.status
        except SQLAlchemyError as e:
            self._throw(e)

    @status_id.setter
    def status_id(self, value: int):
        try:
            with self._app.app_context():
                maindata: _MainData = _MainData.query.first()  # type: ignore
                maindata.status = value
                db.session.commit()
        except SQLAlchemyError as e:
            self._throw(e)

    def get_status(self, status_id: int) -> tuple[bool, _StatusItemModel]:
        '''
        用 id 获取状态
        '''
        try:
            return True, self._c.status.status_list[status_id]
        except IndexError:
            return False, _StatusItemModel(
                id=self.status_id,
                name='Unknown',
                desc='未知的标识符，可能是配置问题。',
                color='error'
            )
        except SQLAlchemyError as e:
            self._throw(e)

    @property
    def status(self) -> tuple[bool, _StatusItemModel]:
        '''
        获取当前状态
        '''
        return self.get_status(self.status_id)

    @property
    def status_dict(self) -> tuple[bool, dict[str, int | str]]:
        '''
        获取当前状态
        ```
        {
            'id': int,
            'name': str,
            'desc': str,
            'color': str
        }
        '''
        status = self.status
        return status[0], to_primitive(self.status[1])  # type: ignore

    @property
    def private_mode(self) -> bool:
        '''
        是否开启隐私模式 (不返回设备状态)
        '''
        try:
            with self._app.app_context():
                maindata: _MainData = _MainData.query.first()  # type: ignore
                return maindata.private_mode
        except SQLAlchemyError as e:
            self._throw(e)

    @private_mode.setter
    def private_mode(self, value: bool):
        try:
            with self._app.app_context():
                maindata: _MainData = _MainData.query.first()  # type: ignore
                maindata.private_mode = value
                db.session.commit()
        except SQLAlchemyError as e:
            self._throw(e)

    @property
    def last_updated(self) -> float:
        '''
        数据最后更新时间 (utc)
        '''
        try:
            with self._app.app_context():
                maindata: _MainData = _MainData.query.first()  # type: ignore
                return maindata.last_updated
        except SQLAlchemyError as e:
            self._throw(e)

    @last_updated.setter
    def last_updated(self, value: float):
        try:
            with self._app.app_context():
                maindata: _MainData = _MainData.query.first()  # type: ignore
                maindata.last_updated = value
                db.session.commit()
        except SQLAlchemyError as e:
            self._throw(e)

    # --- 设备状态接口

    @property
    def _raw_device_list(self) -> dict[str, _DeviceStatusData]:
        '''
        原始设备列表 (未排序)
        '''
        try:
            # 判断隐私模式
            if self.private_mode:
                return {}
            with self._app.app_context():
                devices: list[_DeviceStatusData] = _DeviceStatusData.query.all().copy()
                return {d.id: d for d in devices}
        except SQLAlchemyError as e:
            self._throw(e)

    @property
    def _raw_device_list_dict(self) -> dict[str, dict[str, str | int | float | bool]]:
        devices = self._raw_device_list
        return to_primitive(devices, format_date_time=False)  # type: ignore

    @property
    def device_list(self) -> dict[str, dict[str, Any]]:
        '''
        排序后设备列表
        '''
        try:
            if self.private_mode:
                # 隐私模式
                devicelst = {}
            elif self._c.status.using_first:
                # 使用中优先
                devicelst = {}  # devicelst = device_using
                device_not_using = {}
                device_unknown = {}
                for k, v in self._raw_device_list_dict.items():
                    if v.get('using') == True:  # * 正在使用
                        devicelst[k] = v
                    elif v.get('using') == False:  # * 未在使用
                        if self._c.status.not_using:
                            v['status'] = self._c.status.not_using  # 如锁定了未在使用时状态名, 则替换
                        device_not_using[k] = v
                    else:  # * 未知
                        device_unknown[k] = v
                if self._c.status.sorted:
                    devicelst = dict(sorted(devicelst.items()))
                    device_not_using = dict(sorted(device_not_using.items()))
                    device_unknown = dict(sorted(device_unknown.items()))
                # 追加到末尾
                devicelst.update(device_not_using)
                devicelst.update(device_unknown)
            else:
                # 正常获取
                devicelst = self._raw_device_list_dict
                # 如锁定了未在使用时状态名, 则替换
                if self._c.status.not_using:
                    for d in devicelst.keys():
                        if devicelst[d].get('using') == False:
                            devicelst[d]['status'] = self._c.status.not_using
                if self._c.status.sorted:
                    devicelst = dict(sorted(devicelst.items()))
            return devicelst
        except SQLAlchemyError as e:
            self._throw(e)

    def device_get(self, id: str) -> _DeviceStatusData | None:
        '''
        获取指定设备状态

        :param id: 设备 id
        '''
        try:
            with self._app.app_context():
                device: _DeviceStatusData | None = _DeviceStatusData.query.filter_by(id=id).first()
                return device
        except SQLAlchemyError as e:
            self._throw(e)

    def device_set(self, id: str | None = None,
                   show_name: str | None = None,
                   using: bool | None = None,
                   status: str | None = None,
                   fields: dict = {}
                   ):
        '''
        设备状态设置

        :param id: 设备唯一 id
        :param show_name: 设备显示名称
        :param using: 设备是否正在使用
        :param status: 设备状态文本
        :param fields: 扩展字段
        '''
        try:
            with self._app.app_context():
                device = _DeviceStatusData.query.filter_by(id=id).first()
                if not id:
                    raise u.APIUnsuccessful(400, 'device id cannot be empty!')
                if not device:
                    if not show_name:
                        raise u.APIUnsuccessful(400, 'device show_name cannot be empty!')
                    device = _DeviceStatusData()
                    device.id = id
                    db.session.add(device)
                old_status = device.status
                device.show_name = show_name or device.show_name
                device.using = using if using is not None else device.using
                device.status = status or device.status
                device.fields = u.deep_merge_dict(device.fields, fields)
                db.session.commit()
                self.last_updated = time()

                if status and status != old_status and device.using:
                    log_app_name = status
                    if isinstance(device.fields, dict) and device.fields.get('app_name'):
                        log_app_name = device.fields['app_name']
                    l.debug(f'[usage_log] app changed: {old_status} -> {log_app_name} on {device.show_name}')

                    now_ts = datetime.utcnow()
                    dev_name = device.show_name or id

                    prev_log = _UsageLog.query.filter_by(
                        device_name=dev_name
                    ).order_by(_UsageLog.id.desc()).first()
                    if prev_log and prev_log.duration is None:
                        prev_ts = prev_log.timestamp
                        if prev_ts.tzinfo is not None:
                            prev_ts = prev_ts.replace(tzinfo=None)
                        secs = int((now_ts - prev_ts).total_seconds())
                        if 0 < secs < 7200:
                            prev_log.duration = secs

                    log = _UsageLog(
                        timestamp=now_ts,
                        app_name=log_app_name,
                        device_name=dev_name
                    )
                    db.session.add(log)
                    db.session.commit()
        except SQLAlchemyError as e:
            self._throw(e)

    def _match_category(self, app_name: str, categories: list[_AppCategory]) -> str:
        app_lower = app_name.lower()
        for cat in categories:
            if cat.pattern.lower() in app_lower:
                return cat.category
        return '未分类'

    def categorize_app(self, app_name: str) -> str:
        '''
        根据分类规则匹配应用名，返回分类标签
        未匹配返回 '未分类'
        '''
        try:
            with self._app.app_context():
                return self._match_category(app_name, _AppCategory.query.all())
        except SQLAlchemyError as e:
            self._throw(e)

    def get_display_toggles(self) -> dict:
        try:
            with self._app.app_context():
                t = _DisplayToggle.query.first()
                if not t:
                    return {'show_current_status': True, 'show_today_usage': True, 'show_category_chart': True, 'show_heatmap': False}
                return {
                    'show_current_status': t.show_current_status,
                    'show_today_usage': t.show_today_usage,
                    'show_category_chart': t.show_category_chart,
                    'show_heatmap': t.show_heatmap
                }
        except SQLAlchemyError as e:
            self._throw(e)

    def get_categories(self) -> list[dict]:
        try:
            with self._app.app_context():
                cats: list[_AppCategory] = _AppCategory.query.all()
                return [{'id': c.id, 'pattern': c.pattern, 'category': c.category, 'color': c.color} for c in cats]
        except SQLAlchemyError as e:
            self._throw(e)

    def _get_period_range(self, period: str) -> tuple[datetime, datetime]:
        tz = pytz.timezone(self._c.main.timezone)
        now = datetime.now(tz)
        if period == 'today':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif period == 'week':
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif period == 'month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now
        else:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        return start.astimezone(dt_timezone.utc).replace(tzinfo=None), end.astimezone(dt_timezone.utc).replace(tzinfo=None)

    def compute_aggregation(self, period: str):
        try:
            with self._app.app_context():
                start, end = self._get_period_range(period)
                logs: list[_UsageLog] = _UsageLog.query.filter(
                    _UsageLog.timestamp >= start,
                    _UsageLog.timestamp <= end
                ).order_by(_UsageLog.device_name, _UsageLog.timestamp).all()

                if not logs:
                    return

                categories: list[_AppCategory] = _AppCategory.query.all()

                devices: dict[str, list[_UsageLog]] = {}
                for log in logs:
                    devices.setdefault(log.device_name, []).append(log)

                def _to_naive(ts: datetime) -> datetime:
                    return ts.replace(tzinfo=None) if ts.tzinfo else ts

                app_durations: dict[str, int] = {}
                for device_logs in devices.values():
                    for i in range(len(device_logs)):
                        log = device_logs[i]
                        log_ts = _to_naive(log.timestamp)
                        if i < len(device_logs) - 1:
                            next_ts = _to_naive(device_logs[i + 1].timestamp)
                            duration = int((next_ts - log_ts).total_seconds())
                        else:
                            if log.duration:
                                duration = log.duration
                            else:
                                duration = int((_to_naive(end) - log_ts).total_seconds())
                        if 0 < duration < 7200:
                            app_name = log.app_name
                            app_durations[app_name] = app_durations.get(app_name, 0) + duration

                _AggregatedUsage.query.filter_by(period=period).delete()
                for app_name, seconds in app_durations.items():
                    if seconds > 0:
                        entry = _AggregatedUsage(
                            period=period,
                            period_start=start,
                            app_name=app_name,
                            total_seconds=seconds,
                            category=self._match_category(app_name, categories)
                        )
                        db.session.add(entry)
                db.session.commit()
                l.info(f'[aggregation] {period}: {len(app_durations)} apps computed')
        except SQLAlchemyError as e:
            l.error(f'[aggregation] {period} failed: {e}')

    def compute_all_aggregations(self):
        for period in ('today', 'week', 'month'):
            self.compute_aggregation(period)

    def get_aggregated_usage(self, period: str) -> list[dict]:
        try:
            with self._app.app_context():
                rows: list[_AggregatedUsage] = _AggregatedUsage.query.filter_by(
                    period=period
                ).order_by(_AggregatedUsage.total_seconds.desc()).all()
                return [{
                    'app_name': r.app_name,
                    'category': r.category,
                    'seconds': r.total_seconds,
                    'computed_at': r.computed_at.isoformat() if r.computed_at else None
                } for r in rows]
        except SQLAlchemyError as e:
            self._throw(e)

    def device_remove(self, id: str):
        '''
        移除单个设备

        :param id: 设备唯一 id
        '''
        try:
            with self._app.app_context():
                device: _DeviceStatusData | None = _DeviceStatusData.query.filter_by(id=id).first()
                if device:
                    db.session.delete(device)
                    db.session.commit()
                    self.last_updated = time()
        except SQLAlchemyError as e:
            self._throw(e)

    def device_clear(self):
        '''
        清除设备状态
        '''
        try:
            with self._app.app_context():
                _DeviceStatusData.query.delete()
                db.session.commit()
                self.last_updated = time()
        except SQLAlchemyError as e:
            self._throw(e)

    # --- 统计数据访问

    def record_metrics(self, path: str, count: int = 1, override: bool = False):
        '''
        记录 metrics 数据

        :param path: 路径
        :param count: 记录增加次数 (调试使用?)
        :param override: 是否直接替换值而不是增加
        '''
        if not path in self._c.metrics.allow_list:
            return
        try:
            with self._app.app_context():
                metric: _MetricsData | None = _MetricsData.query.filter_by(path=path).first()
                if not metric:
                    metric = _MetricsData()
                    metric.path = path
                    metric.daily = 0
                    metric.weekly = 0
                    metric.monthly = 0
                    metric.yearly = 0
                    metric.total = 0
                    db.session.add(metric)
                if override:
                    metric.daily = count
                    metric.weekly = count
                    metric.monthly = count
                    metric.yearly = count
                    metric.total = count
                else:
                    metric.daily += count
                    metric.weekly += count
                    metric.monthly += count
                    metric.yearly += count
                    metric.total += count
                db.session.commit()
        except SQLAlchemyError as e:
            self._throw(e)

    @property
    def metrics_data(self) -> tuple[dict[str, int], dict[str, int], dict[str, int], dict[str, int], dict[str, int]]:
        '''
        获取 metrics 数据

        :return: (今日, 本周, 本月, 今年, 全部)
        '''
        try:
            raw_metrics: list[_MetricsData] = _MetricsData.query.all()
            daily = {}
            weekly = {}
            monthly = {}
            yearly = {}
            total = {}
            for i in raw_metrics:
                daily[i.path] = i.daily
                weekly[i.path] = i.weekly
                monthly[i.path] = i.monthly
                yearly[i.path] = i.yearly
                total[i.path] = i.total
            return (daily, weekly, monthly, yearly, total)
        except SQLAlchemyError as e:
            self._throw(e)

    @property
    def metric_data_index(self) -> tuple[int, int, int, int, int]:
        '''
        获取主页 (/) 的 metric 数据

        :return: (今日, 本周, 本月, 今年, 全部)
        '''
        try:
            raw_metric: _MetricsData | None = _MetricsData.query.filter_by(path='/').first()
            if raw_metric:
                return (raw_metric.daily, raw_metric.weekly, raw_metric.monthly, raw_metric.yearly, raw_metric.total)
            else:
                return (0, 0, 0, 0, 0)
        except SQLAlchemyError as e:
            self._throw(e)

    @property
    def metrics_resp(self) -> dict[str, Any]:
        '''
        获取 metrics 返回
        '''
        enabled = self._c.metrics.enabled
        if enabled:
            daily, weekly, monthly, yearly, total = self.metrics_data if enabled else ({}, {}, {}, {}, {})
            now = datetime.now(pytz.timezone(self._c.main.timezone))
            return {
                'success': True,
                'enabled': True,
                'time': now.timestamp(),
                'time_local': now.strftime('%Y-%m-%d %H:%M:%S'),
                'timezone': self._c.main.timezone,
                'daily': daily,
                'weekly': weekly,
                'monthly': monthly,
                'yearly': yearly,
                'total': total
            }
        else:
            return {
                'success': True,
                'enabled': False
            }

    def _metrics_refresh(self):
        '''
        (在 每日 0 点 / 启动时 执行) 刷新 metrics 数据
        '''
        perf = u.perf_counter()
        try:
            with self._app.app_context():
                raw_metrics: list[_MetricsData] = _MetricsData.query.all()
                meta_metrics: _MetricsMetaData = _MetricsMetaData.query.first()  # type: ignore

                # get today
                now = datetime.now(pytz.timezone(self._c.main.timezone))
                year = f'{now.year}'
                month = f'{now.year}-{now.month}'
                today = f'{now.year}-{now.month}-{now.day}'
                week = f'{now.year}-{now.isocalendar().week}'

                if today != meta_metrics.today:
                    l.debug(f'[metrics] today changed: {meta_metrics.today} -> {today}')
                    meta_metrics.today = today
                    for i in raw_metrics:
                        i.daily = 0

                if week != meta_metrics.week:
                    l.debug(f'[metrics] week changed: {meta_metrics.week} -> {week}')
                    meta_metrics.week = week
                    for i in raw_metrics:
                        i.weekly = 0

                if month != meta_metrics.month:
                    l.debug(f'[metrics] month changed: {meta_metrics.month} -> {month}')
                    meta_metrics.month = month
                    for i in raw_metrics:
                        i.monthly = 0

                if year != meta_metrics.year:
                    l.debug(f'[metrics] year changed: {meta_metrics.year} -> {year}')
                    meta_metrics.year = year
                    for i in raw_metrics:
                        i.yearly = 0

                db.session.commit()
        except SQLAlchemyError as e:
            l.error(f'[_metrics_refresh] Error: {e}')
        l.debug(f'[_metrics_refresh] took {perf()}ms')

    # --- 插件数据访问

    def get_plugin_data(self, id: str) -> dict:
        '''
        获取插件数据 (没有则会创建)
        '''
        try:
            with self._app.app_context():
                plugin: _PluginData | None = _PluginData.query.filter_by(id=id).first()
                if plugin is None:
                    plugin = _PluginData()
                    plugin.id = id
                    db.session.add(plugin)
                    db.session.commit()
                return plugin.data
        except SQLAlchemyError as e:
            self._throw(e)

    def set_plugin_data(self, id: str, data: dict):
        '''
        设置插件数据
        '''
        try:
            with self._app.app_context():
                plugin: _PluginData | None = _PluginData.query.filter_by(id=id).first()
                if plugin is None:
                    plugin = _PluginData()
                    plugin.id = id
                    plugin.data = {}
                    db.session.add(plugin)
                plugin.data = data
                db.session.commit()
        except SQLAlchemyError as e:
            self._throw(e)

    # --- 缓存系统

    _cache: dict[str, tuple[float, BytesIO]] = {}

    def get_cached_file(self, dirname: str, filename: str) -> BytesIO | None:
        '''
        加载文件 (经过缓存)

        :param dirname: 路径
        :param filename: 文件名
        :return bytesIO: (加载成功) 文件内容 **(字节流)**
        :return None: (加载失败) 空
        '''
        filepath = safe_join(u.get_path(dirname), filename)
        if not filepath:
            # unsafe -> none
            return None
        try:
            if self._c.main.debug:
                # debug -> load directly
                with open(filepath, 'rb') as f:
                    return BytesIO(f.read())
            else:
                cache_key = f'f-{dirname}/{filename}'
                # check cache & expire
                now = time()
                cached = self._cache.get(cache_key)
                if cached and now - cached[0] < self._c.main.cache_age:
                    # has cache, and not expired
                    return cached[1]
                else:
                    # no cache, or expired
                    with open(filepath, 'rb') as f:
                        ret = BytesIO(f.read())
                    self._cache[cache_key] = (now, ret)
                    return ret
        except FileNotFoundError or IsADirectoryError:
            # not found / isn't file -> none
            return None

    def get_cached_text(self, dirname: str, filename: str) -> str | None:
        '''
        加载文本文件 (经过缓存)

        :param dirname: 路径
        :param filename: 文件名
        :return bytes: (加载成功) 文件内容 **(字符串)**
        :return None: (加载失败) 空
        '''
        raw = self.get_cached_file(dirname, filename)
        if raw:
            try:
                return str(raw.getvalue(), encoding='utf-8')
            except UnicodeDecodeError:
                return None
        else:
            return None

    def _clean_cache(self):
        '''
        清理过期缓存
        '''
        if self._c.main.debug:
            return
        now = time()
        for name in self._cache.keys():
            if now - self._cache.get(name, (now, ''))[0] > self._c.main.cache_age:
                f = self._cache.pop(name, (0, None))[1]
                if f:
                    f.close()
