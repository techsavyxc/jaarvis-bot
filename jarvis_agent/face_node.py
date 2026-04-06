#!/usr/bin/env python3
"""JARVIS Face Display Node - Animated eyes"""

import pygame
import math
import random
import time
import threading

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    import json
    ROS_AVAILABLE = True
except:
    ROS_AVAILABLE = False

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
CYAN = (0, 255, 255)
BLUE = (0, 150, 255)
GREEN = (0, 255, 100)
RED = (255, 50, 50)
YELLOW = (255, 255, 0)
PURPLE = (150, 50, 255)
ORANGE = (255, 150, 0)
PINK = (255, 100, 200)


class Eye:
    def __init__(self, center_x, center_y, size=80):
        self.center_x = center_x
        self.center_y = center_y
        self.size = size
        self.pupil_size = size // 3
        self.pupil_offset_x = 0
        self.pupil_offset_y = 0
        self.target_offset_x = 0
        self.target_offset_y = 0
        self.blink_state = 1.0
        self.is_blinking = False
        self.squint = 0
        self.wide = 0

    def update(self, dt):
        self.pupil_offset_x += (self.target_offset_x - self.pupil_offset_x) * 0.15
        self.pupil_offset_y += (self.target_offset_y - self.pupil_offset_y) * 0.15

    def draw(self, screen, color=CYAN):
        eye_height = int(self.size * self.blink_state)
        if eye_height < 5:
            pygame.draw.line(screen, color,
                           (self.center_x - self.size, self.center_y),
                           (self.center_x + self.size, self.center_y), 4)
            return
        if self.squint > 0:
            eye_height = int(eye_height * (1 - self.squint * 0.5))
        if self.wide > 0:
            eye_height = int(eye_height * (1 + self.wide * 0.3))
        eye_rect = pygame.Rect(
            self.center_x - self.size,
            self.center_y - eye_height // 2,
            self.size * 2,
            eye_height
        )
        pygame.draw.ellipse(screen, color, eye_rect, 3)
        pupil_x = self.center_x + int(self.pupil_offset_x * self.size * 0.4)
        pupil_y = self.center_y + int(self.pupil_offset_y * eye_height * 0.3)
        max_offset_x = self.size - self.pupil_size - 10
        max_offset_y = eye_height // 2 - self.pupil_size // 2 - 5
        pupil_x = max(self.center_x - max_offset_x, min(self.center_x + max_offset_x, pupil_x))
        pupil_y = max(self.center_y - max_offset_y, min(self.center_y + max_offset_y, pupil_y))
        pygame.draw.circle(screen, color, (pupil_x, pupil_y), self.pupil_size)
        highlight_x = pupil_x - self.pupil_size // 3
        highlight_y = pupil_y - self.pupil_size // 3
        pygame.draw.circle(screen, WHITE, (highlight_x, highlight_y), self.pupil_size // 4)


class JarvisFace:
    def __init__(self, width=800, height=480):
        self.width = width
        self.height = height
        eye_y = height // 2 - 20
        eye_spacing = width // 4
        self.left_eye = Eye(width // 2 - eye_spacing // 2, eye_y, size=70)
        self.right_eye = Eye(width // 2 + eye_spacing // 2, eye_y, size=70)
        self.emotion = "neutral"
        self.color = CYAN
        self.is_talking = False
        self.talk_frame = 0
        self.last_blink = time.time()
        self.next_blink = random.uniform(2, 5)
        self.blink_duration = 0.15
        self.blink_start = 0
        self.idle_time = 0
        self.next_look_change = random.uniform(1, 3)
        self.personality = "normal"
        self.status_text = ""
        self.status_time = 0

    def set_emotion(self, emotion):
        self.emotion = emotion
        emotions = {
            "neutral": {"squint": 0, "wide": 0, "color": CYAN},
            "happy": {"squint": 0.3, "wide": 0, "color": GREEN},
            "sad": {"squint": 0.5, "wide": 0, "color": BLUE},
            "angry": {"squint": 0.6, "wide": 0, "color": RED},
            "surprised": {"squint": 0, "wide": 1, "color": YELLOW},
            "thinking": {"squint": 0.2, "wide": 0, "color": PURPLE},
            "excited": {"squint": 0, "wide": 0.5, "color": ORANGE},
            "love": {"squint": 0.3, "wide": 0, "color": PINK},
            "sleepy": {"squint": 0.7, "wide": 0, "color": BLUE},
        }
        if emotion in emotions:
            e = emotions[emotion]
            self.left_eye.squint = e["squint"]
            self.right_eye.squint = e["squint"]
            self.left_eye.wide = e["wide"]
            self.right_eye.wide = e["wide"]
            self.color = e["color"]

    def set_personality(self, personality):
        self.personality = personality
        colors = {
            "normal": CYAN, "professional": WHITE, "sassy": PINK,
            "funny": YELLOW, "pirate": ORANGE, "yoda": GREEN, "surfer": BLUE,
        }
        self.color = colors.get(personality, CYAN)

    def look_at(self, direction):
        directions = {
            "left": (-1, 0), "right": (1, 0), "up": (0, -1),
            "down": (0, 1), "center": (0, 0), "forward": (0, 0),
        }
        if direction in directions:
            x, y = directions[direction]
            self.left_eye.target_offset_x = x
            self.left_eye.target_offset_y = y
            self.right_eye.target_offset_x = x
            self.right_eye.target_offset_y = y

    def blink(self):
        self.blink_start = time.time()
        self.left_eye.is_blinking = True
        self.right_eye.is_blinking = True

    def start_talking(self):
        self.is_talking = True
        self.talk_frame = 0

    def stop_talking(self):
        self.is_talking = False

    def show_status(self, text):
        self.status_text = text
        self.status_time = time.time()

    def update(self, dt):
        current_time = time.time()
        if self.left_eye.is_blinking:
            blink_progress = (current_time - self.blink_start) / self.blink_duration
            if blink_progress < 0.5:
                self.left_eye.blink_state = 1.0 - (blink_progress * 2)
                self.right_eye.blink_state = 1.0 - (blink_progress * 2)
            elif blink_progress < 1.0:
                self.left_eye.blink_state = (blink_progress - 0.5) * 2
                self.right_eye.blink_state = (blink_progress - 0.5) * 2
            else:
                self.left_eye.blink_state = 1.0
                self.right_eye.blink_state = 1.0
                self.left_eye.is_blinking = False
                self.right_eye.is_blinking = False
                self.last_blink = current_time
                self.next_blink = random.uniform(2, 6)
        if not self.left_eye.is_blinking and current_time - self.last_blink > self.next_blink:
            self.blink()
        self.idle_time += dt
        if self.idle_time > self.next_look_change:
            self.idle_time = 0
            self.next_look_change = random.uniform(2, 5)
            self.left_eye.target_offset_x = random.uniform(-0.5, 0.5)
            self.left_eye.target_offset_y = random.uniform(-0.3, 0.3)
            self.right_eye.target_offset_x = self.left_eye.target_offset_x
            self.right_eye.target_offset_y = self.left_eye.target_offset_y
        self.left_eye.update(dt)
        self.right_eye.update(dt)
        if self.status_text and current_time - self.status_time > 3:
            self.status_text = ""

    def draw(self, screen):
        screen.fill(BLACK)
        self.left_eye.draw(screen, self.color)
        self.right_eye.draw(screen, self.color)
        if self.is_talking:
            self.talk_frame += 1
            mouth_open = abs(math.sin(self.talk_frame * 0.3)) * 15
            mouth_y = self.height // 2 + 80
            pygame.draw.ellipse(screen, self.color,
                              (self.width // 2 - 40, mouth_y - mouth_open // 2,
                               80, max(5, mouth_open)), 2)
        if self.status_text:
            font = pygame.font.Font(None, 36)
            text = font.render(self.status_text, True, self.color)
            text_rect = text.get_rect(center=(self.width // 2, self.height - 40))
            screen.blit(text, text_rect)
        font = pygame.font.Font(None, 24)
        personality_text = font.render(f"Mode: {self.personality.upper()}", True, self.color)
        screen.blit(personality_text, (10, 10))


def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    pygame.display.set_caption("JARVIS Face")
    clock = pygame.time.Clock()
    face = JarvisFace(800, 480)
    
    running = True
    last_time = time.time()
    
    while running:
        current_time = time.time()
        dt = current_time - last_time
        last_time = current_time
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_h:
                    face.set_emotion("happy")
                elif event.key == pygame.K_s:
                    face.set_emotion("sad")
                elif event.key == pygame.K_a:
                    face.set_emotion("angry")
                elif event.key == pygame.K_n:
                    face.set_emotion("neutral")
                elif event.key == pygame.K_e:
                    face.set_emotion("excited")
                elif event.key == pygame.K_SPACE:
                    face.blink()
                elif event.key == pygame.K_LEFT:
                    face.look_at("left")
                elif event.key == pygame.K_RIGHT:
                    face.look_at("right")
                elif event.key == pygame.K_UP:
                    face.look_at("up")
                elif event.key == pygame.K_DOWN:
                    face.look_at("down")
                elif event.key == pygame.K_c:
                    face.look_at("center")
                elif event.key == pygame.K_t:
                    face.start_talking()
                elif event.key == pygame.K_y:
                    face.stop_talking()
                elif event.key == pygame.K_1:
                    face.set_personality("normal")
                elif event.key == pygame.K_2:
                    face.set_personality("pirate")
                elif event.key == pygame.K_3:
                    face.set_personality("sassy")
                elif event.key == pygame.K_4:
                    face.set_personality("yoda")
        
        face.update(dt)
        face.draw(screen)
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()


if __name__ == '__main__':
    main()
