from qfluentwidgets import FluentIcon
import time

from ok import Logger, TaskDisabledException
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.CommissionsTask import CommissionsTask, Mission
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.trigger.AutoRouletteTask import AutoRouletteTask

logger = Logger.get_logger(__name__)


class AutoMeditation(DNAOneTimeTask, CommissionsTask, BaseCombatTask):
    """
    自动冥想/终焰任务 - 单次任务，无连续轮次
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "Lvl 70 Meditation Auto Farm"
        self.description = "全自动"
        self.group_name = "全自动"
        self.group_icon = FluentIcon.CAFE
        self.wheel_task = None
        self.default_config.update({
            '刷几次': 999,
            '任务超时时间': 140,  
        })

        self.setup_commission_config()

        keys_to_remove = ["启用自动穿引共鸣", "自动选择首个密函和密函奖励", "轮次"]
        for key in keys_to_remove:
            self.default_config.pop(key, None)

        self.config_description.update({
            '刷几次': '总共刷多少次冥想/终焰',
            '任务超时时间': '单次任务超时时间（秒）',
        })

        self.action_timeout = 10

    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position(save_current_pos=False)
        self.set_check_monthly_card()
        try:
            return self.do_run()
        except TaskDisabledException:
            pass
        except Exception as e:
            logger.error("AutoMeditation error", e)
            raise

    def do_run(self):
        self.load_char()
        _start_time = 0
        _skill_time = 0
        _count = 0
        _macro_executed = False  
        if self.wheel_task is None:
            self.wheel_task = self.get_task_by_class(AutoRouletteTask)
        if self.in_team():
            self.log_info("检测到已在队伍中，先放弃当前任务")
            self.give_up_mission()
            self.wait_until(lambda: not self.in_team(), time_out=30, settle_time=1)

        while True:
            if _count >= self.config.get("刷几次", 999):
                self.log_info(f"已完成全部 {_count} 次任务")
                self.soundBeep()
                return

            if self.in_team():
                if _start_time == 0:
                    _start_time = time.time()
                    _macro_executed = False
                    self.log_info(f"开始第 {_count + 1} 次冥想/终焰任务")

                if not _macro_executed:
                    try:
                        logger.info("开始执行移动宏队列")
                        self.walk_to_aim()
                        _macro_executed = True
                        logger.info("宏队列执行完成")
                    except Exception as e:
                        logger.error(f"宏队列执行失败: {e}")
                        self.give_up_mission()
                        self.wait_until(lambda: not self.in_team(), time_out=30, settle_time=1)
                        _start_time = 0
                        _macro_executed = False
                        continue


                _skill_time = self.use_skill(_skill_time)


                elapsed = time.time() - _start_time
                if elapsed >= self.config.get("任务超时时间", 300):
                    logger.warning(f"任务超时 ({elapsed:.1f}秒)，重新开始...")
                    self.give_up_mission()
                    self.wait_until(lambda: not self.in_team(), time_out=30, settle_time=1)
                    _start_time = 0
                    _macro_executed = False
                    continue

            _status = self.handle_mission_interface()

            if _status == Mission.START:

                elapsed = time.time() - _start_time if _start_time > 0 else 0
                _count += 1
                self.log_info(
                    f"任务完成 [{_count}/{self.config.get('刷几次', 999)}] 用时: {elapsed:.1f}秒"
                )


                if _count >= self.config.get("刷几次", 999):
                    self.log_info(f"已完成全部 {_count} 次任务")
                    self.soundBeep()
                    return

                self.wait_until(self.in_team, time_out=30)
                

                _start_time = 0
                _skill_time = 0
                _macro_executed = False

            self.sleep(0.2)

    def walk_to_aim(self):
        logger.info("开始执行冥想/终焰宏队列")
        move_start = time.time()
        
        try:
            self.sleep(1.5)
            # this has a >60Hz requirements btw, or you might fail to jump over the wall at the start
            self.send_key_down("w")
            self.sleep(0.22)

            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key_down("lshift")
            self.sleep(1)
            self.send_key_down("a")
            self.sleep(0.5)
            self.send_key_up("a")
            self.sleep(2.4)
            self.send_key_down("d")
            self.sleep(0.7)
            self.send_key_up("d")
            self.sleep(0.65)
            self.send_key_up("lshift")
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key("space", down_time=0.1,after_sleep=0.4)

            # walking down the first gate and there will be stupid lag if pc is bad, this few lines will align you to a corner because bumps or the stairs can push you around and ruin some RNG... blame UE4 lol
       
            self.send_key_down("w")
            self.sleep(2.1)
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key_down("lshift")
            self.sleep(1.2)            
            self.send_key_up("w")   
            self.send_key_down("d")
            self.sleep(1.5)
            self.send_key_up("d")
            self.sleep(0.1)
            self.send_key_down("s")
            self.sleep(1.11)
            self.send_key_up("s")
            self.sleep(0.1)

            # this aligns you with the middle of the first crate, it SHOULD

            self.send_key_down("a")
            self.sleep(0.62)
            self.send_key_up("a")

            # end of corneralignment
            self.send_key_down("w")

            # if your jump is off, adjust this delay, if you slip off before the double jump on the crate, also lower it slightly

            self.sleep(3.0)
            self.send_key_up("w")                
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key("space", down_time=0.1,after_sleep=0.2)
            self.sleep(1.0)
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key("space", down_time=0.1,after_sleep=0.4) 
            for _ in range(2): 
                self.mouse_down(key="left")
                self.sleep(0.54)
                self.mouse_up(key="left")
                self.sleep(0.21)
            self.sleep(0.5)
            self.send_key_down("s")
            self.sleep(0.2)
            self.send_key_up("s")

            # ADDED SUPPORT IF THIS HAPPENS ~~you SHOULDN'T vault over the fence, instead walk to the left and slide off it~~ 

            self.send_key_down("w")                                      
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key("space", down_time=0.1,after_sleep=0.2)                  
            self.sleep(0.9)            
            self.send_key_down("a")
            self.sleep(1.1)
            self.send_key_up("a")
            # walk forward the tunnel then go into corneralignment for the puzzle 
            self.send_key_up("lshift")  
            self.send_key_down("lshift")                      
            self.sleep(7.0)
            self.send_key_down("a")
            self.sleep(0.6)
            self.send_key_up("a")
            self.sleep(1.8)
            self.send_key_up("w")
            # you should be walking into the sandbags
            self.send_key_down("a")
            self.sleep(0.6)
            self.send_key_up("a")
            self.sleep(0.6)
            self.send_key_down("d")
            self.sleep(0.8)
            self.send_key_up("d")
            # walking to the puzzle platform
            self.send_key_down("s")
            self.sleep(2.4)          
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key_down("lshift")
            self.sleep(0.15)
            self.send_key_up("lshift")
            self.send_key_up("s")
            # Change this into the function for hacking puzzles if you don't have deft
            for _ in range(4):
                self.send_key("f", after_sleep=1)
            self.wheel_task.run()
            self.reset_and_transport()
            # Adjust this as needed, this will drop 5 jellyfish for rebecca, if your range is limited, just add a walk left macro but you must adjust for the next D key as well, increase the after_sleep or minus range
            # from 5 to 4 jellyfishes if you are doing too much dmg
            for _ in range(5):
                self.send_key("e", after_sleep=0.6)
            self.sleep(0.3)                
            self.send_key_down("d")
            self.sleep(0.2)
            self.send_key_down("lshift")
            self.sleep(0.9)
            self.send_key_up("d")            
            self.send_key_down("w")
            self.sleep(1.5)
            self.send_key_up("w")
            self.send_key_down("d")
            self.sleep(1.8)
            self.send_key_up("d")        
            self.send_key_down("s")
            self.sleep(2.5)    
            self.send_key_up("s")
            self.send_key_down("d")
            self.sleep(2.2)
            self.send_key_up("d")
            # walk up the tunnel
            self.send_key_down("w")
            self.sleep(5.5)
            self.send_key_up("w")
            self.send_key_down("d")                                 
            self.sleep(4.5)
            self.send_key_up("d")
            self.send_key_down("w")
            # IF you get stuck walking right on some cardboard after the tunnel with the huge amount of enemies to the left, adjust this lower, higher if you hit some wall trying to drop into water
            self.sleep(1.3)
            self.send_key_up("w")
            self.send_key_down("d")                                 
            self.sleep(4.3)
            self.send_key("lshift", down_time=0.1,after_sleep=0.2)
            self.sleep(0.9)
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key("space", down_time=0.1,after_sleep=0.2)            
            self.sleep(1.7)            
            # should be dropping into the pool
            self.send_key_up("d")
            self.send_key_down("d")
            self.sleep(0.5)
            self.send_key_up("d")           
            for _ in range(4): 
                self.mouse_down(key="left")
                self.sleep(0.54)
                self.mouse_up(key="left")
                self.sleep(0.21)
            self.sleep(0.2)
            self.send_key_down("lshift")
            self.sleep(1)
            self.send_key_up("lshift")
            self.sleep(0.5)
            self.send_key_down("w") 
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key("space", down_time=0.1,after_sleep=0.2)
            for _ in range(4): 
                self.mouse_down(key="left")
                self.sleep(0.54)
                self.mouse_up(key="left")
                self.sleep(0.21)
            self.send_key("space", down_time=0.1,after_sleep=0.4)
            self.send_key("space", down_time=0.1,after_sleep=0.2)                
            for _ in range(4): 
                self.mouse_down(key="left")
                self.sleep(0.54)
                self.mouse_up(key="left")
                self.sleep(0.21)
            
            self.sleep(2)
            self.send_key_up("w")
            self.send_key_down("s")            
            self.sleep(3)  
            self.send_key_up("s") 
            elapsed = time.time() - move_start
            logger.info(f"宏队列执行完成，用时 {elapsed:.1f} 秒")

        except TaskDisabledException:
            raise
        except Exception as e:
            logger.error(f"宏队列执行出错: {e}")
            raise
        finally:
            for key in ["w", "a", "s", "d", "lshift", "lalt", "space", "e", "q", "z"]:
                self.send_key_up(key)
