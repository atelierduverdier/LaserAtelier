# -*- coding: utf-8 -*-
"""Un blanc ne se traverse pas à la vitesse de gravure.

Christophe, 06/08/2026, après avoir envoyé le G-code d'une pièce faite sur
son Falcon 2 : « règle les problèmes de trajet à vide dans NOS
générateurs ».

CE QUE SON FICHIER LIGHTBURN MONTRE. Deux pièces posées à 101 mm l'une de
l'autre, remplies d'un seul balayage : **4 359 déplacements à vide de
128 mm de médiane**, faits en `G1` à l'avance de gravure faisceau éteint.
55,9 % du parcours, près de 4 heures sur 7. Rien dans le fichier ne le
signale -- G-code valide, image correcte.

L'ATELIER N'A PAS CE DÉFAUT, ET C'EST MESURÉ : 1,51 % sur les 70 fichiers
réellement gravés. `TRANSIT_BLANC_MINI_MM` (v2.45.0) fait traverser en
rapide toute plage blanche qui l'atteint, et le mécanisme a été étendu
deux fois depuis -- la spirale en v2.52.0, le fuseau en v2.56.0.

MAIS RIEN NE LE GELAIT. Un mécanisme étendu deux fois et jamais testé est
exactement la forme du défaut des micro-traits, qui a été livré DEUX FOIS
parce que la correction du premier générateur n'avait pas été portée en
propriété sur toute la famille.
"""
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()
core = h.core
core._apply_settings_config()

MAT = u"Hêtre"
Z = core.Z_WORK_MM
SEUIL = core.TRANSIT_BLANC_MINI_MM


def traversees_lentes(gcode):
    """Déplacements faisceau ÉTEINT, à l'avance de gravure, dépassant le
    seuil. La réponse attendue est une liste vide.

    On juge sur l'AVANCE RÉELLEMENT COMMANDÉE, pas sur le type de bloc :
    l'atelier traverse en `G1` à l'avance rapide (mouvement continu, pas de
    vidage de file) et non en `G0`, donc compter les `G0` ne dirait rien."""
    x = y = None
    s = 0.0
    f = 0.0
    lents = []
    for ligne in gcode.split("\n"):
        code = ligne.split("(")[0].split(";")[0]
        if not code.strip():
            continue
        ms = re.search(r"(?<![A-Za-z])S(\d+\.?\d*)", code)
        if ms:
            s = float(ms.group(1))
        mq = re.search(r"M67\s+E\d+\s+Q(\d+\.?\d*)", code)
        if mq:
            s = float(mq.group(1))
        mf = re.search(r"(?<![A-Za-z])F(\d+\.?\d*)", code)
        if mf:
            f = float(mf.group(1))
        mg = re.match(r"\s*G0*([013])\b", code)
        if not mg:
            continue
        nx = ny = None
        for lettre, val in re.findall(r"([XY])(-?\d+\.?\d*)", code):
            if lettre == "X":
                nx = float(val)
            else:
                ny = float(val)
        px = x if nx is None else nx
        py = y if ny is None else ny
        if x is not None and y is not None and int(mg.group(1)) != 0:
            d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
            if s == 0 and f < core.RAPID_FEED_MM_MIN * 0.99 and d >= SEUIL:
                lents.append(d)
        x, y = px, py
    return lents


# UNE IMAGE AVEC UN VRAI VIDE AU MILIEU. Une image pleine ne prouverait
# rien : elle n'a aucun blanc à traverser, donc n'importe quel code passe.
# 60 mm de vide, douze fois le seuil, exactement la forme du fichier de
# Christophe -- deux zones gravées séparées par du rien.
LARGEUR, HAUTEUR, VIDE = 120, 90, 60
image = [[0.85 if (x < 30 or x > 90) else 0.0 for x in range(LARGEUR)]
         for _ in range(HAUTEUR)]

FAMILLE = {
    "diffusion en lignes":
        lambda: core.generate_gcode_photo_dither_lines(
            image, 1.0, Z, 600.0, 800.0, quiet=True),
    "lignes calibrées":
        lambda: core.generate_gcode_photo_lines(
            image, 1.0, Z, 800.0, 0.30, MAT, quiet=True),
    "similigravure":
        lambda: core.generate_gcode_photo_am(
            image, 1.0, Z, 600.0, 800.0, quiet=True),
    "diffusion (points)":
        lambda: core.generate_gcode_halftone(
            image, 1.0, Z, 500.0, 0.010, 0.060, quiet=True),
}

print("=" * 62)
print("§1  La pièce d'essai peut-elle seulement voir le défaut ?")
print("=" * 62)

print("   image %d x %d au pas 1,0 mm, vide de %d mm au milieu (seuil %g mm)"
      % (LARGEUR, HAUTEUR, VIDE, SEUIL))
assert VIDE > SEUIL * 4, (
    "le vide (%g mm) n'est pas franchement au-delà du seuil (%g) : la "
    "pièce d'essai ne prouverait rien" % (VIDE, SEUIL))

# ET IL FAUT QUE ÇA GRAVE DES DEUX CÔTÉS, sans quoi il n'y a pas de
# traversée du tout et le test passe pour la mauvaise raison.
gauche = sum(1 for l in image for x in range(30) if l[x] > 0)
droite = sum(1 for l in image for x in range(91, LARGEUR) if l[x] > 0)
print("   pixels à graver : %d à gauche, %d à droite" % (gauche, droite))
assert gauche > 100 and droite > 100, "l'image ne grave pas des deux côtés"

print()
print("=" * 62)
print("§2  Aucun tramage ne traverse un blanc à la vitesse de gravure")
print("=" * 62)

produits = {}
for nom, fabrique in FAMILLE.items():
    g = fabrique()
    assert g, "« %s » n'a rien produit sur cette image" % nom
    produits[nom] = g
    lents = traversees_lentes(g)
    print("   %-22s %4d traversée(s) lente(s)%s"
          % (nom, len(lents),
             "  (la pire : %.0f mm)" % max(lents) if lents else ""))
    assert not lents, (
        "« %s » traverse %d fois un blanc à l'avance de gravure, la pire de "
        "%.0f mm : c'est le défaut qui a coûté 4 h au fichier LightBurn"
        % (nom, len(lents), max(lents)))

print()
print("=" * 62)
print("§3  Le contrôle SAIT échouer")
print("=" * 62)

# On désarme le mécanisme par le seul chemin qui le désarme vraiment :
# l'avance rapide passée SOUS l'avance de gravure, où `transit > feed`
# devient faux. Si les traversées lentes n'apparaissent pas alors, c'est
# que §2 ne mesure rien.
_rapide = core.RAPID_FEED_MM_MIN
try:
    core.RAPID_FEED_MM_MIN = 100.0
    core.__dict__["RAPID_FEED_MM_MIN"] = 100.0
    g = core.generate_gcode_photo_dither_lines(
        image, 1.0, Z, 600.0, 800.0, quiet=True)
    # Le repère de comparaison doit être l'avance de gravure, pas la valeur
    # sabotée : on cherche des mouvements éteints longs, quelle que soit F.
    x = y = None
    s = 0.0
    longs = []
    for ligne in g.split("\n"):
        code = ligne.split("(")[0]
        ms = re.search(r"(?<![A-Za-z])S(\d+\.?\d*)", code)
        if ms:
            s = float(ms.group(1))
        mg = re.match(r"\s*G0*1\b", code)
        nx = ny = None
        for lettre, val in re.findall(r"([XY])(-?\d+\.?\d*)", code):
            if lettre == "X":
                nx = float(val)
            else:
                ny = float(val)
        px = x if nx is None else nx
        py = y if ny is None else ny
        if mg and x is not None and y is not None and s == 0:
            d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
            if d >= SEUIL:
                longs.append(d)
        x, y = px, py
finally:
    core.RAPID_FEED_MM_MIN = _rapide
    core.__dict__["RAPID_FEED_MM_MIN"] = _rapide

print("   avance rapide ramenée sous l'avance de gravure : %d traversée(s) "
      "longue(s)%s" % (len(longs),
                       ", la pire %.0f mm" % max(longs) if longs else ""))
assert longs, (
    "le mécanisme désarmé ne produit AUCUNE traversée longue : §2 ne "
    "mesure rien, et sa réussite ne prouve rien")

print()
print("=" * 62)
print("§4  Les fichiers RÉELLEMENT gravés : on compte, on n'assène pas")
print("=" * 62)

# Sur des fichiers produits par des versions ANCIENNES, une divergence est
# une information sur l'historique, pas un défaut du code d'aujourd'hui --
# la même règle que pour les mesures de Christophe. `gravure_photo4.ngc`
# porte 4,6 m de traversées lentes et l'en-tête dit v1.96.4 ; le mécanisme
# est arrivé en v2.45.0. On imprime, on n'assène que sur ce qu'on génère.
import glob                                                   # noqa: E402
import os                                                     # noqa: E402

fautifs = []
for chemin in sorted(glob.glob("/mnt/srv-partage/Gcode/*.ngc")):
    txt = open(chemin, encoding="utf-8", errors="replace").read()
    lents = traversees_lentes(txt)
    if lents:
        version = "?"
        m = re.search(r"LaserAtelier v([\d.]+)", txt[:200])
        if m:
            version = m.group(1)
        fautifs.append((sum(lents), version, os.path.basename(chemin)))
fautifs.sort(reverse=True)
if fautifs:
    for total, version, nom in fautifs[:5]:
        print("   %7.0f mm  v%-9s %s" % (total, version, nom[:34]))
else:
    print("   aucun fichier gravé ne porte de traversée lente")
print("   (mécanisme introduit en v2.45.0 -- un fichier antérieur en porte")
print("    légitimement ; c'est de l'histoire, pas un défaut vivant)")

print()
print("TOUT EST VERT")
