import os
from pal_demod import demodulate

def main():
    resources = [
        "1.bin", "2.bin", "3.bin", "4.bin", "5.bin", "6.bin", "7.bin", "8.bin", "9.bin", "10.bin"
    ]

    for file_name in resources:
        cwd = os.getcwd()
        input_filename = os.path.join(cwd, "resources", "demod", file_name)
        demodulate(input_filename)

if __name__ == "__main__":
    main()