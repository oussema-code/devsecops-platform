"""Render docs/demo/demo.gif (and an MP4 for social media) from recorded run output.

Every line is taken from real runs: scripts/finish-platform.sh (2026-11-07) and
scripts/canary-drill.py (2026-11-06). Long lines are shortened and pauses compressed.
Requires Pillow and, for the MP4, ffmpeg.
"""
import pathlib
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(__file__).resolve().parent
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
BOLD = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 17)
COLS, ROWS, PAD = 92, 13, 22
CW = int(FONT.getlength("M"))
LH = 25
W, H = COLS * CW + 2 * PAD, ROWS * LH + 2 * PAD + 34
BG, FG = (13, 17, 23), (201, 209, 217)
COLOR = {"pass": (63, 185, 80), "fail": (248, 81, 73), "head": (88, 166, 255),
         "cmd": (240, 246, 252), "dim": (125, 133, 144), "warn": (210, 153, 34)}


def style(line):
    if line.startswith("$"):
        return "cmd", BOLD
    if line.startswith("#"):
        return "dim", FONT
    if line.startswith("====="):
        return "head", BOLD
    if "FAILED" in line or "DENIED" in line or " Failed" in line:
        return "fail", FONT
    if line.startswith(("PASS", "RESULT", "Drill complete")) or " OK" in line or "Successful" in line \
            or line.endswith("-> created"):
        return "pass", BOLD if line.startswith("RESULT") else FONT
    if line.startswith("Drill"):
        return "warn", BOLD
    return None, FONT


SCENES = [
    [("# DevSecOps & GitOps platform: recorded results (condensed replay)", 0.2),
     ("# github.com/oussema-code/devsecops-platform", 1.6)],
    [("$ bash scripts/finish-platform.sh        # Kyverno in Enforce mode", 0.9),
     ("===== Admission proof (server-side dry runs; nothing is created) =====", 0.7),
     ("signed  ghcr.io/oussema-code/boutique-checkoutservice@sha256:73aeb301...  -> created", 0.8),
     ("upstream  .../microservices-demo/checkoutservice:v0.10.7@sha256:f0e72ff7...  -> DENIED", 0.6),
     ("nginx:1.29                                                  -> DENIED", 0.5),
     ("ghcr.io/oussema-code/boutique-checkoutservice:latest        -> DENIED", 0.6),
     ("PASS: signed image admitted; upstream, unpinned and tag-only images rejected", 2.6)],
    [("$ python3 scripts/canary-drill.py        # production, 2 replicas", 0.9),
     ("PASS: production Rollout Healthy before the drill", 0.5),
     ("Drill 1: candidate that cannot reach the product catalog", 0.9),
     ("PASS: broken candidate aborted by checkout analysis", 0.6),
     ("PASS: AnalysisRun frontend-59d7cd498d-2-1 Failed", 0.5),
     ("PASS: aborted canary scaled down", 0.4),
     ("PASS: storefront checkout still served by stable Pods after abort", 0.9),
     ("Drill 2: harmless candidate (Pod template annotation only)", 0.9),
     ("PASS: good candidate promoted after passing analysis", 0.5),
     ("PASS: AnalysisRun frontend-659c75b9df-4-1 Successful; new stable 659c75b9df", 0.6),
     ("PASS: Git-defined template restored through a second passing canary", 0.4),
     ("Drill complete. Production frontend matches Git again.", 2.6)],
    [("===== Worker-loss drill =====", 0.6),
     ("production Redis is on devsecops-platform-worker; stopping devsecops-platform-worker2", 0.9),
     ("t+10s checkout FAILED", 0.7),
     ("t+46s checkout OK", 0.35),
     ("t+67s checkout OK", 0.3),
     ("t+83s checkout OK", 0.3),
     ("t+98s checkout OK", 0.3),
     ("# ... 23 more checkouts, all OK ...", 0.5),
     ("t+472s checkout OK", 0.5),
     ("worker-loss summary: 28 ok / 1 failed checkouts over 8 minutes", 2.6)],
    [("===== Final verification =====", 0.5),
     ("PASS: all 3 platform nodes Ready", 0.35),
     ("PASS: boutique-staging deployments, Service endpoints, and checkout", 0.35),
     ("PASS: boutique-production deployments, Service endpoints, and checkout", 0.35),
     ("PASS: policy denied redis-cart", 0.3),
     ("PASS: policy denied frontend.boutique-production.svc.cluster.local", 0.4),
     ("boutique-production   Synced   Healthy", 0.3),
     ("boutique-staging      Synced   Healthy", 0.5),
     ("RESULT: ALL PASSED", 3.5)],
]


def frame(lines):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 30], fill=(22, 27, 34))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([14 + i * 20, 9, 26 + i * 20, 21], fill=c)
    d.text((W // 2 - 120, 6), "devsecops-platform", font=FONT, fill=COLOR["dim"])
    for row, text in enumerate(lines[-ROWS:]):
        key, font = style(text)
        d.text((PAD, 34 + PAD + row * LH), text[:COLS], font=font, fill=COLOR.get(key, FG))
    return img


def build():
    frames, durations = [], []
    for scene in SCENES:
        shown = []
        for text, pause in scene:
            shown.append(text)
            frames.append(frame(shown))
            durations.append(int(pause * 1000))
    gif = OUT / "demo.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True)
    print("wrote", gif)
    if "--mp4" in sys.argv:
        tmp = OUT / "_frames"
        tmp.mkdir(exist_ok=True)
        concat = []
        for i, (img, ms) in enumerate(zip(frames, durations)):
            path = tmp / f"{i:03d}.png"
            img.save(path)
            concat += [f"file '{path}'", f"duration {ms / 1000}"]
        concat.append(f"file '{tmp / f'{len(frames) - 1:03d}.png'}'")
        (tmp / "list.txt").write_text("\n".join(concat) + "\n")
        mp4 = OUT / "demo.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", str(tmp / "list.txt"), "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
                        "-movflags", "+faststart", str(mp4)], check=True)
        for p in tmp.iterdir():
            p.unlink()
        tmp.rmdir()
        print("wrote", mp4)


if __name__ == "__main__":
    build()
