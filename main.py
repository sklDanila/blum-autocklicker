import math
import time
import cv2
import keyboard
import mss
import numpy as np
import pygetwindow as gw
import win32api
import win32con
import random


class Logger:
    def __init__(self, prefix=None):
        self.prefix = prefix

    def log(self, data: str):
        if self.prefix:
            print(f"{self.prefix} {data}")
        else:
            print(data)


class AutoClicker:
    def __init__(
        self,
        window_title,
        target_colors_hex,
        nearby_colors_hex,
        logger,
        click_limit=100,
    ):
        self.window_title = window_title
        self.target_colors_hex = target_colors_hex
        self.nearby_colors_hex = nearby_colors_hex
        self.logger = logger
        self.running = False
        self.reset_state()
        self.click_limit = click_limit
        self.game_over_iterations = 50

    def reset_state(self):
        """Resetting the state before starting work"""
        self.clicked_points = []
        self.iteration_count = 0
        self.no_target_counter = 0
        self.click_count = 0
        self.clicks_per_point = {}
        self.clicks_until_break = random.randint(50, 60)

    @staticmethod
    def hex_to_hsv(hex_color):
        hex_color = hex_color.lstrip("#")
        h_len = len(hex_color)
        rgb = tuple(
            int(hex_color[i : i + h_len // 3], 16) for i in range(0, h_len, h_len // 3)
        )
        rgb_normalized = np.array([[rgb]], dtype=np.uint8)
        hsv = cv2.cvtColor(rgb_normalized, cv2.COLOR_RGB2HSV)
        return hsv[0][0]

    @staticmethod
    def click_at(x, y):
        win32api.SetCursorPos((x, y))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)

    def toggle_script(self):
        self.running = not self.running
        r_text = "on" if self.running else "off"
        self.logger.log(f"Status changed: {r_text}")

    def is_near_color(self, hsv_img, center, target_hsvs, radius=8):
        x, y = center
        height, width = hsv_img.shape[:2]
        for i in range(max(0, x - radius), min(width, x + radius + 1)):
            for j in range(max(0, y - radius), min(height, y + radius + 1)):
                distance = math.sqrt((x - i) ** 2 + (y - j) ** 2)
                if distance <= radius:
                    pixel_hsv = hsv_img[j, i]
                    for target_hsv in target_hsvs:
                        if np.allclose(pixel_hsv, target_hsv, atol=[1, 50, 50]):
                            return True
        return False

    def search_and_click_play_button(self, hsv_img, monitor):
        play_button_hsv = self.hex_to_hsv("#FFFFFF")
        lower_bound = np.array([0, 0, 200])
        upper_bound = np.array([179, 50, 255])

        mask = cv2.inRange(hsv_img, lower_bound, upper_bound)
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            if cv2.contourArea(contour) < 300:
                continue

            M = cv2.moments(contour)
            if M["m00"] == 0:
                continue
            cX = int(M["m10"] / M["m00"]) + monitor["left"]
            cY = int(M["m01"] / M["m00"]) + monitor["top"]

            self.click_at(cX, cY)
            self.logger.log(f"Pressed the Play button: {cX} {cY}")
            self.reset_state()
            return True

        return False

    def click_color_areas(self):
        windows = gw.getWindowsWithTitle(self.window_title)
        if not windows:
            self.logger.log(
                f"No window with title found: {self.window_title}. Open the Blum Web App and reopen the script"
            )
            return

        window = windows[0]
        window.activate()
        target_hsvs = [self.hex_to_hsv(color) for color in self.target_colors_hex]
        nearby_hsvs = [self.hex_to_hsv(color) for color in self.nearby_colors_hex]

        with mss.mss() as sct:
            grave_key_code = 41
            keyboard.add_hotkey(grave_key_code, self.toggle_script)

            while True:
                if self.running:
                    monitor = {
                        "top": window.top,
                        "left": window.left,
                        "width": window.width,
                        "height": window.height,
                    }
                    img = np.array(sct.grab(monitor))
                    img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

                    target_found = False

                    for target_hsv in target_hsvs:
                        lower_bound = np.array([max(0, target_hsv[0] - 1), 30, 30])
                        upper_bound = np.array([min(179, target_hsv[0] + 1), 255, 255])
                        mask = cv2.inRange(hsv, lower_bound, upper_bound)
                        contours, _ = cv2.findContours(
                            mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
                        )

                        for contour in reversed(contours):
                            if cv2.contourArea(contour) < 1:
                                continue

                            M = cv2.moments(contour)
                            if M["m00"] == 0:
                                continue
                            cX = int(M["m10"] / M["m00"]) + monitor["left"]
                            cY = int(M["m01"] / M["m00"]) + monitor["top"]

                            if not self.is_near_color(
                                hsv,
                                (cX - monitor["left"], cY - monitor["top"]),
                                nearby_hsvs,
                            ):
                                continue

                            if any(
                                math.sqrt((cX - px) ** 2 + (cY - py) ** 2) < 35
                                for px, py in self.clicked_points
                            ):
                                continue

                            # Checking the number of clicks on one point
                            if (cX, cY) in self.clicks_per_point:
                                self.clicks_per_point[(cX, cY)] += 1
                            else:
                                self.clicks_per_point[(cX, cY)] = 1

                            if self.clicks_per_point[(cX, cY)] > 100:
                                self.logger.log(
                                    f"Exceeded 100 clicks per point: {cX}, {cY}. Go to the Play button."
                                )
                                break

                            cY += 5
                            self.click_at(cX, cY)
                            self.logger.log(f"Clicked: {cX} {cY}")
                            self.clicked_points.append((cX, cY))
                            target_found = True
                            self.click_count += 1

                            # Checking the click limit
                            if self.click_count >= self.click_limit:
                                self.logger.log("Click limit reached, game over.")
                                break

                            # Checking for the need for a break
                            if self.click_count % self.clicks_until_break == 0:
                                break_duration = random.randint(2, 4)
                                self.logger.log(
                                    f"Break for {break_duration} seconds after {self.click_count} clicks."
                                )
                                time.sleep(break_duration)
                                self.clicks_until_break = random.randint(50, 60)

                    if not target_found:
                        self.no_target_counter += 1
                    else:
                        self.no_target_counter = 0

                    if (
                        self.no_target_counter >= self.game_over_iterations
                        or self.click_count >= self.click_limit
                        or any(count > 100 for count in self.clicks_per_point.values())
                    ):
                        self.logger.log("Game over, search for Play button.")
                        if self.search_and_click_play_button(hsv, monitor):
                            self.no_target_counter = (
                                0  # Resetting the counter after pressing Play
                            )

                    time.sleep(0.1)
                    self.iteration_count += 1
                    if self.iteration_count >= 5:
                        self.clicked_points.clear()
                        self.iteration_count = 0


if __name__ == "__main__":
    logger = Logger("[https://t.me/sklit_crypto]")
    logger.log("Welcome to the free autoclicker script for the game Blum")
    logger.log('After starting the mini-game, press the "~" key on your keyboard')
    target_colors_hex = ["#c9e100", "#bae70e"]
    nearby_colors_hex = ["#abff61", "#87ff27"]
    auto_clicker = AutoClicker(
        "TelegramDesktop", target_colors_hex, nearby_colors_hex, logger, click_limit=55
    )
    try:
        auto_clicker.click_color_areas()
    except Exception as e:
        logger.log(f"An error occurred: {e}")
    for i in reversed(range(5)):
        i += 1
        print(f"The script will exit in {i}")
        time.sleep(1)
