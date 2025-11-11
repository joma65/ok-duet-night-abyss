from qfluentwidgets import FluentIcon
import time
import cv2

from ok import Logger, TaskDisabledException
from src.tasks.CommissionsTask import CommissionsTask, QuickMoveTask, Mission
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.DNAOneTimeTask import DNAOneTimeTask

logger = Logger.get_logger(__name__)


class AutoExploration(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动探险"
        self.description = "半自动"
        self.group_name = "半自动"
        self.group_icon = FluentIcon.VIEW

        self.default_config.update({
            '轮次': 3,
        })

        self.setup_commission_config()

        self.config_description.update({
            '轮次': '打几个轮次',
            '超时时间': '超时后将发出提示',
        })
        
        self.action_timeout = 10
        self.quick_move_task = QuickMoveTask(self)

    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position()
        try:
            return self.do_run()
        except TaskDisabledException as e:
            pass
        except Exception as e:
            logger.error("AutoExploration error", e)
            raise

    def do_run(self):
        self.init_param()
        self.load_char()
        _wait_next_round = False
        _skill_time = 0
        _start_time = 0
        while True:
            if self.in_team():
                self.progressing = self.find_serum()
                if self.progressing:
                    if _start_time == 0:
                        _start_time = time.time()
                        _wait_next_round = False
                        self.quick_move_task.reset()
                    _skill_time = self.use_skill(_skill_time)
                    if (
                        not _wait_next_round
                        and time.time() - _start_time
                        >= self.config.get("超时时间", 120)
                    ):
                        _wait_next_round = True
                        self.log_info_notify("任务超时")
                        self.soundBeep()
                else:
                    self.quick_move_task.run()

            _status = self.handle_mission_interface(stop_func=self.stop_func)
            if _status == Mission.START:
                self.wait_until(self.in_team, time_out=30)
                self.log_info_notify("任务开始")
                self.soundBeep()
                _start_time = 0
            elif _status == Mission.STOP:
                self.quit_mission()
                self.log_info("任务中止")
            elif _status == Mission.CONTINUE:
                self.wait_until(self.in_team, time_out=30)
                self.log_info("任务继续")
                _start_time = 0

            self.sleep(0.2)

    def init_param(self):
        self.current_wave = -1

    def stop_func(self):
        self.get_round_info()
        if self.current_round >= self.config.get("轮次", 3):
            return True

    def find_serum(self):
        return bool(self.find_one("serum_icon"))
