"""Measure the ticket 09 token pairs with the kit contrast.py ratio. Prototype only."""
import sys
sys.path.insert(0, r"C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/scripts")
from contrast import ratio

def hx(rgb): return "#%02x%02x%02x" % tuple(round(c) for c in rgb)
def rgb(h): h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))
def over(fg, a, bg):
    f, b = rgb(fg) if isinstance(fg,str) else fg, rgb(bg)
    return hx(tuple(f[i]*a + b[i]*(1-a) for i in range(3)))

T = {
 "dark": dict(bg="#0b0c0f", sidebar="#0e0f13", surface="#131519", s2="#181a1f", s3="#1f2127", hover="#1c1e24",
   text="#ededf0", text2="#a3a7b1", text3="#9298a5", inverse="#0b0c0f", brand="#8e97ff", brand_strong="#a9b0ff", brand_ink="#0b0c1a",
   ok="#5ccf9a", warn="#eeb85c", bad="#f07f7f", info="#6fb6ee", control="#697185",
   soft=dict(ok=("#5ccf9a",.12), warn=("#eeb85c",.12), bad=("#f07f7f",.12), info=("#6fb6ee",.12), brand=("#8e97ff",.12))),
 "light": dict(bg="#f6f6f4", sidebar="#efefec", surface="#ffffff", s2="#f9f9f8", s3="#f0f0ee", hover="#f1f1ef",
   text="#16171b", text2="#5c5f68", text3="#656a75", inverse="#ffffff", brand="#4f58e0", brand_strong="#3d45c9", brand_ink="#ffffff",
   ok="#157347", warn="#8a540d", bad="#bd3030", info="#216a9f", control="#838994",
   soft=dict(ok=("#1f9d64",.10), warn=("#b87412",.10), bad=("#cf3c3c",.08), info=("#2a7fc0",.10), brand=("#4f58e0",.09))),
}
CAND = {  # proposed new values
 "dark": dict(bad_strong="#f49a9a", bad_ink="#0b0c0f"),
 "light": dict(bad_strong="#9f2626", bad_ink="#ffffff"),
}
rows = []
def m(theme, name, fg, bg, need):
    r = ratio(fg, bg); rows.append((theme, name, fg, bg, r, need, "pass" if r >= need else "FAIL"))
for th, t in T.items():
    tint = {k: over(c, a, t["surface"]) for k, (c, a) in t["soft"].items()}
    print(th, "tints over surface:", tint)
    for k in ("ok", "warn", "bad", "info"):
        m(th, f"{k} on {k}-tint", t[k], tint[k], 4.5)
        m(th, f"text on {k}-tint", t["text"], tint[k], 4.5)
    m(th, "brand on brand-tint", t["brand"], tint["brand"], 4.5)
    m(th, "brand-strong on brand-tint", t["brand_strong"], tint["brand"], 4.5)
    m(th, "text on brand-tint (active row)", t["text"], tint["brand"], 4.5)
    m(th, "text-2 on brand-tint (active row)", t["text2"], tint["brand"], 4.5)
    m(th, "text-2 on surface-3 (selected row)", t["text2"], t["s3"], 4.5)
    m(th, "text-3 on brand-tint (active row)", t["text3"], tint["brand"], 4.5)
    m(th, "ring brand on brand-tint (focus)", t["brand"], tint["brand"], 3.0)
    m(th, "ring brand on surface-3 (focus)", t["brand"], t["s3"], 3.0)
    m(th, "info on info-tint (proposal B)", t["info"], tint["info"], 4.5)
    c = CAND[th]
    m(th, "bad-ink on bad (destructive fill)", c["bad_ink"], t["bad"], 4.5)
    m(th, "bad-ink on bad-strong (destructive hover)", c["bad_ink"], c["bad_strong"], 4.5)
    m(th, "old #fff on bad (current ui-button-destructive)", "#ffffff", t["bad"], 4.5)
    m(th, "bad-strong vs surface (fill edge)", c["bad_strong"], t["surface"], 3.0)
    m(th, "bad outline text on surface", t["bad"], t["surface"], 4.5)
    m(th, "bad on bad-tint hover (destructive outline hover)", t["bad"], tint["bad"], 4.5)
    for k in ("bad", "warn", "ok", "info", "control"):
        m(th, f"{k} border vs surface (wireframe, 1.4.11)", t[k], t["surface"], 3.0)
    m(th, "control-border vs brand-tint (control on active row)", t["control"], tint["brand"], 3.0)
    m(th, "control-border vs surface-3", t["control"], t["s3"], 3.0)
for r in rows: print("%-6s %-52s %s on %s  %.2f:1 (need %.1f) %s" % r)
print("FAILS:", sum(1 for r in rows if r[-1] == "FAIL"))
