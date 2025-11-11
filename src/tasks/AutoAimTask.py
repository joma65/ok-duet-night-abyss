from ok import TriggerTask, Logger, og
from src.tasks.BaseCombatTask import BaseCombatTask, CharDeadException
from src.tasks.BaseListenerTask import BaseListenerTask

from pynput import mouse

logger = Logger.get_logger(__name__)


class TriggerDeactivateException(Exception):
    """停止激活异常。"""

    pass


class AutoAimTask(BaseListenerTask, BaseCombatTask, TriggerTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动花序弓蓄力瞄准"
        self.description = "需主动激活，运行中可使用右键或左键打断"
        self.setup_listener_config()
        self.default_config.update(
            {
                "激活键": "right",
                "按下时间": 0.50,
                "间隔时间": 0.50,
            }
        )
        self.config_type["激活键"]["options"].insert(0, "right")
        self.config_description.update(
            {
                "按下时间": "右键按住多久(秒)",
                "间隔时间": "右键释放后等待多久(秒)",
            }
        )
        self.manual_activate = False
        self.signal = False
        self.signal_interrupt = False
        self.is_down = False

    def disable(self):
        """禁用任务时，断开信号连接。"""
        self.try_disconnect_listener()
        return super().disable()

    def reset(self):
        self.manual_activate = False
        self.signal = False
        self.signal_interrupt = False

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
                self.do_aim()
            except CharDeadException:
                self.log_error("Characters dead", notify=True)
                break
            except TriggerDeactivateException as e:
                logger.info(f"auto_aim_task_deactivate {e}")
                break
        if self.is_down:
            self.mouse_up(key="right")
        return

    def do_aim(self):
        self.mouse_down(key="right")
        self.is_down = True
        self.sleep_check(self.config.get("按下时间", 0.50), False)
        self.mouse_up(key="right")
        self.is_down = False
        self.sleep_check(self.config.get("间隔时间", 0.50))

    def sleep_check(self, sec, check_signal_flag=True):
        remaining = sec
        step = 0.2
        while remaining > 0:
            s = step if remaining > step else remaining
            self.sleep(s)
            remaining -= s
            if (self.signal and check_signal_flag) or self.signal_interrupt:
                self.switch_state()
            if not self.manual_activate:
                raise TriggerDeactivateException()

    def switch_state(self):
        self.signal_interrupt = False
        self.signal = False
        self.manual_activate = not self.manual_activate
        if self.manual_activate:
            logger.info("激活自动蓄力瞄准")
        else:
            logger.info("关闭自动蓄力瞄准")

    def on_global_click(self, x, y, button, pressed):
        if self._executor.paused:
            return
        if self.config.get('激活键', 'x2') == '使用键盘':
            if button not in (mouse.Button.left, mouse.Button.right):
                return
        # 根据配置获取激活键
        activate_key = self.config.get("激活键", "right")
        if activate_key == "right":
            btn = mouse.Button.right
        elif activate_key == "x1":
            btn = mouse.Button.x1
        else:  # x2
            btn = mouse.Button.x2

        if pressed:
            # 激活键按下 - 切换状态
            if button == btn:
                self.signal = True
            # 运行中按下右键或左键 - 打断
            elif self.manual_activate and (
                button == mouse.Button.right or button == mouse.Button.left
            ):
                self.signal_interrupt = True

    def on_global_press(self, key):
        if self._executor.paused or self.config.get('激活键', 'x2') != '使用键盘':
            return
        lower = self.config.get('键盘', 'ctrl_r').lower()
        hot_key = self.normalize_hotkey(lower)
        if self.key_equal(key, hot_key):
            self.signal = True
