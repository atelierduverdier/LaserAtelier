# -*- coding: utf-8 -*-
"""La MIRE DE MESURE gravée sur les planches de calibration.

Idée de Christophe (31/07/2026) : graver la graduation SUR la planche
plutôt que d'y poser une réglette. Une réglette posée est 0,5 à 1 mm
au-dessus de la surface, donc vue sous un autre angle que le trait qu'on
mesure ; une graduation gravée partage son plan ET le repère machine.

Validé sur bois le jour même : la mire a permis de mesurer un trait à
0,50 mm par photo, valeur ensuite CONFIRMÉE au pied à coulisse alors que
la table annonçait 0,30. C'est elle qui a fait tomber le fait que la
table des largeurs au foyer était périmée.
"""
import re

from harness import preparer

h = preparer()
core = h.core


def bbox(g):
    xs, ys = [], []
    for l in g.split("\n"):
        if not l.startswith(("G0 X", "G1 X")):
            continue
        for t in l.split():
            if t.startswith("X"):
                xs.append(float(t[1:]))
            elif t.startswith("Y"):
                ys.append(float(t[1:]))
    return min(xs), min(ys), max(xs), max(ys)


# --- 1. La mire est là, et ses cotes sont RONDES ----------------------
# Rondes parce qu'elles sont annoncées en en-tête et servent de référence
# métrologique : une base de 80,00 mm connue à 0,05 mm près donne 0,06 %
# d'erreur d'échelle.
for nom, gen in (("Planche 1", core.generate_gcode_planche_focus),
                 ("Planche 2", core.generate_gcode_planche_defocus)):
    g = gen(quiet=True)
    assert g, nom
    m = re.search(r"rectangle de ([\d.]+) x ([\d.]+) mm ENTRE CENTRES", g)
    assert m, (nom, [l for l in g.split("\n") if l.startswith("(")][:6])
    L, H = float(m.group(1)), float(m.group(2))
    assert L % 10 == 0 and H % 10 == 0, (nom, L, H)
    assert "reglette au mm" in g, nom
    print("1. {} : mire annoncee, rectangle {:.0f} x {:.0f} mm (rond) OK".format(
        nom, L, H))

# --- 2. Sans mire, le G-code est celui d'AVANT -----------------------
for nom, gen in (("Planche 1", core.generate_gcode_planche_focus),
                 ("Planche 2", core.generate_gcode_planche_defocus)):
    g0 = gen(mire=False, quiet=True)
    assert "Mire de mesure" not in g0, nom
    assert bbox(g0)[2] < bbox(gen(quiet=True))[2], (
        "avec la mire, la planche doit s'elargir", nom)
print("2. mire=False : aucune trace de mire, planche plus petite OK")

# --- 3. Les 4 repères existent vraiment, aux bons écarts -------------
g = core.generate_gcode_planche_focus(quiet=True)
seg, garde, x, y = [], False, None, None
for l in g.split("\n"):
    if l.startswith("(-- "):
        garde = "repere" in l
        continue
    m = re.match(r"G0 X([-\d.]+) Y([-\d.]+)", l)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
        continue
    m = re.match(r"G1 X([-\d.]+) Y([-\d.]+)", l)
    if m and garde and x is not None:
        seg.append(((x, y), (float(m.group(1)), float(m.group(2)))))
        x, y = float(m.group(1)), float(m.group(2))
assert len(seg) == 8, ("4 croix x 2 bras attendus", len(seg))
centres = sorted({(round((a[0] + b[0]) / 2, 2), round((a[1] + b[1]) / 2, 2))
                  for a, b in seg})
assert len(centres) == 4, centres
xs = sorted({c[0] for c in centres})
ys = sorted({c[1] for c in centres})
mm = re.search(r"rectangle de ([\d.]+) x ([\d.]+) mm", g)
assert abs((xs[-1] - xs[0]) - float(mm.group(1))) < 1e-6, (xs, mm.group(1))
assert abs((ys[-1] - ys[0]) - float(mm.group(2))) < 1e-6, (ys, mm.group(2))
print("3. 4 croix, ecarts {:.0f} x {:.0f} mm CONFORMES a l'en-tete OK".format(
    xs[-1] - xs[0], ys[-1] - ys[0]))

# --- 4. La mire ne recouvre JAMAIS le contenu -------------------------
# Au premier essai, le trait le plus large avait été gravé en travers des
# chiffres de la réglette : inmesurable, et invisible autrement qu'à
# l'aperçu. La garde est donc calculée, pas écrite à la main.
b, lbl, infos = core.mire_de_mesure(10.0, 10.0, 50.0, 40.0)
assert infos is not None and infos["garde"] >= 0.5, infos
# ... et si on ne laisse pas la place, la mire REFUSE au lieu de chevaucher.
b2, _l2, i2 = core.mire_de_mesure(10.0, 10.0, 50.0, 40.0, marge=0.0, garde=0.0)
_b3, _l3, i3 = core.mire_de_mesure(0.0, 0.0, 5.0, 5.0, marge=0.0, garde=-20.0)
assert i3 is None, "une mire qui chevauche le contenu doit etre refusee"
print("4. garde de {:.1f} mm sous le contenu ; une mire qui chevaucherait "
      "est refusee OK".format(infos["garde"]))

# --- 5. Gravée LENTEMENT, et réglable par laser -----------------------
# La réglette, ce sont des dizaines de petits traits séparés par des
# rapides, donc autant d'accélérations : à F1200 le support en PLA de
# l'atelier vibrait et les repères sortaient ONDULÉS -- ce qui ruine
# exactement ce qu'on leur demande, un centre net.
assert core.MIRE_FEED <= 400, core.MIRE_FEED
assert ("mire_power", "MIRE_POWER") in [(k, g_) for k, g_, _c, _v in core._USER_SETTINGS]
assert "mire_power" in core.PER_LASER_KEYS and "mire_feed" in core.PER_LASER_KEYS
puiss = {int(m.group(1)) for l in g.split("\n") if not l.startswith("(")
         for m in [re.search(r"\bS(\d+)", l) or re.search(r"M67 E0 Q(\d+)", l)] if m}
assert int(core.MIRE_POWER) in puiss, (core.MIRE_POWER, sorted(puiss))
print("5. mire a S{:.0f} F{:.0f}, reglable par laser, presente dans le G-code OK"
      .format(core.MIRE_POWER, core.MIRE_FEED))

print("\nTOUS LES TESTS mire_planches PASSENT")


# --- 6. Compaction : rien ne doit se toucher -------------------------
# Les planches ont été resserrées le 31/07/2026 (« je n'ai pas besoin de
# 3 cm de traits pour avoir la largeur, ça économisera du bois et la
# photo sera plus facile ») : trait 20 -> 12 mm, entre-rangs 6 -> 4,
# étiquettes 3 -> 2,5, et l'entre-colonnes CALCULÉ sur la largeur réelle
# des étiquettes au lieu de 12 mm forfaitaires. Resserrer une mise en
# page sans vérifier les distances, c'est exactement comme ça qu'un trait
# s'est retrouvé gravé en travers des chiffres de la réglette.
import math


def _segments(g):
    par_commentaire, cur, x, y = {}, None, None, None
    for l in g.split("\n"):
        if l.startswith("(-- "):
            cur = l
            continue
        m = re.match(r"G0 X([-\d.]+) Y([-\d.]+)", l)
        if m:
            x, y = float(m.group(1)), float(m.group(2))
            continue
        m = re.match(r"G1 X([-\d.]+) Y([-\d.]+)", l)
        if m and x is not None:
            par_commentaire.setdefault(cur, []).append(
                ((x, y), (float(m.group(1)), float(m.group(2)))))
            x, y = float(m.group(1)), float(m.group(2))
    return par_commentaire


def _dist(p, a, b):
    (ax, ay), (bx, by), (px, py) = a, b, p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


for nom, gen, cle in (("Planche 1", core.generate_gcode_planche_focus, "Planche 1 : S"),
                      ("Planche 2", core.generate_gcode_planche_defocus, "Planche 2 : d")):
    g = gen(quiet=True)
    seg = _segments(g)
    traits = [s for c, ss in seg.items() if c and cle in c for s in ss]
    etiq = [s for c, ss in seg.items() if c and "etiquette" in c for s in ss]
    assert traits and etiq, (nom, len(traits), len(etiq))
    mini = min(_dist(p, a, b) for a, b in traits for c_, d_ in etiq for p in (c_, d_))
    assert mini > 0.6, (nom, "une etiquette touche un trait", mini)
    print("6. {} : {} traits, distance minimale trait/etiquette {:.2f} mm OK".format(
        nom, len(traits), mini))

# ... et la compaction a bien eu lieu (une regression la reperdrait en
# silence : les planches marcheraient, elles seraient juste plus grandes).
import inspect
sig = inspect.signature(core.generate_gcode_planche_focus)
assert sig.parameters["trait_len"].default <= 12.0, sig.parameters["trait_len"].default
assert sig.parameters["row_gap"].default <= 4.0, sig.parameters["row_gap"].default
w, h = 0.0, 0.0
xs = [float(t[1:]) for l in core.generate_gcode_planche_focus(quiet=True).split("\n")
      if l.startswith(("G0 X", "G1 X")) for t in l.split() if t.startswith("X")]
assert max(xs) - min(xs) < 170, ("planche 1 trop large", max(xs) - min(xs))
print("7. Planche 1 : {:.0f} mm de large (etait ~195 avant compaction) OK".format(
    max(xs) - min(xs)))
