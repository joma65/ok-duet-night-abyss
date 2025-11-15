"""
自动解密任务
在屏幕上查找 puzzle_1 到 puzzle_8 的位置，用于后续自动解密
"""

import json
import os
import time
from ok import TriggerTask, Logger, GenshinInteraction
from src.tasks.BaseDNATask import BaseDNATask

logger = Logger.get_logger(__name__)


class AutoPuzzleTask(BaseDNATask, TriggerTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动解锁迷宫(无巧手)"
        self.description = "自动识别并进行迷宫解密"
        self.default_config.update(
            {
                "启用": True,
                "移动延迟（秒）": 0.1,  # 鼠标移动间隔延迟（秒）
            }
        )
        self.template_shape = None
        self.puzzle_boxes = {}
        self.detection_threshold = 0.85  # 固定检测阈值

        # 在初始化时加载路径数据
        self.puzzle_paths = self._load_puzzle_paths()

    def _load_puzzle_paths(self):
        """从 JSON 文件加载解密路径数据"""
        json_path = os.path.join("mod", "builtin", "puzzle_paths.json")
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"✓ 成功加载解密路径数据: {json_path}")
                return data.get("paths", {})
        except FileNotFoundError:
            logger.error(f"✗ 解密路径文件不存在: {json_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"✗ 解密路径 JSON 解析失败: {e}")
            return {}
        except Exception as e:
            logger.error(f"✗ 加载解密路径失败: {e}")
            return {}

    def run(self):
        # 初始化检测区域
        if self.template_shape != self.frame.shape[:2]:
            self.init_boxes()
            logger.info("AutoPuzzleTask 已初始化检测区域")

        # 扫描屏幕查找所有拼图
        self.scan_puzzles()

        self.next_frame()

    def init_boxes(self):
        """初始化优化后的检测区域，适配所有 16:9 分辨率"""
        # 所有 puzzle 位置相同，游戏中随机显示其中一种
        # 根据实际检测结果：puzzle_2 位置 (2380, 648, 3263, 1534)
        # 原始尺寸: 883x886，添加 5% 边距确保检测稳定
        # 基准分辨率: 3840x2160

        # 统一的检测区域（放大 5%）
        puzzle_box = self.box_of_screen_scaled(
            3840, 2160, 2336, 604, 3307, 1578, name="puzzle_detection", hcenter=True
        )

        # 所有 puzzle 使用相同的检测区域
        for i in range(1, 9):
            self.puzzle_boxes[f"mech_maze_{i}"] = puzzle_box

        self.template_shape = self.frame.shape[:2]
        height, width = self.frame.shape[:2]
        logger.info(f"初始化解密检测区域完成，屏幕尺寸: {width}x{height}")
        logger.info("已设置统一的 puzzle 检测区域（带 5% 边距）")

    def scan_puzzles(self):
        """扫描所有拼图位置"""
        found_any = False

        # 首次运行时输出调试信息
        if not hasattr(self, "_debug_logged"):
            logger.info(f"开始扫描 puzzle，阈值: {self.detection_threshold}")
            self._debug_logged = True

        for i in range(1, 9):
            puzzle_name = f"mech_maze_{i}"

            # 使用 find_one 查找拼图
            try:
                puzzle_box = self.find_one(
                    puzzle_name,
                    box=self.puzzle_boxes[puzzle_name],
                    threshold=self.detection_threshold,
                )
            except Exception as e:
                logger.error(f"查找 {puzzle_name} 时出错: {e}")
                continue

            if puzzle_box:
                found_any = True
                self.log_puzzle_info(puzzle_name, puzzle_box)
                # 执行自动解密
                self.solve_puzzle(puzzle_name)
                break  # 找到一个就执行，不继续查找其他

        if not found_any:
            # 降低日志频率，避免刷屏
            if (
                not hasattr(self, "_last_no_puzzle_log")
                or (self.get_timestamp() - self._last_no_puzzle_log) > 5.0
            ):
                logger.debug("未检测到解密拼图")
                self._last_no_puzzle_log = self.get_timestamp()

    def log_puzzle_info(self, puzzle_name, puzzle_box):
        """输出检测到的拼图信息"""
        logger.info(f"🔍 检测到 {puzzle_name}")
        logger.info(f"  - 置信度: {puzzle_box.confidence:.3f}")

        # 绘制检测框
        self.draw_boxes(puzzle_name, puzzle_box, "green")

    def get_timestamp(self):
        """获取当前时间戳（秒）"""

        return time.time()

    def solve_puzzle(self, puzzle_name):
        """执行 puzzle 解密（需要游戏窗口在前台）"""
        if puzzle_name not in self.puzzle_paths:
            logger.warning(f"{puzzle_name} 没有解密路径")
            return

        logger.info(f"🎯 检测到 {puzzle_name}，准备执行自动解密")
        logger.info("⚠️ 解密需要游戏窗口在前台（鼠标拖拽操作无法后台执行）")

        # 使用 bring_to_front() 确保游戏窗口在前台
        self.executor.device_manager.hwnd_window.bring_to_front()

        import win32api
        import win32con

        puzzle_data = self.puzzle_paths[puzzle_name]
        # 提取 coordinates 字段（如果是新格式），否则使用原数据（兼容旧格式）
        if isinstance(puzzle_data, dict) and "coordinates" in puzzle_data:
            path = puzzle_data["coordinates"]
        else:
            path = puzzle_data

        height, width = self.frame.shape[:2]

        # 获取配置的移动延迟
        move_delay = self.config.get("移动延迟（秒）", 0.1)

        # 路径是基于 1920x1080 的，需要缩放到当前分辨率
        scale_x = width / 1920
        scale_y = height / 1080

        # 第一个点：按下鼠标
        x = int(path[0][0] * scale_x)
        y = int(path[0][1] * scale_y)
        abs_x, abs_y = self.executor.interaction.capture.get_abs_cords(x, y)
        logger.debug(f"按下并移动到: ({abs_x}, {abs_y})")

        win32api.SetCursorPos((abs_x, abs_y))
        self.sleep(0.01)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        self.sleep(move_delay)

        # 中间点：移动鼠标（保持按下状态）
        for i in range(1, len(path)):
            x = int(path[i][0] * scale_x)
            y = int(path[i][1] * scale_y)
            abs_x, abs_y = self.executor.interaction.capture.get_abs_cords(x, y)
            logger.debug(f"拖拽到: ({abs_x}, {abs_y})")

            win32api.SetCursorPos((abs_x, abs_y))
            self.sleep(move_delay)

        # 最后：释放鼠标左键
        logger.debug("释放")
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

        logger.info(f"✅ {puzzle_name} 解密完成")
        self.sleep(1)  # 等待游戏响应
