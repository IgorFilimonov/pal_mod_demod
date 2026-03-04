import math
import cv2
import struct
import sys

F_CHROMA = 4433618.75
SAMPLE_RATE = 12000000.0
T_SAMPLE = 1000000.0 / SAMPLE_RATE
LINE_TIME = 64.0
BLANKING = 12.0
NUM_LINES = 625
X_RESOLUTION = 768
PIXEL_TIME = (LINE_TIME - BLANKING) / X_RESOLUTION
FRONT_PORCH = 1.5
HSYNC = 4.7
PRE_BURST = 0.9
BURST = 2.25
BACK_PORCH = BLANKING - FRONT_PORCH - HSYNC
EQ_SHORT = 2.35
EQ_LONG = 27.3

SYNC_LVL = 0.0
BLANK_LVL = 0.285
WHITE_LVL = 1.0
BLACK_LVL = 0.339
BURST_AMP = 0.1425
COLOR_GAIN = 1.0

sample_buffer = []
timer = 0.0
estimated_time = 0.0
burst_phase = -math.pi * 3.0 / 4.0
carrier_sign = -1.0
frame_num = 0

def write_samples(time, sample):
    global estimated_time, timer, sample_buffer
    estimated_time += time
    while timer < estimated_time:
        sample_buffer += [sample]
        timer += T_SAMPLE

def write_long_sync():
    write_samples(EQ_LONG, SYNC_LVL)
    write_samples((LINE_TIME / 2) - EQ_LONG, BLANK_LVL)

def write_short_sync():
    write_samples(EQ_SHORT, SYNC_LVL)
    write_samples((LINE_TIME / 2) - EQ_SHORT, BLANK_LVL)

def write_line_sync(burst):
    global estimated_time, timer, sample_buffer
    write_samples(FRONT_PORCH, BLANK_LVL)
    write_samples(HSYNC, SYNC_LVL)
    write_samples(PRE_BURST, BLANK_LVL)

    estimated_time += BURST
    while timer < estimated_time:
        if burst:
            wt = (burst_phase + math.pi * 2 * (timer / 1000000.0) * F_CHROMA) % (math.pi * 2)
            sample_buffer += [BLANK_LVL + (BURST_AMP * math.sin(wt))]
        else:
            sample_buffer += [BLANK_LVL]
        timer += T_SAMPLE

    write_samples(BLANKING - FRONT_PORCH - HSYNC - PRE_BURST - BURST, BLANK_LVL)

def write_blank_line(sync):
    global estimated_time, timer, sample_buffer
    write_line_sync(sync)
    write_samples(LINE_TIME - BLANKING, BLACK_LVL)

def get_pixel_y(line, fields_line):
    if line < 311:
        pixel_y = 1 + fields_line * 2
    else:
        pixel_y = (fields_line - 287) * 2
    return pixel_y

def write_frame(image):
    global estimated_time, timer, sample_buffer, carrier_sign, burst_phase, frame_num
    fields_line = 0
    for line in range(1, NUM_LINES + 1):
        if 1 <= line <= 2 or 314 <= line <= 315:
            write_long_sync()
            write_long_sync()
        elif line == 3:
            write_long_sync()
            write_short_sync()
        elif line == 313:
            write_short_sync()
            write_long_sync()
        elif 4 <= line <= 5 or 311 <= line <= 312 or 316 <= line <= 317 or 624 <= line <= 625:
            write_short_sync()
            write_short_sync()
        elif line == 6 or line == 318:
            write_blank_line(False)
        elif 7 <= line <= 23 or 319 <= line <= 335:
            write_blank_line(True)
        elif line == 623:
            write_line_sync(True)
            write_samples(LINE_TIME / 2 - BLANKING, BLACK_LVL)
            write_short_sync()
        else:
            write_line_sync(True)
            pixel_x = 0
            pixel_timer = timer
            estimated_time += LINE_TIME - BLANKING
            y = 0.0
            u = 0.0
            v = 0.0
            while timer < estimated_time:
                if timer >= pixel_timer:
                    pixel_y = get_pixel_y(line, fields_line)
                    b, g, r = image[pixel_y, pixel_x]
                    r /= 255.0
                    g /= 255.0
                    b /= 255.0
                    y = 0.299 * r + 0.587 * g + 0.114 * b
                    u = 0.493 * (b - y)
                    v = 0.877 * (r - y)
                    pixel_x += 1
                    pixel_timer += PIXEL_TIME

                wt = (math.pi * 2 * (timer / 1000000.0) * F_CHROMA) % (math.pi * 2)
                e = y + (u *  math.sin(wt) * COLOR_GAIN + v * carrier_sign * math.cos(wt) * COLOR_GAIN)
                e = BLACK_LVL + e * (WHITE_LVL-BLACK_LVL)
                sample_buffer += [e]
                timer += T_SAMPLE
            fields_line += 1

        burst_phase *= -1.0
        carrier_sign *= -1.0
        timer = LINE_TIME * NUM_LINES * frame_num + T_SAMPLE * len(sample_buffer)

    frame_num += 1
    timer = LINE_TIME * NUM_LINES * frame_num + T_SAMPLE * len(sample_buffer)
    estimated_time = timer

def write_output_file(output_filename):
    global sample_buffer
    packed_samples = struct.pack('f' * len(sample_buffer), *sample_buffer)
    with open(output_filename, "wb") as f:
        f.write(packed_samples)

def parse_args():
    if 3 > len(sys.argv) or len(sys.argv) > 5:
        print("Usage: <input_filename> <output_filename> [optional: sample_rate, frames_amount]")
        exit()

    global SAMPLE_RATE
    video_path = ""
    output_filename = ""
    frames_amount = 0
    if len(sys.argv) >= 3:
        video_path = sys.argv[1]
        output_filename = sys.argv[2]
        if len(sys.argv) >= 4:
            SAMPLE_RATE = int(sys.argv[3])
            if len(sys.argv) >= 5:
                frames_amount = int(sys.argv[4])
    return video_path, output_filename, frames_amount

def main():
    video_path, output_filename, frames_amount = parse_args()

    video_capture = cv2.VideoCapture(video_path)
    if not video_capture.isOpened():
        print(f"Error: Could not open the video")
        return

    is_there_next_frame = True
    frames_count = 0
    while is_there_next_frame:
        is_there_next_frame, frame = video_capture.read()
        if is_there_next_frame:
            write_frame(frame)
            frames_count += 1
            if frames_count == frames_amount:
                break
    video_capture.release()

    write_output_file(output_filename)

if __name__ == "__main__":
    main()