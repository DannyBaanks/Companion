from pathlib import Path
import cv2

src = Path(r"C:\Users\progr\.codex\generated_images\01a0834e-cd73-7773-b112-6e0fd76789a6\exec-1dbdd8b0-327c-4d11-afd0-0b853df65801.png")
out = Path("packs/tabby-shinji-cat")
names = ["idle", "thinking", "working", "success", "error", "waiting"]
sheet = cv2.imread(str(src), cv2.IMREAD_COLOR)
h, w = sheet.shape[:2]
for i, name in enumerate(names):
    x, y = (i % 3) * (w // 3), (i // 3) * (h // 2)
    cell = sheet[y:y + h // 2, x:x + w // 3]
    m = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    # Conservative foreground seed: central subject, then clean connected background.
    gc = (cv2.GC_BGD * (m < 35)).astype("uint8")
    gc[:] = cv2.GC_PR_BGD
    gc[24:-24, 24:-24] = cv2.GC_PR_FGD
    gc[80:-80, 80:-80] = cv2.GC_FGD
    bgd, fgd = __import__("numpy").zeros((1, 65), "float64"), __import__("numpy").zeros((1, 65), "float64")
    cv2.grabCut(cell, gc, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
    alpha = ((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)).astype("uint8") * 255
    rgba = cv2.cvtColor(cell, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = alpha
    cv2.imwrite(str(out / f"{name}.png"), rgba)
