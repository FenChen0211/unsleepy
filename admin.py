# coding: utf-8

from flask import redirect, request
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView

from models import ConfigModel


class _SecureMixin:
    _expected_secret: str = ''

    def is_accessible(self):
        return request.cookies.get('sleepy-secret') == self._expected_secret

    def inaccessible_callback(self, name, **kwargs):
        return redirect('/panel/login')


class SleepyAdminIndexView(_SecureMixin, AdminIndexView):
    @expose('/logout')
    def logout_view(self):
        return redirect('/panel/logout')


class UsageLogView(_SecureMixin, ModelView):
    column_list = ('timestamp', 'app_name', 'device_name', 'duration')
    column_searchable_list = ('app_name', 'device_name')
    column_sortable_list = ('timestamp', 'app_name', 'device_name', 'duration')
    column_default_sort = ('timestamp', True)
    column_formatters = {
        'timestamp': lambda v, c, m, p: m.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC') if m.timestamp else ''
    }
    can_edit = False
    can_delete = True
    can_create = True
    page_size = 50


class DeviceStatusView(_SecureMixin, ModelView):
    column_list = ('id', 'show_name', 'using', 'status', 'last_updated')
    column_searchable_list = ('id', 'show_name', 'status')
    column_sortable_list = ('id', 'show_name', 'using', 'status', 'last_updated')
    can_delete = True
    can_create = False
    can_edit = True


class MainDataView(_SecureMixin, ModelView):
    column_list = ('id', 'status', 'private_mode', 'last_updated')
    can_create = False
    can_delete = False


class MetricsDataView(_SecureMixin, ModelView):
    column_list = ('path', 'daily', 'weekly', 'monthly', 'yearly', 'total')
    can_create = False
    can_edit = False
    can_delete = False


class PluginDataView(_SecureMixin, ModelView):
    column_list = ('id', 'data')
    can_create = False
    can_edit = True
    can_delete = False


def init_admin(app, config: ConfigModel):
    from data import db, _UsageLog, _DeviceStatusData, _MainData, _MetricsData, _PluginData

    admin_ep = '/admin'

    for view_cls in (SleepyAdminIndexView, UsageLogView, DeviceStatusView, MainDataView, MetricsDataView, PluginDataView):
        view_cls._expected_secret = config.main.secret

    admin = Admin(
        app,
        name=f'{config.page.name} 管理',
        url=admin_ep,
        index_view=SleepyAdminIndexView(url=admin_ep, name='管理后台')
    )

    admin.add_view(UsageLogView(_UsageLog, db.session, name='使用记录', category='数据'))
    admin.add_view(DeviceStatusView(_DeviceStatusData, db.session, name='设备状态', category='数据'))
    admin.add_view(MainDataView(_MainData, db.session, name='系统状态', category='系统'))
    admin.add_view(MetricsDataView(_MetricsData, db.session, name='访问统计', category='系统'))
    admin.add_view(PluginDataView(_PluginData, db.session, name='插件数据', category='系统'))

    return admin
