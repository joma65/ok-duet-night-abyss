from ok import TriggerTask, Logger, og
from src.tasks.BaseDNATask import BaseDNATask
from src.tasks.BaseListenerTask import BaseListenerTask

from pynput import mouse, keyboard
logger = Logger.get_logger(__name__)

class TriggerDeactivateException(Exception):
    """停止激活异常。"""
    pass

class AutoMoveTask(BaseListenerTask, BaseDNATask, TriggerTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动穿引共鸣"
        self.description = "需主动激活，运行中也可使用左键打断"
        self.setup_listener_config()
        self.default_config.update({
            '按下时间': 0.50,
            '间隔时间': 0.45,
        })
        self.config_description.update({
            '按下时间': '左键按住多久',
            '间隔时间': '左键释放后等待多久',
        })
        self.manual_activate = False
        self.signal = False
        self.signal_left = False
        self.is_down = False

    def disable(self):
        """禁用任务时，断开信号连接。"""
        self.try_disconnect_listener()
        return super().disable()

    def reset(self):
        self.manual_activate = False
        self.signal = False
        self.signal_left = False
    
    def run(self):
        self.try_connect_listener()

        if self.signal:
            self.signal = False
            if self.in_team() and og.device_manager.hwnd_window.is_foreground():
                self.switch_state()
        
        if not self.in_team():
            return

        while self.manual_activate:
            try:
                self.do_move()
            except TriggerDeactivateException as e:
                logger.info(f'auto_move_task_deactivate {e}')
                break
        if self.is_down:
            self.mouse_up()
        return 
    
    def do_move(self):
        self.mouse_down()
        self.is_down = True
        self.sleep_check(self.config.get('按下时间', 0.50), False)
        self.mouse_up()
        self.is_down = False
        self.sleep_check(self.config.get('间隔时间', 0.45))

    def sleep_check(self, sec, check_signal_flag=True):
        remaining = sec
        step = 0.2
        while remaining > 0:
            s = step if remaining > step else remaining
            self.sleep(s)
            remaining -= s
            if (self.signal and check_signal_flag) or self.signal_left:
                self.switch_state()
            if not self.manual_activate:
                raise TriggerDeactivateException()
            
    def switch_state(self):
        self.signal_left = False
        self.signal = False
        self.manual_activate = not self.manual_activate
        if self.manual_activate:
            logger.info("激活快速移动")
        else:
            logger.info("关闭快速移动")
        
    def on_global_click(self, x, y, button, pressed):
        if self._executor.paused:
            return
        if self.config.get('激活键', 'x2') == '使用键盘':
            if button not in (mouse.Button.left,):
                return
        if self.config.get('激活键', 'x2') == 'x1':
            btn = mouse.Button.x1
        else:
            btn = mouse.Button.x2
        if pressed:
            if button == btn:
                self.signal = True
            elif button == mouse.Button.left and self.manual_activate:
                self.signal_left = True

    def on_global_press(self, key):
        if self._executor.paused or self.config.get('激活键', 'x2') != '使用键盘':
            return
        lower = self.config.get('键盘', 'ctrl_r').lower()
        hot_key = self.normalize_hotkey(lower)
        if self.key_equal(key, hot_key):
            self.signal = True
