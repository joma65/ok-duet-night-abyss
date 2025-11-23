from qfluentwidgets import FluentIcon
import time
import re
import os
import cv2
import numpy as np
from pathlib import Path
from PIL import Image

from ok import Logger, TaskDisabledException, Box
from src.tasks.BaseDNATask import BaseDNATask
from src.tasks.DNAOneTimeTask import DNAOneTimeTask

logger = Logger.get_logger(__name__)


class AutoFishMultiSpotTask(DNAOneTimeTask, BaseDNATask):
    """AutoFishMultiSpotTask
    Automatically rotates through multiple fishing spots with integrated fishing logic
    """
    # Fishing constants (from AutoFishTask)
    BAR_MIN_AREA = 1200
    ICON_MIN_AREA = 70
    ICON_MAX_AREA = 400
    CONTROL_ZONE_RATIO = 0.25
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Auto Fish Multi Spot"
        self.description = "Automatically rotates through 3 fishing spots"
        self.group_name = "Fully Automatic"
        self.group_icon = FluentIcon.CAFE
        
        # Default config (includes fishing configs)
        self.default_config.update({
            "Max Rounds Per Spot": 0,  # 0 = unlimited
            "No Fish Timeout": 30.0,  # Seconds to wait for "no more fish" detection
            "PNG Check Timeout": 10.0,  # Seconds to wait for PNG image before W key
            "END_WAIT_SPACE": 0.5,  # Wait time after each round (seconds)
            "MAX_START_SEC": 20.0,  # Start phase timeout (seconds)
            "MAX_FIGHT_SEC": 60.0,  # Fighting phase timeout (seconds)
            "MAX_END_SEC": 20.0,  # End phase timeout (seconds)
            "发出声音提醒": False,  # Disable sound notifications when changing spots
            "Enable Purgatorio": True,  # Enable/disable Purgatorio fishing spot
            "Enable Icelake": True,  # Enable/disable Icelake fishing spot
            "Enable Sewers": True,  # Enable/disable Sewers fishing spot
        })
        
        # Config descriptions
        self.config_description.update({
            "Max Rounds Per Spot": "Maximum rounds per spot (0 = unlimited)",
            "No Fish Timeout": "Timeout to detect 'no more fish' message (seconds)",
            "PNG Check Timeout": "Timeout to wait for PNG image before pressing W (seconds)",
            "END_WAIT_SPACE": "Wait time after each round (seconds)",
            "MAX_START_SEC": "Start phase timeout (seconds)",
            "MAX_FIGHT_SEC": "Fighting phase timeout (seconds)",
            "MAX_END_SEC": "End phase timeout (seconds)",
            "发出声音提醒": "Play sound notification when completed",
            "Enable Purgatorio": "Enable fishing at Purgatorio spot",
            "Enable Icelake": "Enable fishing at Icelake spot",
            "Enable Sewers": "Enable fishing at Sewers spot",
        })
        
        # Fishing spot scripts (in order: Purgatorio -> Icelake -> Sewers)
        self.spot_scripts = [
            {"name": "Purgatorio", "py": "mod/fish/Purgatorio.py", "png": "mod/fish/Purgatorio.png", "e_count": 0},
            {"name": "Icelake", "py": "mod/fish/Icelake.py", "png": "mod/fish/Icelake.png", "e_count": 1},
            {"name": "Sewers", "py": "mod/fish/Sewers.py", "png": "mod/fish/Sewers.png", "e_count": 2},
        ]
        
        # Load menu images from mod/fish folder
        self.menu_images = {}
        self.load_menu_images()
        
    def run(self):
        DNAOneTimeTask.run(self)
        try:
            return self.do_run()
        except TaskDisabledException:
            pass
        except Exception as e:
            logger.error(f"AutoFishMultiSpotTask error: {e}")
            raise
    
    def init(self):
        """Initialize fishing spots"""
        logger.info(f"Initialized {len(self.spot_scripts)} fishing spots")
        # Initialize stats tracking
        self.total_fish_caught = 0
        self.current_spot_fish = 0
        self.fishing_stats = {
            "rounds_completed": 0,
            "total_time": 0.0,
            "start_time": None,
            "current_phase": "Preparing",
            "chance_used": 0,
        }
        # Initialize all info displays from the start
        self.info_set("Current Spot", "None")
        self.info_set("Fish Caught (Current Spot)", 0)
        self.info_set("Total Fish Caught", 0)
        self.info_set("Status", "Ready")
        self.info_set("Rounds Completed", 0)
        self.info_set("Chance Used (Bigger Fish)", 0)
        self.info_set("Current Phase", "Preparing")
    
    def load_menu_images(self):
        """Load menu images from mod/fish folder"""
        mod_folder = "mod/fish"
        if not os.path.exists(mod_folder):
            logger.warning(f"Mod folder not found: {mod_folder}")
            return
        
        menu_image_names = ["inventory", "fishingsupplies", "fishingsupplies2", "inventory2", "inventory3", "locatefishing", "teleport", "rod", "rod2", "Purgatorio", "Icelake"]
        
        for image_name in menu_image_names:
            image_path = os.path.join(mod_folder, f"{image_name}.png")
            if os.path.exists(image_path):
                try:
                    pil_img = Image.open(image_path)
                    img_array = np.array(pil_img)
                    # Convert RGB to BGR for OpenCV
                    template = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                    self.menu_images[image_name] = template
                    logger.info(f"Loaded menu image: {image_name}")
                except Exception as e:
                    logger.error(f"Failed to load image {image_name}: {e}")
            else:
                logger.warning(f"Image file not found: {image_path}")
    
    def find_image_template(self, template_img, threshold: float = 0.7):
        """Find template image in current frame using template matching"""
        if template_img is None:
            return None
        
        frame = self.frame
        if frame is None:
            return None
        
        # Convert frame to BGR if needed
        if len(frame.shape) == 3:
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
        else:
            frame_gray = frame
            template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
        
        # Template matching
        result = cv2.matchTemplate(frame_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= threshold:
            h, w = template_gray.shape[:2]
            x = max_loc[0]
            y = max_loc[1]
            # Return a Box object (x, y, width, height)
            return Box(x, y, w, h)
        
        return None
    
    def wait_for_png(self, png_path: str, timeout: float = 10.0) -> bool:
        """Wait for PNG image to appear on screen using template matching"""
        logger.info(f"Waiting for PNG image: {png_path}")
        deadline = time.monotonic() + timeout
        
        # Load template image
        if not os.path.exists(png_path):
            logger.error(f"PNG file not found: {png_path}")
            return False
        
        try:
            pil_img = Image.open(png_path)
            img_array = np.array(pil_img)
            template = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error(f"Failed to load PNG template {png_path}: {e}")
            return False
        
        while time.monotonic() < deadline:
            box = self.find_image_template(template, threshold=0.7)
            if box:
                image_name = Path(png_path).stem
                logger.info(f"Found PNG image: {image_name}")
                return True
            self.sleep(0.2)  # sleep() will raise TaskDisabledException if disabled
            self.next_frame()
        
        image_name = Path(png_path).stem
        logger.warning(f"Timeout waiting for PNG image: {image_name}")
        return False
    
    def click_coordinate(self, x: int, y: int, name: str = "", delay: float = 1.0):
        """Click at a specific coordinate with delay"""
        logger.info(f"Clicking at ({x}, {y})" + (f" - {name}" if name else ""))
        self.click(x, y)
        self.sleep(delay)
    
    def wait_for_image(self, image_name: str, timeout: float = 10.0) -> bool:
        """Wait for an image to appear on screen (without clicking)"""
        logger.info(f"Waiting for {image_name}.png to appear...")
        deadline = time.monotonic() + timeout
        
        if image_name not in self.menu_images:
            logger.error(f"Image {image_name} not loaded in menu_images")
            return False
        
        template = self.menu_images[image_name]
        
        while time.monotonic() < deadline:
            box = self.find_image_template(template, threshold=0.7)
            if box:
                logger.info(f"Found {image_name}.png - map loaded!")
                return True
            
            self.sleep(0.2)
            self.next_frame()
        
        logger.warning(f"Timeout: Could not find {image_name}.png after {timeout} seconds")
        return False
    
    def find_and_click_image(self, image_name: str, timeout: float = 10.0, delay: float = 1.0) -> bool:
        """Find an image on screen and click it"""
        logger.info(f"Looking for {image_name}.png...")
        deadline = time.monotonic() + timeout
        
        if image_name not in self.menu_images:
            logger.error(f"Image {image_name} not loaded in menu_images")
            return False
        
        template = self.menu_images[image_name]
        
        while time.monotonic() < deadline:
            box = self.find_image_template(template, threshold=0.7)
            if box:
                # Click at the center of the found image
                center_x = box.x + box.width // 2
                center_y = box.y + box.height // 2
                logger.info(f"Found {image_name}.png at ({center_x}, {center_y}), clicking...")
                self.click(center_x, center_y)
                self.sleep(delay)
                return True
            
            self.sleep(0.2)
            self.next_frame()
        
        logger.warning(f"Timeout: Could not find {image_name}.png after {timeout} seconds")
        return False
    
    def find_and_click_image_optional(self, image_names: list, timeout: float = 10.0, delay: float = 1.0) -> bool:
        """Find one of multiple images on screen and click it (tries each in order)"""
        logger.info(f"Looking for one of: {', '.join([f'{name}.png' for name in image_names])}...")
        deadline = time.monotonic() + timeout
        
        # Check which images are loaded
        available_templates = {}
        for image_name in image_names:
            if image_name in self.menu_images:
                available_templates[image_name] = self.menu_images[image_name]
        
        if not available_templates:
            logger.error(f"None of the images {image_names} are loaded in menu_images")
            return False
        
        while time.monotonic() < deadline:
            # Try each image in order
            for image_name, template in available_templates.items():
                box = self.find_image_template(template, threshold=0.7)
                if box:
                    # Click at the center of the found image
                    center_x = box.x + box.width // 2
                    center_y = box.y + box.height // 2
                    logger.info(f"Found {image_name}.png at ({center_x}, {center_y}), clicking...")
                    self.click(center_x, center_y)
                    self.sleep(delay)
                    return True
            
            self.sleep(0.2)
            self.next_frame()
        
        logger.warning(f"Timeout: Could not find any of {image_names} after {timeout} seconds")
        return False
    
    def navigate_to_fishing_spot(self, spot_name: str, e_count: int = 0):
        """Navigate through menu to fishing spot teleport using image detection"""
        logger.info(f"Navigating to {spot_name} fishing spot (E count: {e_count})")
        
        # Step 1: Press ESC
        logger.info("Pressing ESC")
        self.send_key("esc", down_time=0.1)
        self.sleep(1.0)
        self.next_frame()
        
        # Step 2: Find and click inventory.png
        logger.info("Step 2: Looking for inventory.png...")
        if not self.find_and_click_image("inventory", timeout=10.0, delay=1.0):
            logger.error("Failed to find inventory.png")
            return False
        
        # Step 2.5: Find and click fishingsupplies.png or fishingsupplies2.png
        logger.info("Step 2.5: Looking for fishingsupplies.png or fishingsupplies2.png...")
        if not self.find_and_click_image_optional(["fishingsupplies", "fishingsupplies2"], timeout=10.0, delay=1.0):
            logger.error("Failed to find fishingsupplies.png or fishingsupplies2.png")
            return False
        
        # Step 3: Find and click rod.png or rod2.png
        logger.info("Step 3: Looking for rod.png or rod2.png...")
        if not self.find_and_click_image_optional(["rod", "rod2"], timeout=10.0, delay=1.0):
            logger.error("Failed to find rod.png or rod2.png")
            return False
        
        # Step 4: Find and click inventory3.png
        logger.info("Step 4: Looking for inventory3.png...")
        if not self.find_and_click_image("inventory3", timeout=10.0, delay=1.0):
            logger.error("Failed to find inventory3.png")
            return False
        
        # Step 5: Press E key (if needed) - before locatefishing click
        if e_count > 0:
            logger.info(f"Waiting 2 seconds after clicking inventory3 for menu to load...")
            self.sleep(2.0)
            self.next_frame()  # Update frame before pressing E
            for i in range(e_count):
                logger.info(f"Pressing E key ({i+1}/{e_count})")
                # Use explicit down/up for better reliability
                self.send_key_down("e")
                self.sleep(0.2)  # Hold key down for 0.2 seconds
                self.send_key_up("e")
                self.sleep(1.0)  # Wait after each E press for menu to respond
                self.next_frame()  # Update frame after each E press
        
        # Step 6: Find and click locatefishing.png
        logger.info("Step 6: Looking for locatefishing.png...")
        if not self.find_and_click_image("locatefishing", timeout=10.0, delay=1.0):
            logger.error("Failed to find locatefishing.png")
            return False
        
        # Step 7: Find and click teleport.png
        logger.info("Step 7: Looking for teleport.png...")
        if not self.find_and_click_image("teleport", timeout=10.0, delay=1.0):
            logger.error("Failed to find teleport.png")
            return False
        
        # Step 8: Wait for map to load - use image detection for Purgatorio and Icelake, fixed wait for Sewers
        if spot_name == "Sewers":
            wait_time = 5.0
            logger.info(f"Waiting {wait_time} seconds after teleport for loading to complete (Sewers)...")
            self.sleep(wait_time)
        elif spot_name == "Purgatorio":
            logger.info("Step 8: Waiting for Purgatorio.png to appear (up to 30 seconds)...")
            if not self.wait_for_image("Purgatorio", timeout=30.0):
                logger.warning("Purgatorio.png not found after 30 seconds, continuing anyway...")
        elif spot_name == "Icelake":
            logger.info("Step 8: Waiting for Icelake.png to appear (up to 30 seconds)...")
            if not self.wait_for_image("Icelake", timeout=30.0):
                logger.warning("Icelake.png not found after 30 seconds, continuing anyway...")
        
        logger.info(f"Successfully navigated to {spot_name}")
        return True
    
    def execute_spot_script(self, script_path: str, png_path: str):
        """Execute a spot navigation script, checking for PNG before W key presses"""
        logger.info(f"Executing script: {script_path}")
        
        # Read and parse the script (using relative path from working directory)
        if not os.path.exists(script_path):
            logger.error(f"Script file not found: {script_path}")
            return False
        
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # Execute the script with pyautogui calls replaced by ok-dna methods
        logger.info("Executing script actions...")
        try:
            # Create a modified script that uses ok-dna methods
            modified_script = script_content
            
            # Remove pyautogui import statements
            modified_script = re.sub(r'^import pyautogui\s*$', '', modified_script, flags=re.MULTILINE)
            modified_script = re.sub(r'^from pyautogui import.*$', '', modified_script, flags=re.MULTILINE)
            
            # Remove all mouse movement lines (moveTo) - we'll click directly at coordinates
            modified_script = re.sub(r'^.*pyautogui\.moveTo.*$', '', modified_script, flags=re.MULTILINE)
            
            # Skip all actions until the first W key press
            # Find the first W key press and remove everything before it
            # This skips the initial ESC and any mouse clicks that happen before walking
            w_pattern = r'pyautogui\.press\([\'"]w[\'"]\)'
            w_match = re.search(w_pattern, modified_script, re.IGNORECASE)
            if w_match:
                # Remove everything before the first W press
                modified_script = modified_script[w_match.start():]
                logger.debug("Skipped all actions before first W key press")
            else:
                # If no W press found, skip the first ESC sequence and early mouse actions
                # Skip first ESC press sequence
                patterns = [
                    r'^time\.sleep\([^)]+\)\s*\n\s*pyautogui\.press\([\'"]esc[\'"]\)\s*\n\s*time\.sleep\([^)]+\)\s*\n',
                    r'time\.sleep\([^)]+\)\s*\n\s*pyautogui\.press\([\'"]esc[\'"]\)\s*\n\s*time\.sleep\([^)]+\)',
                ]
                for pattern in patterns:
                    modified_script = re.sub(pattern, '', modified_script, count=1, flags=re.MULTILINE)
                
                # Skip first few mouseDown/mouseUp pairs (usually 2-3 clicks)
                mouse_pattern = r'pyautogui\.mouseDown\([^)]+\)\s*\n\s*time\.sleep\([^)]+\)\s*\n\s*pyautogui\.mouseUp\([^)]+\)'
                modified_script = re.sub(mouse_pattern, '', modified_script, count=3, flags=re.MULTILINE)
                logger.debug("Skipped first ESC and early mouse actions")
            
            # Replace pyautogui calls with ok-dna methods AFTER skipping
            modified_script = modified_script.replace('pyautogui.press', '_ok_press')
            modified_script = modified_script.replace('pyautogui.sleep', '_ok_sleep')
            modified_script = modified_script.replace('pyautogui.mouseDown', '_ok_mouse_down')
            modified_script = modified_script.replace('pyautogui.mouseUp', '_ok_mouse_up')
            modified_script = modified_script.replace('pyautogui.click', '_ok_click')
            
            # Track if we've seen the first W key press (PNG already checked after teleport)
            first_w_pressed = False
            esc_skip_count = 0  # Track ESC presses to skip first one
            
            # Define replacement functions that convert pyautogui to ok-dna methods
            def _ok_press(key):
                nonlocal first_w_pressed, esc_skip_count
                # Skip the first ESC press - we already navigated
                if key.lower() == 'esc':
                    esc_skip_count += 1
                    if esc_skip_count == 1:
                        logger.debug("Skipping first ESC key (already navigated)")
                        return
                    else:
                        logger.debug("Pressing ESC key")
                        self.send_key("esc", down_time=0.1)
                        self.sleep(0.01)
                        return
                
                # Check for W key - PNG already checked after teleport
                if key.lower() == 'w':
                    if not first_w_pressed:
                        # PNG already checked after teleport, hold W for 2 seconds
                        first_w_pressed = True
                        logger.debug("Holding W key for 2 seconds (first press after PNG check)")
                        self.send_key_down("w")
                        self.sleep(2.0)  # Hold for 2 seconds
                        self.send_key_up("w")
                    else:
                        logger.debug("Pressing W key")
                        self.send_key("w", down_time=0.1)
                    # Check cancellation after each key press
                    self.sleep(0.01)  # Small sleep to allow cancellation check
                elif key.lower() == 'f':
                    logger.debug("Pressing F key")
                    self.send_key("f", down_time=0.1)
                    self.sleep(0.01)  # Small sleep to allow cancellation check
                elif key.lower() == 'a':
                    logger.debug("Pressing A key")
                    self.send_key("a", down_time=0.1)
                    self.sleep(0.01)  # Small sleep to allow cancellation check
                else:
                    logger.debug(f"Pressing key: {key}")
                    self.send_key(key, down_time=0.1)
                    self.sleep(0.01)  # Small sleep to allow cancellation check
            
            def _ok_sleep(duration):
                # Use self.sleep() which handles cancellation automatically
                # For longer sleeps, break into smaller chunks to allow cancellation
                # This ensures the stop button works properly
                if duration > 0.1:
                    elapsed = 0.0
                    check_interval = 0.05  # Smaller interval for better cancellation responsiveness
                    while elapsed < duration:
                        self.sleep(check_interval)  # sleep() raises TaskDisabledException if disabled
                        elapsed += check_interval
                    # Sleep remaining time
                    remaining = duration - elapsed
                    if remaining > 0:
                        self.sleep(remaining)
                else:
                    self.sleep(duration)  # sleep() raises TaskDisabledException if disabled
            
            def _ok_mouse_down(x, y):
                # Press mouse down at coordinates (left button by default)
                self.mouse_down(x=int(x), y=int(y), key="left")
                self.sleep(0.01)  # Small sleep to allow cancellation check
            
            def _ok_mouse_up(x, y):
                # Release mouse up (left button by default)
                # Note: mouse_up doesn't need coordinates, but we keep the parameter for compatibility
                self.mouse_up(key="left")
                self.sleep(0.01)  # Small sleep to allow cancellation check
            
            def _ok_click(x, y):
                # Click directly at coordinates
                self.click(int(x), int(y))
                self.sleep(0.01)  # Small sleep to allow cancellation check
            
            # Execute modified script in a controlled namespace
            namespace = {
                '_ok_press': _ok_press,
                '_ok_sleep': _ok_sleep,
                '_ok_mouse_down': _ok_mouse_down,
                '_ok_mouse_up': _ok_mouse_up,
                '_ok_click': _ok_click,
                'time': time,
            }
            try:
                exec(modified_script, namespace)
                logger.info("Script execution completed")
                return True
            except TaskDisabledException:
                logger.info("Script execution cancelled by user")
                raise  # Re-raise to stop the entire task
            
        except TaskDisabledException:
            # Re-raise TaskDisabledException to stop the entire task
            raise
        except Exception as e:
            logger.error(f"Error executing script: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def find_fish_and_interact(self, fish_png_path: str = "mod/fish/fish.png", timeout: float = 30.0):
        """Keep pressing W until fish.png is found, then press F, click, and press spacebar"""
        logger.info("Looking for fish.png while holding W...")
        deadline = time.monotonic() + timeout
        
        # Load fish.png template
        if not os.path.exists(fish_png_path):
            logger.error(f"Fish PNG file not found: {fish_png_path}")
            return False
        
        try:
            pil_img = Image.open(fish_png_path)
            img_array = np.array(pil_img)
            template = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error(f"Failed to load fish.png template {fish_png_path}: {e}")
            return False
        
        # Hold W key down continuously
        self.send_key_down("w")
        logger.info("Holding W key down...")
        
        try:
            # Keep checking for fish.png while W is held down
            while time.monotonic() < deadline:
                # Check for fish.png
                box = self.find_image_template(template, threshold=0.7)
                if box:
                    logger.info("Found fish.png!")
                    self.send_key_up("w")  # Stop pressing W
                    self.sleep(0.5)  # Small delay
                    
                    # Press F on the fish
                    logger.info("Pressing F on fish...")
                    self.send_key("f", down_time=0.1)
                    self.sleep(1.0)
                    
                    # Click on (1760, 950)
                    logger.info("Clicking at (1760, 950)...")
                    self.click(1760, 950)
                    self.sleep(1.0)
                    
                    # Don't press spacebar - AutoFishTask will handle it
                    
                    return True
                
                self.sleep(0.2)  # Check every 0.2 seconds
                self.next_frame()
        finally:
            # Make sure W key is released even if we timeout or error
            self.send_key_up("w")
        
        # Timeout
        logger.warning(f"Timeout waiting for fish.png after {timeout} seconds")
        return False
    
    def exit_fishing_menu(self):
        """Exit fishing menu by pressing ESC twice with delay"""
        logger.info("Exiting fishing menu (ESC x2)...")
        self.send_key("esc", down_time=0.1)
        self.sleep(1.0)
        self.send_key("esc", down_time=0.1)
        self.sleep(1.0)
    
    def detect_no_more_fish(self, quick_check: bool = False) -> bool:
        """Detect if 'no more fish' image appears on screen using image matching"""
        no_fish_png_path = "mod/fish/nomorefish.png"
        
        if not os.path.exists(no_fish_png_path):
            logger.debug(f"No more fish PNG file not found: {no_fish_png_path}")
            return False
        
        # Load nomorefish.png template
        try:
            pil_img = Image.open(no_fish_png_path)
            img_array = np.array(pil_img)
            template = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error(f"Failed to load nomorefish.png template {no_fish_png_path}: {e}")
            return False
        
        if quick_check:
            # Quick single check
            box = self.find_image_template(template, threshold=0.7)
            if box:
                logger.info("Detected 'no more fish' image")
                return True
            return False
        
        # Full check with timeout
        cfg = self.config
        timeout = cfg.get("No Fish Timeout", 10.0)
        deadline = time.monotonic() + timeout
        
        logger.info("Checking for 'no more fish' image...")
        while time.monotonic() < deadline:
            box = self.find_image_template(template, threshold=0.7)
            if box:
                logger.info("Detected 'no more fish' image")
                return True
            
            self.sleep(0.5)
            self.next_frame()
        
        logger.debug("No 'no more fish' image detected")
        return False
    
    # ===== Fishing methods (merged from AutoFishTask) =====
    
    def check_no_more_fish(self) -> bool:
        """Check if 'no more fish' image appears (wrapper for detect_no_more_fish)"""
        return self.detect_no_more_fish(quick_check=True)
    
    def find_fish_cast(self) -> tuple[bool, tuple]:
        """查找 fish_cast 图标（抛竿/收杆），返回 (found, center)"""
        CAST_THRESHOLD = 0.8  # fish_cast 匹配阈值
        fish_box = self.box_of_screen_scaled(3840, 2160, 3147, 1566, 3383, 1797, name="fish_bite")
        box = self.find_one("fish_cast", box=fish_box, threshold=CAST_THRESHOLD) or self.find_one("fish_ease",
                                                                                                  box=fish_box,
                                                                                                  threshold=CAST_THRESHOLD)
        if box:
            return True, (box.x + box.width // 2, box.y + box.height // 2)
        return False, (0, 0)

    def find_fish_bite(self) -> tuple[bool, tuple]:
        """查找 fish_bite 图标（等待鱼上钩），返回 (found, center)"""
        BITE_THRESHOLD = 0.8  # fish_bite 匹配阈值
        fish_box = self.box_of_screen_scaled(
            3840, 2160, 3147, 1566, 3383, 1797, name="fish_bite"
        )
        box = self.find_one("fish_bite", box=fish_box, threshold=BITE_THRESHOLD)
        if box:
            return True, (box.x + box.width // 2, box.y + box.height // 2)
        return False, (0, 0)

    def find_fish_chance(self) -> tuple[bool, tuple]:
        """查找 fish_chance 图标（授渔以鱼），返回 (found, center)"""
        CHANCE_THRESHOLD = 0.8  # fish_chance 匹配阈值
        fish_chance_box = self.box_of_screen_scaled(3840, 2160, 3467, 1797, 3703, 2033, name="fish_chance")
        box = self.find_one("fish_chance", box=fish_chance_box, threshold=CHANCE_THRESHOLD)
        if box:
            return True, (box.x + box.width // 2, box.y + box.height // 2)
        return False, (0, 0)
    
    def find_bar_and_fish_by_area(self):
        """基于 ROI 找到鱼条和鱼标的区域与面积

        返回：((has_bar, bar_center, bar_rect), (has_icon, icon_center, icon_rect))
        注意：bar_center 和 icon_center 是相对于 ROI 内部的坐标，bar_rect 和 icon_rect 也是
        """
        # 获取 ROI 区域
        box = self.box_of_screen_scaled(1920, 1080, 1620, 325, 1645, 725, name="fish_roi")

        try:
            frame_height, _ = self.frame.shape[:2]
            res_ratio = frame_height / 1080
            roi_img = box.crop_frame(self.frame)

            # 转换为灰度图
            gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)

            # 二值化：提取亮色区域（鱼条和图标都是白色/亮色）
            _, scene_bin = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

            # 查找轮廓
            contours, _ = cv2.findContours(scene_bin, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

            # 收集所有符合最小面积的轮廓
            blobs = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > self.ICON_MIN_AREA * res_ratio ** 2:
                    blobs.append({"contour": contour, "area": area})

            # 按面积降序排列
            blobs.sort(key=lambda b: b["area"], reverse=True)

            has_bar = has_icon = False
            bar_center = bar_rect = icon_center = icon_rect = None
            bar_area = icon_area = 0.0

            # 查找鱼条（最大的符合条件的轮廓）
            for blob in blobs:
                if blob["area"] > self.BAR_MIN_AREA * res_ratio ** 2:
                    contour = blob["contour"]
                    moments = cv2.moments(contour)
                    if moments["m00"] > 0:
                        has_bar = True
                        bar_area = blob["area"]
                        bar_center = (
                            int(moments["m10"] / moments["m00"]),
                            int(moments["m01"] / moments["m00"]),
                        )
                        x, y, w, h = cv2.boundingRect(contour)
                        bar_rect = (x, y, x + w, y + h)
                    break

            # 查找鱼标（第二大的符合条件的轮廓，排除鱼条）
            for blob in blobs:
                if blob["area"] == bar_area:
                    continue
                if self.ICON_MIN_AREA * res_ratio ** 2 < blob["area"] < self.ICON_MAX_AREA * res_ratio ** 2:
                    contour = blob["contour"]
                    moments = cv2.moments(contour)
                    if moments["m00"] > 0:
                        has_icon = True
                        icon_area = blob["area"]
                        icon_center = (
                            int(moments["m10"] / moments["m00"]),
                            int(moments["m01"] / moments["m00"]),
                        )
                        x, y, w, h = cv2.boundingRect(contour)
                        icon_rect = (x, y, x + w, y + h)
                    break

            if has_bar:
                zone_ratio = bar_area / box.area()
                if self.CONTROL_ZONE_RATIO <= 0 or abs(
                        zone_ratio - self.CONTROL_ZONE_RATIO) / self.CONTROL_ZONE_RATIO > 0.1:
                    self.CONTROL_ZONE_RATIO = zone_ratio
                    self.log_info(f"set CONTROL_ZONE_RATIO {self.CONTROL_ZONE_RATIO}")

            return (has_bar, bar_center, bar_rect), (has_icon, icon_center, icon_rect)
        except TaskDisabledException:
            raise
        except Exception as e:
            logger.error(f"find_bar_and_fish_by_area error: {e}")
            return (False, None, None), (False, None, None)

    def phase_start(self) -> bool:
        """Start phase: cast and wait for fish to bite"""
        cfg = self.config
        self.fishing_stats["current_phase"] = "Casting"
        self.info_set("Current Phase", "Casting")

        start_deadline = time.monotonic() + cfg.get("MAX_START_SEC", 20.0)

        has_cast_icon, _ = self.find_fish_cast()
        self.fishing_stats["last_cast_icon_found"] = has_cast_icon

        # Check for chance opportunity
        has_chance_icon, _ = self.find_fish_chance()
        if has_chance_icon:
            logger.info("Detected fish_chance (Chance Used) -> Press E key to use chance cast")
            self.fishing_stats["chance_used"] = self.fishing_stats.get("chance_used", 0) + 1
            self.info_set("Chance Used (Bigger Fish)", self.fishing_stats["chance_used"])
            # Previous round's fish used as bait, don't count in rounds
            if self.fishing_stats["rounds_completed"] > 0:
                self.fishing_stats["rounds_completed"] -= 1
                self.info_set("Rounds Completed", self.fishing_stats["rounds_completed"])
                logger.info(f"Previous round's fish used as bait, rounds adjusted to: {self.fishing_stats['rounds_completed']}")
            self.send_key("e", down_time=0.06)
        elif not has_cast_icon:
            logger.info("fish_cast not found in start phase, trying to press space to cast and wait for fish_bite")
            self.send_key("space", down_time=0.06)
        else:
            logger.info("Found fish_cast -> Press space to cast")
            self.send_key("space", down_time=0.06)
        
        # Quick check for "no more fish" image after casting
        self.sleep(0.5)
        self.next_frame()
        if self.check_no_more_fish():
            logger.info("Detected 'no more fish' - stopping fishing")
            raise Exception("No more fish available")

        logger.info("Waiting for fish_bite to appear...")
        ret = self.wait_until(lambda: self.find_fish_bite()[0], time_out=start_deadline, raise_if_not_found=False)
        self.fishing_stats["last_bite_icon_found"] = ret
        if ret:
            logger.info("Found fish_bite -> Waiting for fish to bite")
        else:
            logger.info("Timeout: Waiting for fish_bite to appear")
            return False

        # Wait for fish_bite to disappear (fish bit the hook)
        logger.info("Waiting for fish to bite...")
        bite_gone_stable_time = 0.5
        ret = self.wait_until(lambda: not self.find_fish_bite()[0], time_out=start_deadline,
                              settle_time=bite_gone_stable_time)
        self.fishing_stats["last_bite_icon_found"] = not ret
        if not ret:
            logger.info("Timeout waiting for fish_bite to disappear")
            return False

        # Wait for fish_cast to appear (reel prompt)
        logger.info("Waiting for fish_cast to appear (reel prompt)...")
        ret = self.wait_until(lambda: self.find_fish_cast()[0], time_out=start_deadline)
        self.fishing_stats["last_cast_icon_found"] = ret
        if ret:
            logger.info("Found fish_cast -> Press space to reel, entering fighting phase")
            self.send_key("space", down_time=0.06)
            return True

        logger.info("Timeout: Waiting for fish_cast to appear")
        return False

    def phase_fight(self) -> bool:
        """Fighting phase: control the fishing bar"""
        cfg = self.config
        self.fishing_stats["current_phase"] = "Fighting"
        self.info_set("Current Phase", "Fighting")
        logger.info("Entering fighting phase...")

        BAR_MISSING_TIMEOUT = 2.5
        MERGE_GRACE_SECONDS = 0.20
        fight_deadline = time.monotonic() + cfg.get("MAX_FIGHT_SEC", 60.0)

        is_holding_space = False
        icon_was_visible_prev = False
        last_known_icon_y_relative = 0.0

        bar_missing_start_time = None
        merge_start_time = None

        def set_hold(target_hold: bool):
            nonlocal is_holding_space
            if target_hold != is_holding_space:
                if target_hold:
                    self.send_key_down("space")
                else:
                    self.send_key_up("space")
                is_holding_space = target_hold
                self.fishing_stats["last_hold_state"] = is_holding_space

        try:
            while True:
                now = time.monotonic()
                if now >= fight_deadline:
                    logger.info("Fighting timeout")
                    return False

                (has_bar, bar_center, bar_rect), (has_icon, icon_center, icon_rect) = self.find_bar_and_fish_by_area()

                if has_bar and has_icon:
                    last_known_icon_y_relative = icon_center[1] - bar_center[1]

                if not has_bar:
                    if bar_missing_start_time is None:
                        bar_missing_start_time = now
                    elif now - bar_missing_start_time >= BAR_MISSING_TIMEOUT:
                        logger.info(f"Fish bar missing for more than {BAR_MISSING_TIMEOUT}s -> Fighting ended")
                        return True
                else:
                    bar_missing_start_time = None

                if has_bar and bar_rect:
                    bar_top = bar_rect[1]
                    bar_bottom = bar_rect[3]
                    bar_height = bar_bottom - bar_top

                    if bar_height <= 0:
                        bar_height = 1

                    control_zone_ratio = self.CONTROL_ZONE_RATIO
                    control_height = int(bar_height * control_zone_ratio)
                    control_top = bar_top + control_height
                    control_bottom = bar_bottom - control_height

                    is_merged = has_bar and (not has_icon) and icon_was_visible_prev

                    if has_icon:
                        merge_start_time = None
                        icon_y = icon_center[1]

                        if icon_y < control_top:
                            set_hold(True)
                        elif icon_y > control_bottom:
                            set_hold(False)
                    else:
                        if is_merged:
                            if merge_start_time is None:
                                merge_start_time = now
                                self.fishing_stats["last_merge_event"] = (f"merged, last_rel={last_known_icon_y_relative:.1f}")
                            elapsed = now - merge_start_time
                            if elapsed <= MERGE_GRACE_SECONDS:
                                if last_known_icon_y_relative < 0:
                                    set_hold(True)
                                else:
                                    set_hold(False)
                        else:
                            merge_start_time = None
                else:
                    set_hold(False)

                icon_was_visible_prev = has_icon
                self.next_frame()

        except TaskDisabledException:
            self.send_key_up("space")
            raise
        finally:
            self.send_key_up("space")

    def phase_end(self) -> bool:
        """End phase: collect fish and return to casting"""
        cfg = self.config
        self.fishing_stats["current_phase"] = "Reeling"
        self.info_set("Current Phase", "Reeling")

        wait_time = cfg.get("END_WAIT_SPACE", 0.5)
        logger.info(f"Waiting {wait_time}s for fish info display to end...")
        self.sleep(wait_time)

        logger.info("Reeling (Space)")
        self.send_key("space", down_time=0.06)

        confirm_deadline = time.monotonic() + cfg.get("MAX_END_SEC", 20.0)
        while time.monotonic() < confirm_deadline:
            has_cast_icon, _ = self.find_fish_cast()
            has_bite_icon, _ = self.find_fish_bite()
            has_chance_icon, _ = self.find_fish_chance()
            self.fishing_stats["last_cast_icon_found"] = has_cast_icon
            self.fishing_stats["last_bite_icon_found"] = has_bite_icon
            if has_cast_icon or has_bite_icon or has_chance_icon:
                if has_chance_icon:
                    logger.info("Confirmed returned to casting interface (detected chance used)")
                else:
                    logger.info("Confirmed returned to casting interface")
                return True
            self.send_key("space", down_time=0.06)
            self.sleep(0.3)
        logger.info("End phase confirmation failed")
        return False
    
    def run_fishing_loop(self, max_rounds: int = 0, initial_total: int = 0):
        """Run the fishing loop for current spot"""
        cfg = self.config
        
        # Initialize fishing stats for this spot
        self.fishing_stats = {
            "rounds_completed": 0,
            "total_time": 0.0,
            "start_time": time.time(),
            "current_phase": "Preparing",
            "chance_used": 0,
        }
        
        self.info_set("Rounds Completed", 0)
        self.info_set("Chance Used (Bigger Fish)", 0)
        self.info_set("Current Phase", "Preparing")
        if max_rounds > 0:
            self.info_set("Target Rounds", max_rounds)

        while True:
            try:
                if max_rounds > 0 and self.fishing_stats["rounds_completed"] >= max_rounds:
                    has_chance_icon, _ = self.find_fish_chance()
                    if has_chance_icon:
                        logger.info("Detected chance used, previous round not counted, continuing fishing...")
                    else:
                        elapsed_time = time.time() - self.fishing_stats["start_time"]
                        hours = int(elapsed_time // 3600)
                        minutes = int((elapsed_time % 3600) // 60)
                        seconds = int(elapsed_time % 60)
                        logger.info("=" * 50)
                        logger.info(f"✓ Completed target rounds: {self.fishing_stats['rounds_completed']} rounds")
                        logger.info(f"✓ Total time: {hours:02d}:{minutes:02d}:{seconds:02d}")
                        if self.fishing_stats["rounds_completed"] > 0:
                            avg_time = elapsed_time / self.fishing_stats["rounds_completed"]
                            logger.info(f"✓ Average per round: {avg_time:.1f} seconds")
                        logger.info("Fishing completed!")
                        logger.info("=" * 50)
                        if cfg.get("发出声音提醒", False):
                            self.soundBeep()
                        break

                if not self.phase_start():
                    self.sleep(1.0)
                    continue
                if not self.phase_fight():
                    self.sleep(1.0)
                    continue
                if not self.phase_end():
                    self.sleep(1.0)
                    continue

                # Complete one round
                self.fishing_stats["rounds_completed"] += 1
                self.info_set("Rounds Completed", self.fishing_stats["rounds_completed"])
                
                # Update current spot and total fish counts in real-time
                self.current_spot_fish = self.fishing_stats["rounds_completed"]
                self.total_fish_caught = initial_total + self.current_spot_fish
                self.info_set("Fish Caught (Current Spot)", self.current_spot_fish)
                self.info_set("Total Fish Caught", self.total_fish_caught)

                elapsed_time = time.time() - self.fishing_stats["start_time"]
                hours = int(elapsed_time // 3600)
                minutes = int((elapsed_time % 3600) // 60)
                seconds = int(elapsed_time % 60)
                if self.fishing_stats["rounds_completed"] > 0:
                    avg_time = elapsed_time / self.fishing_stats["rounds_completed"]
                    logger.info("=" * 50)
                    logger.info(f"✓ Completed round {self.fishing_stats['rounds_completed']}")
                    logger.info(f"  Total time: {hours:02d}:{minutes:02d}:{seconds:02d}")
                    logger.info(f"  Average per round: {avg_time:.1f} seconds")
                    if max_rounds > 0:
                        remaining = max_rounds - self.fishing_stats["rounds_completed"]
                        logger.info(f"  Remaining rounds: {remaining}")
                    logger.info("=" * 50)

                self.sleep(1.0)
                self.sleep(1.0)
            except TaskDisabledException:
                # Preserve stats before re-raising
                if hasattr(self, 'fishing_stats'):
                    self.info_set("Rounds Completed", self.fishing_stats.get("rounds_completed", 0))
                    self.info_set("Chance Used (Bigger Fish)", self.fishing_stats.get("chance_used", 0))
                if hasattr(self, 'total_fish_caught'):
                    self.info_set("Total Fish Caught", self.total_fish_caught)
                raise
            except Exception as e:
                if "No more fish available" in str(e):
                    logger.info("No more fish available - stopping fishing")
                    break
                logger.error(f"Fishing loop error: {e}")
                break
        
        # Final stats update before returning
        if hasattr(self, 'fishing_stats'):
            final_rounds = self.fishing_stats.get("rounds_completed", 0)
            final_chance = self.fishing_stats.get("chance_used", 0)
            self.info_set("Rounds Completed", final_rounds)
            self.info_set("Chance Used (Bigger Fish)", final_chance)
            # Update total fish caught (it should already be updated in real-time, but ensure it's set here too)
            if hasattr(self, 'total_fish_caught'):
                self.info_set("Total Fish Caught", self.total_fish_caught)
        
        return self.fishing_stats["rounds_completed"]
    
    def do_run(self):
        """Main execution loop"""
        # Initialize stats tracking
        self.total_fish_caught = 0
        self.current_spot_fish = 0
        
        cfg = self.config
        max_rounds_per_spot = cfg.get("Max Rounds Per Spot", 0)
        
        # Filter spots based on config options
        enabled_spots = []
        spot_enable_map = {
            "Purgatorio": cfg.get("Enable Purgatorio", True),
            "Icelake": cfg.get("Enable Icelake", True),
            "Sewers": cfg.get("Enable Sewers", True),
        }
        
        for spot_info in self.spot_scripts:
            spot_name = spot_info["name"]
            if spot_enable_map.get(spot_name, True):
                enabled_spots.append(spot_info)
            else:
                logger.info(f"Skipping {spot_name} (disabled in config)")
        
        if not enabled_spots:
            logger.error("No fishing spots enabled! Please enable at least one spot in config.")
            return
        
        logger.info("=" * 50)
        logger.info("Auto Fish Multi Spot Task Started")
        logger.info(f"Fishing spots enabled: {len(enabled_spots)}/{len(self.spot_scripts)}")
        enabled_names = [s["name"] for s in enabled_spots]
        logger.info(f"Order: {' -> '.join(enabled_names)}")
        if max_rounds_per_spot > 0:
            logger.info(f"Max rounds per spot: {max_rounds_per_spot}")
        logger.info("=" * 50)
        
        # Main loop: execute each enabled spot script in order
        for spot_index, spot_info in enumerate(enabled_spots):
            try:
                spot_name = spot_info["name"]
                script_path = spot_info["py"]
                png_path = spot_info["png"]
                e_count = spot_info.get("e_count", 0)
                
                logger.info("=" * 50)
                logger.info(f"Starting spot {spot_index + 1}/{len(enabled_spots)}: {spot_name}")
                logger.info("=" * 50)
                
                # Update info display for current spot
                self.info_set("Current Spot", f"{spot_name} ({spot_index + 1}/{len(enabled_spots)})")
                self.info_set("Status", f"Navigating to {spot_name}")
                self.current_spot_fish = 0
                self.info_set("Fish Caught (Current Spot)", 0)
                
                # Step 1: Navigate menu to fishing spot teleport (5 sec wait for Sewers, 25 sec for others)
                self.navigate_to_fishing_spot(spot_name, e_count)
                
                # Step 1.5: Sewers-specific - look for fish.png and interact (no W needed, already waited 5 sec in navigate)
                if spot_name == "Sewers":
                    logger.info("Sewers: Looking for fish.png (up to 1 minute)...")
                    if self.wait_for_png("mod/fish/fish.png", timeout=60.0):
                        logger.info("Found fish.png, pressing F and clicking to enter fishing mode")
                        # Press F on the fish
                        self.send_key("f", down_time=0.1)
                        self.sleep(1.0)
                        # Click on (1760, 950)
                        self.click(1760, 950)
                        self.sleep(1.0)
                    else:
                        logger.warning("fish.png not found after 1 minute, continuing anyway...")
                else:
                    # Step 2: Icelake-specific movement - tap 'a' twice
                    if spot_name == "Icelake":
                        logger.info("Icelake: Waiting for map to stabilize, then tapping 'a' twice...")
                        self.sleep(1.0)  # Wait for map to fully load
                        self.next_frame()  # Update frame
                        logger.info("Icelake: Tapping 'a' (first tap)...")
                        self.send_key("a", down_time=0.1)
                        self.sleep(0.3)  # Small delay between taps
                        logger.info("Icelake: Tapping 'a' (second tap)...")
                        self.send_key("a", down_time=0.1)
                        self.sleep(0.5)  # Small delay after taps
                        logger.info("Icelake: Finished tapping 'a' twice, proceeding to find fish...")
                
                # Step 4: Hold W and find fish.png, then interact (for Purgatorio and Icelake, skip for Sewers)
                if spot_name != "Sewers":
                    logger.info("Step 4: Looking for fish.png while holding W...")
                    self.find_fish_and_interact(fish_png_path="mod/fish/fish.png", timeout=30.0)
                
                # Step 5: Run fishing loop
                logger.info("Starting fishing loop...")
                self.info_set("Status", f"Fishing at {spot_name}")
                # Track initial total before this spot
                initial_total = self.total_fish_caught
                
                # Reset current spot fish count
                self.current_spot_fish = 0
                self.info_set("Fish Caught (Current Spot)", 0)
                
                try:
                    # Run fishing loop directly (no threading needed)
                    fish_caught = self.run_fishing_loop(max_rounds=max_rounds_per_spot, initial_total=initial_total)
                    
                    # Update totals
                    self.current_spot_fish = fish_caught
                    self.total_fish_caught = initial_total + fish_caught
                    self.info_set("Fish Caught (Current Spot)", fish_caught)
                    self.info_set("Total Fish Caught", self.total_fish_caught)
                    
                    logger.info(f"Fishing completed - Caught {fish_caught} fish at {spot_name}")
                    logger.info(f"Total fish caught so far: {self.total_fish_caught}")
                except TaskDisabledException:
                    logger.info("Task disabled, stopping...")
                    break
                except Exception as e:
                    logger.error(f"Fishing error: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Continue to next spot
                finally:
                    # Always exit fishing menu and move to next spot
                    logger.info("Exiting fishing menu and moving to next spot...")
                    self.info_set("Status", f"Exiting {spot_name}")
                    try:
                        self.exit_fishing_menu()
                    except Exception as e:
                        logger.error(f"Error exiting fishing menu: {e}")
                    
                    # Ensure fish count and all stats are updated
                    if hasattr(self, 'fishing_stats'):
                        fish_caught = self.fishing_stats.get("rounds_completed", 0)
                        chance_used = self.fishing_stats.get("chance_used", 0)
                        self.current_spot_fish = fish_caught
                        self.total_fish_caught = initial_total + fish_caught
                        self.info_set("Fish Caught (Current Spot)", fish_caught)
                        self.info_set("Total Fish Caught", self.total_fish_caught)
                        self.info_set("Rounds Completed", fish_caught)
                        self.info_set("Chance Used (Bigger Fish)", chance_used)
                    
                    # Check for "no more fish" image
                    logger.info("Checking for 'no more fish' image...")
                    if self.detect_no_more_fish(quick_check=True):
                        logger.info(f"Detected 'no more fish' image at {spot_name}")
                    else:
                        logger.info(f"No 'no more fish' image detected at {spot_name}, continuing to next spot")
                
                # Step 5: Small delay before next spot
                if spot_index < len(enabled_spots) - 1:
                    logger.info("Waiting before next spot...")
                    self.sleep(2.0)
                
            except TaskDisabledException:
                logger.info("Task disabled, stopping...")
                # Preserve all stats before stopping
                if hasattr(self, 'fishing_stats'):
                    final_rounds = self.fishing_stats.get("rounds_completed", 0)
                    final_chance = self.fishing_stats.get("chance_used", 0)
                    self.info_set("Rounds Completed", final_rounds)
                    self.info_set("Chance Used (Bigger Fish)", final_chance)
                self.info_set("Total Fish Caught", self.total_fish_caught)
                self.info_set("Status", "Stopped")
                break
            except Exception as e:
                logger.error(f"AutoFishMultiSpotTask fatal error at {spot_name}: {e}")
                self.sleep(2.0)
                # Continue to next spot
                continue
        
        logger.info("=" * 50)
        logger.info("Auto Fish Multi Spot Task Completed")
        logger.info(f"Total fish caught across all spots: {self.total_fish_caught}")
        logger.info(f"All fishing spots processed: {' -> '.join(enabled_names)}")
        logger.info("=" * 50)
        
        # Final info update - preserve all stats so they persist after completion/stop
        if hasattr(self, 'fishing_stats'):
            final_rounds = self.fishing_stats.get("rounds_completed", 0)
            final_chance = self.fishing_stats.get("chance_used", 0)
            self.info_set("Rounds Completed", final_rounds)
            self.info_set("Chance Used (Bigger Fish)", final_chance)
            self.info_set("Current Phase", "Completed")
        self.info_set("Status", "Completed")
        self.info_set("Total Fish Caught", self.total_fish_caught)
        # Keep current spot info visible
        if hasattr(self, 'current_spot_fish'):
            self.info_set("Fish Caught (Current Spot)", self.current_spot_fish)
        
        # Teleport back to Purgatorio and AFK there
        logger.info("=" * 50)
        logger.info("Teleporting back to Purgatorio to AFK...")
        logger.info("=" * 50)
        self.info_set("Status", "Returning to Purgatorio")
        try:
            # Navigate to Purgatorio (e_count = 0 for Purgatorio)
            self.navigate_to_fishing_spot("Purgatorio", e_count=0)
            logger.info("Successfully teleported to Purgatorio")
            self.info_set("Status", "AFK at Purgatorio")
            logger.info("Now AFK at Purgatorio. Task will continue running until manually stopped.")
            
            # Keep the task running (AFK/idle)
            while True:
                self.sleep(10.0)  # Sleep in 10-second chunks to allow cancellation
                # Update status periodically to show it's still running
                self.info_set("Status", "AFK at Purgatorio")
        except TaskDisabledException:
            logger.info("Task disabled while AFK at Purgatorio")
            # Preserve all stats before stopping
            if hasattr(self, 'fishing_stats'):
                final_rounds = self.fishing_stats.get("rounds_completed", 0)
                final_chance = self.fishing_stats.get("chance_used", 0)
                self.info_set("Rounds Completed", final_rounds)
                self.info_set("Chance Used (Bigger Fish)", final_chance)
            self.info_set("Total Fish Caught", self.total_fish_caught)
            self.info_set("Status", "Stopped")
            raise
        except Exception as e:
            logger.error(f"Error while AFK at Purgatorio: {e}")
            raise

