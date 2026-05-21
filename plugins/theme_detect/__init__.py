# coding: utf-8

from pydantic import BaseModel
import plugin as pl

class ThemeDetectConfig(BaseModel):
    light: str = 'default'
    dark: str = 'dark'

p = pl.Plugin(
    name='theme_detect',
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=ThemeDetectConfig
)

@p.event_handler(pl.BeforeRequestHook)
def on_before_request(event: pl.BeforeRequestHook, request):
    '''
    The default theme now follows the user's system color scheme with CSS.
    Avoid switching Flask themes implicitly; older theme CSS can otherwise
    override the refreshed default UI for dark-mode users.
    '''
    return event


@p.index_inject()
def inject_theme_detect():
    '''
    Keep this plugin compatible without forcing a reload/theme cookie.
    '''
    return ''
