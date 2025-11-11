from qfluentwidgets import FluentIcon
import time

from ok import Logger, TaskDisabledException
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.CommissionsTask import CommissionsTask, Mission

logger = Logger.get_logger(__name__)


class AutoExpulsion(DNAOneTimeTask, CommissionsTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.description = "全自动(存在特定开始位置无法全自动)"
        self.default_config.update({
            '开局向前走': 0.0,
            '开局是否跳跃': False,
            '开局是否奔跑': False,
            '任务超时时间': 120,
            '刷几次': 999,
        })
        self.config_description.update({
            '开局向前走': '开局向前走几秒',
            '任务超时时间': '放弃任务前等待的秒数',
        })
        self.setup_commission_config()
        self.default_config.pop("启用自动穿引共鸣", None)
        self.name = "自动驱离"
        self.action_timeout = 10

    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position()
        try:
            return self.do_run()
        except TaskDisabledException as e:
            pass
        except Exception as e:
            logger.error("AutoExpulsion error", e)
            raise

    def do_run(self):
        self.load_char()
        _start_time = 0
        _skill_time = 0
        _count = 0
        while True:
            if self.in_team():
                if _start_time == 0:
                    _count += 1
                    self.move_on_begin()
                    _start_time = time.time()
                _skill_time = self.use_skill(_skill_time)
                if time.time() - _start_time >= self.config.get("任务超时时间", 120):
                    logger.info("已经超时，重开任务...")
                    self.give_up_mission()
                    self.wait_until(lambda: not self.in_team(), time_out=30, settle_time=1)

            _status = self.handle_mission_interface()
            if _status == Mission.START:
                self.wait_until(self.in_team, time_out=30)
                if _count >= self.config.get("刷几次", 999):
                    self.sleep(1)
                    self.open_in_mission_menu()
                    self.log_info_notify("任务终止")
                    self.soundBeep()
                    return
                self.log_info("任务开始")
                self.sleep(2.5)
                _start_time = 0
            self.sleep(0.2)

    def move_on_begin(self):
        jump = self.config.get("开局是否跳跃", False)
        shift = self.config.get("开局是否奔跑", False)
        if (walk_sec := self.config.get("开局向前走", 0)) > 0:
            self.send_key_down("w")
            self.sleep(0.03)
            if shift:
                self.send_key_down("lshift")
                self.sleep(0.03)
            if jump:
                start = time.time()
                while time.time() - start < walk_sec:
                    self.send_key("space", after_sleep=0.25)
            else:
                self.sleep(walk_sec)
            self.send_key_up("w")
            if shift:
                self.sleep(0.03)
                self.send_key_up("lshift")
            self.sleep(1)

