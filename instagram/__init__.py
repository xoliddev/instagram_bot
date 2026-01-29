"""
Instagram Bot Modules
Modular architecture for Instagram automation

Modullar:
- api.py: GraphQL API funksiyalari
- actions.py: Follow/Unfollow amaliyotlari  
- stories.py: Story ko'rish va like bosish
- sync.py: Follower sinxronizatsiya
- utils.py: Yordamchi funksiyalar
"""

from .api import InstagramAPI
from .actions import InstagramActions
from .stories import InstagramStories
from .sync import InstagramSync
from .utils import (
    get_human_delay, 
    update_heartbeat, 
    safe_goto, 
    send_telegram_msg,
    refresh_page_if_stuck,
    smart_sleep
)

__all__ = [
    'InstagramAPI',
    'InstagramActions', 
    'InstagramStories',
    'InstagramSync',
    'get_human_delay',
    'update_heartbeat',
    'safe_goto',
    'send_telegram_msg',
    'refresh_page_if_stuck',
    'smart_sleep'
]
