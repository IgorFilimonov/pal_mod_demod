import struct
import numpy as np
from OpenGL.GL import *
import glfw

INVERT_VIDEO = True
LEVEL_BLACK = 0.3
SAMPLE_RATE = 9000000
LINES_NUMBER = 625
FPS = 25
HSYNC = True
VSYNC = True
LEVEL_SYNC = 0.2
BLACK_LINES_NUMBER = 49
FIRST_VISIBLE_LINE = 23
SYNC_LINES_NUMBER = 3

def read_bin(path):
    with open(path, 'rb') as f:
        content = f.read()
        samples = struct.iter_unpack('f', content)
    return samples

class ATVScreen:
    def __init__(self, samples_handler):
        if not glfw.init():
            raise Exception(":(")
        self.samples_handler = samples_handler
        self.width, self.height = self.samples_handler.get_width_and_height()
        self.window = glfw.create_window(self.width, self.height, "ATV Screen", None, None)
        glfw.set_window_pos(self.window, 100, 100)
        glfw.make_context_current(self.window)
        self.texture = glGenTextures(1)

    def start(self):
        while not glfw.window_should_close(self.window):
            glfw.poll_events()

            image_data = self.samples_handler.get_frame()

            glViewport(0, 0, self.width, self.height)

            glBindTexture(GL_TEXTURE_2D, self.texture)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.width, self.height,0, GL_LUMINANCE, GL_UNSIGNED_BYTE, image_data)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE)
            glEnable(GL_TEXTURE_2D)

            glClearColor(0.0, 0.0, 0.0, 1.0)
            glClear(GL_COLOR_BUFFER_BIT)

            glBegin(GL_TRIANGLES)

            p = 1.0
            glTexCoord2f(0.0, 0.0)
            glVertex2f(-p, -p)
            glTexCoord2f(1.0, 0.0)
            glVertex2f(p, -p)
            glTexCoord2f(1.0, 1.0)
            glVertex2f(p, p)

            glTexCoord2f(0.0, 0.0)
            glVertex2f(-p, -p)
            glTexCoord2f(1.0, 1.0)
            glVertex2f(p, p)
            glTexCoord2f(0.0, 1.0)
            glVertex2f(-p, p)

            glEnd()

            glfw.swap_buffers(self.window)

        glfw.terminate()

class ATVSamplesHandler:
    def __init__(self, samples_iterator):
        self.samples_iterator = samples_iterator

    sample_range_correction = 255.0 / (1.0 - LEVEL_BLACK)
    line_duration = 1.0 / (LINES_NUMBER * FPS)

    samples_per_line_signals = int(line_duration * SAMPLE_RATE * 12.0  / 64.0) # "a", Line-blanking interval
    samples_per_hsync = int(line_duration * SAMPLE_RATE * 10.5  / 64.0) # "b", Interval between time datum and back edge of line-blanking pulse
    samples_per_htop = int(line_duration * SAMPLE_RATE *  4.7  / 64.0) # "d", Duration of synchronizing pulse

    hl = 32.0 # half of the line
    p  = 2.35 # "p", Duration of equalizing pulse
    q  = 27.3 # "q", Duration of field-synchronizing pulse

    # In the first half of the first line field index is detected
    field_detect_start_pos = int(line_duration * SAMPLE_RATE * p / 64.0)
    field_detect_end_pos = int(line_duration * SAMPLE_RATE * q / 64.0)
    # In the second half of the first line vertical synchronization is detected
    vsync_detect_start_pos = int(line_duration * SAMPLE_RATE * (p + hl) / 64.0)
    vsync_detect_end_pos = int(line_duration * SAMPLE_RATE * (q + hl) / 64.0)

    field_detect_percent = 0.75 # It is better not to detect field index than detect it wrong
    detect_total_len = line_duration * SAMPLE_RATE * (q - p) / 64.0 # same for field index and vSync detection
    field_detect_threshold1 = int(detect_total_len * field_detect_percent)
    field_detect_threshold2 = int(detect_total_len * (1.0 - field_detect_percent))

    vsync_detect_percent = 0.5
    vsync_detect_threshold = int(detect_total_len * vsync_detect_percent)

    samples_per_line = int(SAMPLE_RATE / (LINES_NUMBER * FPS))
    samples_per_line_frac = SAMPLE_RATE / (LINES_NUMBER * FPS) - samples_per_line
    height = LINES_NUMBER - BLACK_LINES_NUMBER
    width = samples_per_line - samples_per_line_signals + 4
    image_data = np.zeros((height, width), dtype = np.uint8)
    #line_shift_data = np.zeros((height, 1))
    row_index = 0

    def get_width_and_height(self):
        return self.width, self.height

    sample_offset = 0 # assumed (averaged) sample offset from the start of horizontal sync pulse
    sample_offset_frac = 0.0 # sample offset, fractional part
    sample_offset_detected = 0 # detected sample offset from the start of horizontal sync pulse
    line_index = 0
    field_index = 0

    prev_sample = 0.0
    hsync_shift = 0.0
    hsync_error_count = 0
    field_detect_sample_count = 0
    vsync_detect_sample_count = 0

    def get_frame(self):
        next_sample_exists = True
        while next_sample_exists:
            try:
                sample = next(self.samples_iterator)[0]
            except StopIteration:
                next_sample_exists = False
            else:
                normalized_sample = sample
                if INVERT_VIDEO:
                    normalized_sample = 1.0 - sample
                if sample < 0.0:
                    normalized_sample = 0.0
                elif sample > 1.0:
                    normalized_sample = 1.0

                sample_video = int((sample - LEVEL_BLACK) * self.sample_range_correction)
                if sample_video < 0:
                    sample_video = 0
                elif sample_video > 255:
                    sample_video = 255

                if self.process_sample(normalized_sample, sample_video):
                    return self.image_data

        return self.image_data

    def set_sample_value(self, column, value):
        if self.width - 2 > column >= -2:
            self.image_data[self.height - self.row_index - 1, column + 2] = value

    def process_sample(self, sample, sample_video): # if true is returned, full frame is ready
        self.set_sample_value(self.sample_offset - self.samples_per_hsync, sample_video)

        if HSYNC:
            if self.prev_sample >= LEVEL_SYNC > sample and self.sample_offset_detected > self.samples_per_line - self.samples_per_htop:
                sample_offset_detected_frac = (sample - LEVEL_SYNC) / (self.prev_sample - sample)
                hsync_shift = -self.sample_offset - self.sample_offset_frac - sample_offset_detected_frac
                if hsync_shift > self.samples_per_line / 2:
                    hsync_shift -= self.samples_per_line
                elif hsync_shift < -self.samples_per_line / 2:
                    hsync_shift += self.samples_per_line

                if abs(hsync_shift) > self.samples_per_htop:
                    self.hsync_error_count += 1
                    if self.hsync_error_count >= 4:
                        # Fast sync: shift is too large, needs to be fixed ASAP
                        self.hsync_shift = hsync_shift
                        self.hsync_error_count = 0
                else:
                    # Slow sync: slight adjustment is needed
                    self.hsync_shift = hsync_shift * 0.2
                    self.hsync_error_count = 0

                self.sample_offset_detected = 0
            else:
                self.sample_offset_detected += 1

        self.sample_offset += 1

        if VSYNC:
            if self.field_detect_start_pos < self.sample_offset < self.field_detect_end_pos and sample < LEVEL_SYNC:
                self.field_detect_sample_count += 1
            if self.vsync_detect_start_pos < self.sample_offset < self.vsync_detect_end_pos and sample < LEVEL_SYNC:
                self.vsync_detect_sample_count += 1

        if self.sample_offset >= self.samples_per_line:
            sample_offset_float = self.hsync_shift + self.sample_offset_frac - self.samples_per_line_frac
            self.sample_offset = int(sample_offset_float)
            self.sample_offset_frac = sample_offset_float - self.sample_offset
            self.hsync_shift = 0.0

            self.line_index += 1
            return self.end_of_a_line()
        else:
            return False

    def end_of_a_line(self):
        flag = False
        if self.line_index == SYNC_LINES_NUMBER + 3 and self.field_index == 0:
            flag = True

        if self.vsync_detect_sample_count > self.vsync_detect_threshold and (self.line_index < 3 or self.line_index > SYNC_LINES_NUMBER + 1) and VSYNC:
            if self.field_detect_sample_count > self.field_detect_threshold1:
                self.field_index = 0
            elif self.field_detect_sample_count < self.field_detect_threshold2:
                self.field_index = 1
            self.line_index = 2

        self.field_detect_sample_count = 0
        self.vsync_detect_sample_count = 0

        if self.line_index > LINES_NUMBER / 2 + self.field_index:
            self.line_index = 1
            self.field_index = 1 - self.field_index

        row_index = (self.line_index - FIRST_VISIBLE_LINE) * 2 - self.field_index
        if self.is_row_valid(row_index):
            self.row_index = row_index

        return flag

    def is_row_valid(self, row_index):
        if self.height > row_index >= 0:
            return True
        else:
            return False


def main():
    #samples_iterator = read_bin('C:/Users/Igor/Documents/pal/palpalpal14132243197342482536.bin')
    samples_iterator = read_bin('C:/Users/Igor/Documents/pal/habr.bin')
    atv_samples_handler = ATVSamplesHandler(samples_iterator)
    atv_screen = ATVScreen(atv_samples_handler)
    atv_screen.start()

if __name__ == "__main__":
    main()