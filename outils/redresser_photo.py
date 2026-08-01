#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Redresse la photo d'une planche gravée, à partir de sa MIRE.

    python3 outils/redresser_photo.py photo.jpg --gcode planche1_foyer.ngc
    python3 outils/redresser_photo.py photo.jpg --base 140x60 --pxmm 60

Les cotes de la mire sont LUES DANS L'EN-TETE du .ngc quand on le donne :
recopier « 140x60 » à la main est un piège, puisque la mise en page d'une
planche peut changer (elles ont été resserrées le 31/07/2026) et qu'une
cote périmée donnerait une échelle fausse EN SILENCE.

Pourquoi cet outil existe
-------------------------
Une photo tenue à la main n'est jamais perpendiculaire à la planche, et
FreeCAD met une image à l'échelle de façon UNIFORME : il ne sait pas
corriger cette perspective. Toutes les mesures prises sur une photo de
biais sont donc biaisées, et rien ne le signale.

Les quatre repères en croix de la mire donnent quatre correspondances,
donc l'homographie complète. On redresse une fois pour toutes, et on
sort une image où 1 mm vaut EXACTEMENT `--pxmm` pixels partout. Il ne
reste plus qu'à l'importer dans FreeCAD à la taille annoncée et à
mesurer à l'outil Ligne du Draft : c'est l'utilisateur qui décide où
s'arrête la brûlure, ce qu'aucun seuil automatique ne sait faire à sa
place.

Volontairement HORS du workbench : cv2 n'existe pas dans le python
embarqué de FreeCAD, et ce script n'a besoin ni de FreeCAD ni de Part.
Il tourne avec le python du système.

Le repérage des croix
---------------------
Par défaut on CLIQUE les quatre croix (haut-gauche, haut-droite,
bas-droite, bas-gauche). Un clic vaut quelques pixels de précision, mais
chaque point est ensuite raffiné automatiquement dans une petite fenêtre
autour du clic -- le raffinement ne peut pas partir ailleurs puisqu'il
est borné. Sur une base de 140 mm, une croix placée à 0,05 mm près donne
0,04 % d'erreur d'échelle.

Ce choix est délibéré : la détection automatique des croix est ce qui a
échoué le plus souvent (repères pollués par la réglette, étiquettes
prises pour des traits). Le pas fragile est confié à l'oeil, le calcul
exact à la machine.
"""
import argparse
import os
import sys

try:
    import cv2
    import numpy as np
except ImportError:
    sys.exit("Il faut OpenCV et NumPy : sudo pacman -S python-opencv python-numpy")

COINS = ("haut-gauche", "haut-droite", "bas-droite", "bas-gauche")


def ordonner(pts):
    """Remet 4 points dans l'ordre horaire en partant du haut-gauche.

    L'ORDRE DES CLICS NE COMPTE DONC PAS. C'est une correction, pas un
    confort : passés dans un ordre croisé, les mêmes quatre points
    produisaient un redressement en « noeud papillon » -- une image
    détruite, accompagnée de chiffres parfaitement plausibles (0,48 %
    d'écart de diagonales) et d'aucun avertissement. Un outil de mesure
    n'a pas le droit de se tromper en silence.

    Tri par angle autour du barycentre (donc cyclique et sans ambiguïté),
    puis rotation pour démarrer au point le plus en haut à gauche.
    """
    import math
    cx = sum(p[0] for p in pts) / 4.0
    cy = sum(p[1] for p in pts) / 4.0
    tri = sorted(pts, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    k = min(range(4), key=lambda i: tri[i][0] + tri[i][1])
    return tri[k:] + tri[:k]


def convexe(pts):
    """Les 4 points forment-ils un quadrilatère convexe non croisé ?"""
    signes = []
    for i in range(4):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % 4]
        cx_, cy_ = pts[(i + 2) % 4]
        signes.append((bx - ax) * (cy_ - ay) - (by - ay) * (cx_ - ax))
    return all(s > 0 for s in signes) or all(s < 0 for s in signes)


def raffiner(gris, x, y, rayon=40):
    """Centre sous-pixel de la croix autour d'un clic approximatif.

    Barycentre pondéré par la noirceur dans une fenêtre bornée : le
    raffinement ne peut pas fuir vers un autre motif puisqu'il ne voit
    que `rayon` pixels autour du point cliqué."""
    h, w = gris.shape
    x0, x1 = max(0, int(x) - rayon), min(w, int(x) + rayon)
    y0, y1 = max(0, int(y) - rayon), min(h, int(y) + rayon)
    z = gris[y0:y1, x0:x1].astype(np.float32)
    if z.size == 0:
        return float(x), float(y)
    fond = np.percentile(z, 80)
    p = np.clip(fond - z, 0, None)
    if p.sum() <= 0:
        return float(x), float(y)
    ys, xs = np.nonzero(p)
    poids = p[ys, xs]
    return (float((xs * poids).sum() / poids.sum()) + x0,
            float((ys * poids).sum() / poids.sum()) + y0)


def cliquer(img):
    """Fait cliquer les 4 croix, dans l'ordre, sur une vue réduite."""
    h, w = img.shape[:2]
    k = min(1.0, 1400.0 / max(h, w))
    vue = cv2.resize(img, (int(w * k), int(h * k)))
    pts, fini = [], [False]

    def au_clic(event, x, y, flags, _p):
        if event == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append((x / k, y / k))
            cv2.circle(vue, (x, y), 8, (0, 0, 255), 2)
            cv2.imshow("reperes", vue)
            if len(pts) == 4:
                fini[0] = True

    cv2.namedWindow("reperes", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("reperes", au_clic)
    for i, nom in enumerate(COINS):
        print("  clique la croix {} ({}/4)".format(nom, i + 1))
        while len(pts) <= i and not fini[0]:
            cv2.imshow("reperes", vue)
            if cv2.waitKey(20) == 27:
                cv2.destroyAllWindows()
                sys.exit("annulé")
    cv2.waitKey(300)
    cv2.destroyAllWindows()
    return pts


def controle(img, pts, chemin):
    """Image de contrôle : où les croix ont été retenues. À REGARDER
    avant de croire le résultat -- c'est la seule vérification qui
    couvre une erreur de clic ou de raffinement."""
    v = img.copy()
    for (x, y), nom in zip(pts, COINS):
        cv2.circle(v, (int(x), int(y)), 30, (0, 0, 255), 4)
        cv2.line(v, (int(x) - 60, int(y)), (int(x) + 60, int(y)), (0, 0, 255), 2)
        cv2.line(v, (int(x), int(y) - 60), (int(x), int(y) + 60), (0, 0, 255), 2)
        cv2.putText(v, nom, (int(x) + 35, int(y) - 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 255), 3)
    h, w = v.shape[:2]
    k = min(1.0, 1600.0 / max(h, w))
    cv2.imwrite(chemin, cv2.resize(v, (int(w * k), int(h * k))))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("--gcode", default=None,
                    help="fichier .ngc de la planche : les cotes de la mire sont "
                         "LUES DANS SON EN-TETE. A preferer a --base, qui se "
                         "perime des qu'on change la mise en page d'une planche")
    ap.add_argument("--base", default=None,
                    help="cotes du rectangle ENTRE CENTRES des croix, ex 140x60. "
                         "A n'utiliser que sans le .ngc sous la main")
    ap.add_argument("--pxmm", type=float, default=40.0,
                    help="pixels par mm de l'image redressee (defaut 40, "
                         "soit 0,025 mm/pixel)")
    ap.add_argument("--marge", type=float, default=8.0,
                    help="mm conserves autour du rectangle des croix (defaut 8)")
    ap.add_argument("--sortie", default=None)
    ap.add_argument("--json", default=None,
                    help="ecrit un petit JSON decrivant le resultat (fichier, "
                         "taille en mm, px/mm) -- c'est le contrat que lit le "
                         "panneau FreeCAD, plus sur que de relire stdout")
    ap.add_argument("--reperes", default=None,
                    help="4 points x,y separes par des espaces, au lieu des clics "
                         "(pour rejouer sans interface)")
    a = ap.parse_args()

    if a.gcode:
        import re
        entete = open(a.gcode, errors="ignore").read(4000)
        m = re.search(r"rectangle de ([\d.]+) x ([\d.]+) mm ENTRE CENTRES", entete)
        if not m:
            sys.exit("pas de ligne « rectangle de ... ENTRE CENTRES » dans {} : "
                     "cette planche n'a pas de mire, ou elle est anterieure a la "
                     "v2.14".format(a.gcode))
        L, H = float(m.group(1)), float(m.group(2))
        print("cotes de la mire lues dans {} : {:.2f} x {:.2f} mm".format(
            os.path.basename(a.gcode), L, H))
    elif a.base:
        L, H = (float(v) for v in a.base.lower().split("x"))
    else:
        sys.exit("donne --gcode planche.ngc (recommande) ou --base 140x60")
    img = cv2.imread(a.photo)
    if img is None:
        sys.exit("image illisible : " + a.photo)
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print("photo {} x {} px".format(img.shape[1], img.shape[0]))

    if a.reperes:
        bruts = [tuple(float(v) for v in p.split(",")) for p in a.reperes.split()]
        if len(bruts) != 4:
            sys.exit("--reperes attend exactement 4 points")
    else:
        print("Clique les 4 croix dans l'ordre : " + ", ".join(COINS))
        bruts = cliquer(img)

    pts = ordonner([raffiner(gris, x, y) for x, y in bruts])
    if not convexe(pts):
        sys.exit("les 4 points ne forment pas un quadrilatere convexe : deux "
                 "reperes sont sans doute confondus ou mal places")
    print("reperes retenus (remis dans l'ordre automatiquement) :")
    for (rx, ry), nom in zip(pts, COINS):
        d = min(((rx - bx) ** 2 + (ry - by) ** 2) ** 0.5 for bx, by in bruts)
        print("  {:12s} ({:7.1f},{:7.1f})   raffinement {:.1f} px".format(
            nom, rx, ry, d))

    import math
    base = os.path.splitext(a.sortie or a.photo)[0]
    controle(img, pts, base + "_reperes.jpg")
    print("controle des reperes ecrit : " + base + "_reperes.jpg")

    # --- diagonales : le test de perspective, AVANT redressement ------
    d1 = math.dist(pts[0], pts[2])
    d2 = math.dist(pts[1], pts[3])
    ecart = 200.0 * abs(d1 - d2) / (d1 + d2)
    print("diagonales {:.1f} et {:.1f} px -> ecart {:.2f} %".format(d1, d2, ecart))
    if ecart > 3.0:
        print("  ATTENTION : plus de 3 % d'ecart, la photo est franchement de")
        print("  biais. Le redressement corrige la geometrie, mais un angle")
        print("  rasant etale aussi le flou : refais la photo plus de face.")

    # --- redressement -------------------------------------------------
    # Le rapport des cotes du quadrilatere doit rester dans le meme ordre
    # de grandeur que celui attendu : au-dela, un repere a ete place sur
    # autre chose (un chiffre de reglette, un noeud du bois...).
    larg_px = (math.dist(pts[0], pts[1]) + math.dist(pts[3], pts[2])) / 2
    haut_px = (math.dist(pts[0], pts[3]) + math.dist(pts[1], pts[2])) / 2
    attendu, obtenu = L / H, larg_px / max(haut_px, 1e-6)
    print("rapport des cotes : {:.3f} mesure contre {:.3f} attendu".format(
        obtenu, attendu))
    if not (0.5 * attendu < obtenu < 2.0 * attendu):
        sys.exit("le quadrilatere ne ressemble pas a un rectangle {:.0f}x{:.0f} : "
                 "verifie --base et les reperes cliques".format(L, H))

    m = a.marge
    src = np.array(pts, dtype=np.float32)
    dst = np.array([[m, m], [m + L, m], [m + L, m + H], [m, m + H]],
                   dtype=np.float32) * a.pxmm
    W = int(round((L + 2 * m) * a.pxmm))
    Ht = int(round((H + 2 * m) * a.pxmm))
    M = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(img, M, (W, Ht), flags=cv2.INTER_CUBIC)

    sortie = a.sortie or (base + "_redresse.png")
    cv2.imwrite(sortie, out)
    if a.json:
        import json
        with open(a.json, "w") as fh:
            json.dump({"fichier": os.path.abspath(sortie),
                       "largeur_mm": W / a.pxmm, "hauteur_mm": Ht / a.pxmm,
                       "pxmm": a.pxmm, "base_mm": [L, H],
                       "ecart_diagonales_pct": ecart,
                       "controle": os.path.abspath(base + "_reperes.jpg")}, fh)

    print()
    print("=== {} ===".format(sortie))
    print("  {} x {} px, a EXACTEMENT {:.0f} px/mm ({:.4f} mm/px)".format(
        W, Ht, a.pxmm, 1.0 / a.pxmm))
    print()
    print("  Dans FreeCAD : importe cette image et donne-lui la taille")
    print("     largeur = {:.3f} mm     hauteur = {:.3f} mm".format(
        W / a.pxmm, Ht / a.pxmm))
    print("  L'echelle est alors exacte partout : plus de calibration a")
    print("  faire, l'outil Ligne du Draft donne directement des mm.")
    print()
    print("  Verification a faire toi-meme : mesure les deux diagonales")
    print("  entre croix opposees, elles doivent valoir {:.3f} mm.".format(
        math.hypot(L, H)))


if __name__ == "__main__":
    main()
