import struct

SAMPLE_SIZE = 32 # 8 or 16 or 32

def read_bin(path):
    if SAMPLE_SIZE == 8:
        struct_format = 'b'
        divisor = 127
    elif SAMPLE_SIZE == 16:
        struct_format = 'h'
        divisor = 32767
    else:
        struct_format = 'f'
        divisor = 1
    with open(path, 'rb') as f:
        content = f.read()
        samples_iterator = struct.iter_unpack(struct_format, content)

    float_samples = []
    next_sample_exists = True
    while next_sample_exists:
        try:
            sample = next(samples_iterator)[0]
        except StopIteration:
            next_sample_exists = False
        else:
            float_samples.append(sample / divisor)
    return iter(float_samples)