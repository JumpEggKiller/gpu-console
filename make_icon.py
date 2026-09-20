"""Generate a simple GPU-console-style icon (dark bg + cyan card + green bar)."""
from PIL import Image, ImageDraw

def make(size):
    im = Image.new("RGBA", (size, size), (10, 14, 20, 255))
    d = ImageDraw.Draw(im)
    s = size / 100
    # panel
    d.rounded_rectangle([8*s, 10*s, 92*s, 90*s], radius=10*s, fill=(13, 20, 32), outline=(28, 39, 57))
    # header bar
    d.rounded_rectangle([14*s, 16*s, 86*s, 26*s], radius=4*s, fill=(16, 26, 42))
    d.rectangle([18*s, 19*s, 40*s, 23*s], fill=(56, 207, 230))
    # util bar
    d.rounded_rectangle([14*s, 34*s, 86*s, 44*s], radius=4*s, fill=(20, 29, 44))
    d.rounded_rectangle([14*s, 34*s, int(14*s + 72*s*0.62), 44*s], radius=4*s, fill=(242, 177, 61))
    # vram bar
    d.rounded_rectangle([14*s, 52*s, 86*s, 62*s], radius=4*s, fill=(20, 29, 44))
    d.rounded_rectangle([14*s, 52*s, int(14*s + 72*s*0.83), 62*s], radius=4*s, fill=(56, 207, 230))
    # history bars
    hs = [30, 55, 40, 70, 90, 60, 80, 45, 65, 35, 50, 75]
    bw = 5.5*s
    x = 14*s
    for v in hs:
        h = 8*s + v/100 * 20*s
        c = (239, 91, 91) if v >= 85 else ((242, 177, 61) if v >= 50 else (63, 208, 127))
        d.rectangle([x, 88*s - h, x + bw, 88*s], fill=c)
        x += bw + 0.5*s
    return im

sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = [make(s) for s in sizes]
imgs[-1].save(
    r"C:\Users\micasa\gpu-console\gpu_console.ico",
    format="ICO",
    sizes=[(i.width, i.height) for i in imgs],
    append_images=imgs[:-1],
)
print("icon written")