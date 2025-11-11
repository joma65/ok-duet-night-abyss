from qfluentwidgets import FluentIcon
import time
import cv2
import re

from ok import Logger, TaskDisabledException, Box, find_color_rectangles, color_range_to_bound
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.CommissionsTask import CommissionsTask, QuickMoveTask, Mission

logger = Logger.get_logger(__name__)


class AutoExcavation(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动勘察"
        self.description = "半自动"
        self.group_name = "半自动"
        self.group_icon = FluentIcon.VIEW

        self.default_config.update({
            '轮次': 3,
        })
        
        self.setup_commission_config()
        keys_to_remove = ["超时时间"]
        for key in keys_to_remove:
            self.default_config.pop(key, None)

        self.config_description.update({
            "轮次": "打几个轮次",
        })
        
        self.action_timeout = 10
        self.progressing = False
        self.quick_move_task = QuickMoveTask(self)

    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position()
        try:
            return self.do_run()
        except TaskDisabledException as e:
            pass
        except Exception as e:
            logger.error("AutoExcavation error", e)
            raise

    def do_run(self):
        self.init_param()
        self.load_char()
        _skill_time = 0
        _excavator_count = 0
        while True:
            if self.in_team():
                self.progressing = self.find_target_health_bar()
                if self.progressing:
                    self.quick_move_task.reset()
                    _skill_time = self.use_skill(_skill_time)
                else:
                    if _skill_time > 0:
                        _excavator_count += 1
                        _skill_time = 0
                        if _excavator_count < 3:
                            self.soundBeep(1)
                    self.quick_move_task.run()

            _status = self.handle_mission_interface(stop_func=self.stop_func)
            if _status == Mission.START:
                self.wait_until(self.in_team, time_out=30)
                self.log_info_notify("任务开始")
                self.soundBeep()
                self.init_param()
                _excavator_count = 0
                _skill_time = 0
            elif _status == Mission.STOP:
                self.quit_mission()
                self.init_param()
                self.log_info("任务中止")
            elif _status == Mission.CONTINUE:
                self.wait_until(self.in_team, time_out=30)
                self.sleep(2)
                self.log_info("任务继续")
                _excavator_count = 0
                _skill_time = 0
                if not self.find_target_health_bar():
                    self.soundBeep(1)

            self.sleep(0.2)

    def init_param(self):
        self.current_round = -1
        self.progressing = False

    def stop_func(self):
        self.get_round_info()
        if self.current_round >= self.config.get("轮次", 3):
            return True

    def find_target_health_bar(self, threshold: float = 0.6):
        health_bar_box = self.box_of_screen_scaled(2560, 1440, 131, 488, 406, 501, name="health_bar", hcenter=True)
        self.draw_boxes("health_bar", health_bar_box, color="blue")
        min_width = self.width_of_screen(200 / 2560)
        min_height = self.height_of_screen(8 / 1440)
        health_bar = find_color_rectangles(self.frame, green_health_bar_color, min_width, min_height, box=health_bar_box, threshold=threshold)
        self.draw_boxes(boxes=health_bar)
        return health_bar

    def find_track_point(self, threshold: float = 0, box: Box | None = None, template=None) -> Box | None:
        if box is None:
            box = self.box_of_screen_scaled(2560, 1440, 454, 265, 2110, 1094, name="find_track_point", hcenter=True)
        if template is None:
            template = filter_track_point_color(self.get_feature_by_name("track_point").mat)
        return self.find_one("track_point", threshold=threshold, box=box, template=template)


def filter_track_point_color(img):
    lower_bound, upper_bound = color_range_to_bound(track_point_color)
    mask = cv2.inRange(img, lower_bound, upper_bound)
    img_modified = img.copy()
    img_modified[mask == 0] = 0
    return img_modified


green_health_bar_color = {
    "r": (135, 150),  # Red range
    "g": (200, 215),  # Green range
    "b": (150, 165),  # Blue range
}

track_point_color = {
    "r": (121, 255),  # Red range
    "g": (116, 255),  # Green range
    "b": (34, 211),  # Blue range
}
