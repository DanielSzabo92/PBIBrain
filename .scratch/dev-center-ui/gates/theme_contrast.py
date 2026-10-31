# Contrast of the theme.css text, status and brand tokens on each surface token, dark and light (ticket 01).
# Run: python theme_contrast.py
import re, sys
sys.path.insert(0, r"C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/scripts")
from contrast import ratio as _r, parse_hex
ratio=lambda a,b:_r("#%02x%02x%02x"%a,"#%02x%02x%02x"%b)
css = open(r"C:/Users/Daniel/Desktop/PBIBrain/frontend/src/theme.css", encoding="utf8").read()
def block(sel):
    i = css.index(sel); j = css.index("{", i); k = css.index("}", j)
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", css[j:k]))
dark = block(":root {"); light = {**dark, **block(':root[data-theme="light"]')}
def rgb(v):
    v=v.strip()
    if v.startswith("#"): return parse_hex(v), 1.0
    m = re.match(r"rgb\((\d+) (\d+) (\d+) / ([\d.]+)\)", v); return tuple(map(int,m.groups()[:3])), float(m.group(4))
def comp(fg, a, bg): return tuple(round(f*a+b*(1-a)) for f,b in zip(fg,bg))
hx=lambda t:"#%02x%02x%02x"%t
SURF=["bg","bg-sidebar","surface","surface-2","surface-3","surface-hover"]
TEXT=[("text",4.5),("text-2",4.5),("text-3",4.5),("brand",4.5),("brand-strong",4.5),("ok",4.5),("warn",4.5),("bad",4.5),("info",4.5)]
fails=0
for name,t in (("dark",dark),("light",light)):
    print(f"== {name}")
    for fg,mn in TEXT:
        row=[]
        for s in SURF:
            r=ratio(rgb(t[fg])[0], rgb(t[s])[0]); ok=r>=mn; fails+= not ok
            row.append(f"{s}={r:.2f}{'' if ok else ' FAIL'}")
        print(f"  {fg:13} " + "  ".join(row))
    # status text on its soft tint over surface and bg
    for st in ("ok","warn","bad","info","brand"):
        for s in ("surface","bg"):
            c,a=rgb(t[st+"-soft"]); bgc=comp(c,a,rgb(t[s])[0]); r=ratio(rgb(t[st])[0],bgc); fails+= r<4.5
            print(f"  {st} on {st}-soft over {s} ({hx(bgc)}): {r:.2f}{'' if r>=4.5 else ' FAIL'}")
    for fg,bg in (("brand-ink","brand"),("brand-ink","brand-strong"),("text-inverse","text")):
        r=ratio(rgb(t[fg])[0],rgb(t[bg])[0]); fails+=r<4.5; print(f"  {fg} on {bg}: {r:.2f}{'' if r>=4.5 else ' FAIL'}")
    for fg,mn in (("control-border",3.0),("line-strong",3.0),("line",3.0),("line-focus",3.0),("brand",3.0)):
        for s in ("bg","surface","surface-2"):
            r=ratio(rgb(t[fg])[0],rgb(t[s])[0]); print(f"  non-text {fg} on {s}: {r:.2f} {'pass 3:1' if r>=mn else 'below 3:1'}")
print("TEXT FAILS:",fails)
