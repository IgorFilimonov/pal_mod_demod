import os
from pal_mod import modulate

def main():
    for i in range(1, 11):
        cwd = os.getcwd()
        video_path = os.path.join(cwd, "resources", "mod", str(i) + ".mp4")
        output_filename = os.path.join(cwd, "resources", "demod", str(i) + ".bin")
        modulate(video_path, output_filename, 10)

if __name__ == "__main__":
    main()