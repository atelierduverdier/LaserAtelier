#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convertit un projet LightBurn (.lbrn / .lbrn2) en SVG.

    python3 outils/lbrn2_vers_svg.py dessin.lbrn2            # -> dessin.svg
    python3 outils/lbrn2_vers_svg.py dessin.lbrn2 sortie.svg
    python3 outils/lbrn2_vers_svg.py dessin.lbrn2 --vignette v.png

POURQUOI PAS UN MODE DE PLUS. Christophe, 06/08/2026 : « on m'a envoyé un
fichier LightBurn au lieu d'un SVG, sais-tu l'importer ou en retirer le
SVG ? ». L'atelier sait déjà lire un SVG -- `svg_import.py`, avec son
aplatissement à 0,02 mm et sa capture des couleurs. Ajouter un vingt-et-
unième mode pour un format d'échange serait empiler là où il suffit de
traduire : ce script rend un SVG, et l'import existant fait le reste.

LE FORMAT, décodé sur son fichier (267 chemins) :

  <Shape Type="Path"> porte trois enfants --
    <XForm>  a b c d e f   : la matrice affine, comme `matrix()` en SVG ;
    <VertList> `V<x> <y>` puis, facultatifs, `c0x`/`c0y` (point de
       contrôle SORTANT) et `c1x`/`c1y` (ENTRANT) ;
    <PrimList> `L<i> <j>` un segment, `B<i> <j>` une cubique de i à j.

  UN POINT DE CONTRÔLE ABSENT S'ÉCRIT `c0x1` SANS `c0y`. C'est le piège
  du format : `1` n'est pas une coordonnée, c'est un marqueur. On ne
  retient donc un point de contrôle que si SES DEUX composantes sont là
  -- une abscisse valant vraiment 1 est toujours suivie de son ordonnée.

  Les <Shape Type="Group"> imbriquent d'autres formes et composent leur
  XForm avec celle de leurs enfants.

LightBurn travaille en Y VERS LE HAUT, le SVG en Y vers le bas : tout est
donc enveloppé dans un miroir vertical calculé sur l'emprise réelle.
"""
import argparse
import base64
import os
import re
import sys
import xml.etree.ElementTree as ET

# `V x y` puis les points de contrôle éventuels, dans l'ordre où LightBurn
# les écrit. Tout est collé, sans séparateur : d'où les lookahead.
_NOMBRE = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
_SOMMET = re.compile(
    r"V(?P<x>{n})\s+(?P<y>{n})"
    r"(?:c0x(?P<c0x>{n}))?(?:c0y(?P<c0y>{n}))?"
    r"(?:c1x(?P<c1x>{n}))?(?:c1y(?P<c1y>{n}))?".format(n=_NOMBRE))
_PRIMITIVE = re.compile(r"(?P<t>[LB])(?P<a>\d+)\s+(?P<b>\d+)")

IDENTITE = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _composer(m, n):
    """m ∘ n : on applique n, puis m (convention SVG `matrix`)."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def _appliquer(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def _xform(forme):
    txt = (forme.findtext("XForm") or "").strip()
    if not txt:
        return IDENTITE
    bouts = [float(v) for v in txt.split()]
    return tuple(bouts[:6]) if len(bouts) >= 6 else IDENTITE


def _sommets(texte):
    """[(x, y, sortant|None, entrant|None), ...] d'un <VertList>."""
    out = []
    for m in _SOMMET.finditer(texte or ""):
        g = m.groupdict()
        # Les DEUX composantes, ou rien : cf. le piège `c0x1` ci-dessus.
        sortant = ((float(g["c0x"]), float(g["c0y"]))
                   if g["c0x"] is not None and g["c0y"] is not None else None)
        entrant = ((float(g["c1x"]), float(g["c1y"]))
                   if g["c1x"] is not None and g["c1y"] is not None else None)
        out.append((float(g["x"]), float(g["y"]), sortant, entrant))
    return out


def _chemin(forme, matrice):
    """Le `d` d'un <Shape Type="Path">, déjà transformé."""
    sommets = _sommets(forme.findtext("VertList"))
    if not sommets:
        return None
    brut = forme.findtext("PrimList")
    prims = [(m.group("t"), int(m.group("a")), int(m.group("b")))
             for m in _PRIMITIVE.finditer(brut or "")]
    if not prims:
        # PAS DE PrimList : LE CONTOUR EST IMPLICITE. Sur le fichier de
        # Christophe, 110 chemins sur 267 sont dans ce cas -- les ignorer
        # en perdait 41 %, et le dessin sortait troué. Les sommets se
        # suivent alors dans l'ordre et la boucle se referme ; chaque
        # segment est une cubique si un point de contrôle existe de part
        # ou d'autre, un simple trait sinon.
        n = len(sommets)
        if n < 2:
            return None
        for i in range(n):
            j = (i + 1) % n
            courbe = sommets[i][2] is not None or sommets[j][3] is not None
            prims.append(("B" if courbe else "L", i, j))

    def pt(i):
        return _appliquer(matrice, sommets[i][0], sommets[i][1])

    morceaux = []
    precedent = None
    for genre, i, j in prims:
        if i >= len(sommets) or j >= len(sommets):
            continue
        if precedent != i:
            x, y = pt(i)
            morceaux.append("M{:.4f} {:.4f}".format(x, y))
        x, y = pt(j)
        if genre == "L":
            morceaux.append("L{:.4f} {:.4f}".format(x, y))
        else:
            sortant = sommets[i][2] or (sommets[i][0], sommets[i][1])
            entrant = sommets[j][3] or (sommets[j][0], sommets[j][1])
            c1 = _appliquer(matrice, sortant[0], sortant[1])
            c2 = _appliquer(matrice, entrant[0], entrant[1])
            morceaux.append("C{:.4f} {:.4f} {:.4f} {:.4f} {:.4f} {:.4f}"
                            .format(c1[0], c1[1], c2[0], c2[1], x, y))
        precedent = j
    if not morceaux:
        return None
    # Boucle fermée : la dernière primitive revient au premier sommet.
    if prims[-1][2] == prims[0][1]:
        morceaux.append("Z")
    return "".join(morceaux)


def _ellipse(forme, matrice):
    """Une ellipse, rendue en deux arcs -- `transform` suffirait, mais un
    `d` autonome traverse mieux les lecteurs SVG minimalistes."""
    try:
        # LightBurn écrit `Rx`/`Ry` en CAPITALE : chercher "rx" ne trouvait
        # rien et les deux ellipses du fichier passaient à la trappe.
        rx = float(forme.get("Rx") or forme.get("rx") or 0)
        ry = float(forme.get("Ry") or forme.get("ry") or 0)
    except (TypeError, ValueError):
        return None
    if rx <= 0 or ry <= 0:
        return None
    pts = [_appliquer(matrice, rx, 0.0), _appliquer(matrice, -rx, 0.0)]
    # Rayons transformés : on mesure ce que devient un rayon unitaire.
    ox, oy = _appliquer(matrice, 0.0, 0.0)
    ax, ay = _appliquer(matrice, rx, 0.0)
    bx, by = _appliquer(matrice, 0.0, ry)
    rx2 = ((ax - ox) ** 2 + (ay - oy) ** 2) ** 0.5
    ry2 = ((bx - ox) ** 2 + (by - oy) ** 2) ** 0.5
    (x1, y1), (x2, y2) = pts
    return ("M{:.4f} {:.4f}A{:.4f} {:.4f} 0 1 0 {:.4f} {:.4f}"
            "A{:.4f} {:.4f} 0 1 0 {:.4f} {:.4f}Z"
            .format(x1, y1, rx2, ry2, x2, y2, rx2, ry2, x1, y1))


def _parcourir(noeud, matrice, sortie):
    for forme in noeud.findall("Shape"):
        m = _composer(matrice, _xform(forme))
        genre = forme.get("Type")
        if genre == "Group":
            enfants = forme.find("Children")
            _parcourir(enfants if enfants is not None else forme, m, sortie)
        elif genre in ("Path", "Ellipse"):
            d = (_chemin(forme, m) if genre == "Path"
                 else _ellipse(forme, m))
            if d:
                sortie.append((forme.get("CutIndex") or "0", d))


def convertir(chemin_lbrn):
    """Renvoie (liste des `d`, (xmin, ymin, xmax, ymax))."""
    racine = ET.parse(chemin_lbrn).getroot()
    chemins = []
    _parcourir(racine, IDENTITE, chemins)
    xs, ys = [], []
    for _calque, d in chemins:
        for m in re.finditer(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", d):
            xs.append(float(m.group(1)))
            ys.append(float(m.group(2)))
    if not xs:
        return chemins, (0.0, 0.0, 1.0, 1.0)
    return chemins, (min(xs), min(ys), max(xs), max(ys))


def couleur_calque(index):
    """Une couleur DISTINCTE par calque LightBurn, pas la sienne.

    LightBurn colore ses calques selon une palette qui lui est propre ;
    la recopier de mémoire serait inventer une table -- le travers que ce
    dépôt traque depuis qu'une colonne de largeurs fabriquée a faussé deux
    recettes. On répartit donc les teintes régulièrement : les calques
    restent SÉPARABLES, ce qui est le but, sans prétendre reproduire des
    couleurs qu'on n'a pas lues.

    `svg_import.resolve_fill_color` retombe sur le `stroke` faute de
    `fill` : chaque objet importé portera donc la couleur de son calque."""
    try:
        i = int(index)
    except (TypeError, ValueError):
        i = 0
    import colorsys
    # NOMBRE D'OR pour espacer les teintes : un pas de 0,137 rapprochait
    # les calques 2, 9 et 10 dans le même vert -- séparables sur le papier,
    # indiscernables à l'œil, donc inutiles. 0,618 les écarte au maximum.
    r, v, b = colorsys.hsv_to_rgb((i * 0.61803) % 1.0, 0.85, 0.65)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(v * 255), int(b * 255))


def ecrire_svg(chemins, bornes, destination, marge=1.0):
    xmin, ymin, xmax, ymax = bornes
    larg = (xmax - xmin) + 2 * marge
    haut = (ymax - ymin) + 2 * marge
    # Y VERS LE HAUT chez LightBurn, vers le bas en SVG : un miroir, calé
    # sur l'emprise réelle pour que le dessin retombe dans la vue.
    tr = ("translate({:.4f} {:.4f}) scale(1 -1)"
          .format(marge - xmin, haut - marge + ymin))
    with open(destination, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fh.write('<svg xmlns="http://www.w3.org/2000/svg" '
                 'width="{0:.4f}mm" height="{1:.4f}mm" '
                 'viewBox="0 0 {0:.4f} {1:.4f}">\n'.format(larg, haut))
        # Trait proportionnel au dessin : 0,1 mm sur 367 mm ne se voit pas.
        # L'import de l'atelier ignore l'épaisseur, mais le fichier doit
        # rester lisible dans un navigateur ou un éditeur.
        epaisseur = max(0.1, max(larg, haut) / 1200.0)
        fh.write('<g transform="{}" fill="none" '
                 'stroke-width="{:.3f}">\n'.format(tr, epaisseur))
        # UN GROUPE PAR CALQUE : c'est l'organisation que le dessinateur a
        # voulue dans LightBurn, et la perdre en traduisant obligerait à la
        # refaire à la main.
        par_calque = {}
        for calque, d in chemins:
            par_calque.setdefault(calque, []).append(d)
        for calque in sorted(par_calque, key=lambda c: (len(c), c)):
            fh.write('<g id="calque_{0}" stroke="{1}">\n'.format(
                calque, couleur_calque(calque)))
            for d in par_calque[calque]:
                fh.write('<path d="{}"/>\n'.format(d))
            fh.write('</g>\n')
        fh.write('</g>\n</svg>\n')
    return larg, haut


def extraire_vignette(chemin_lbrn, destination):
    """La vignette PNG que LightBurn range dans le fichier -- c'est LE
    moyen de vérifier une conversion : elle montre ce que le dessin est
    censé donner, sans rien devoir à notre lecture du format."""
    racine = ET.parse(chemin_lbrn).getroot()
    n = racine.find("Thumbnail")
    if n is None or not n.get("Source"):
        return False
    with open(destination, "wb") as fh:
        fh.write(base64.b64decode(n.get("Source")))
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source")
    ap.add_argument("destination", nargs="?")
    ap.add_argument("--vignette", help="extrait aussi la vignette du projet")
    args = ap.parse_args()

    dest = args.destination or (os.path.splitext(args.source)[0] + ".svg")
    chemins, bornes = convertir(args.source)
    if not chemins:
        print("Aucune forme trouvée dans %s" % args.source)
        return 1
    larg, haut = ecrire_svg(chemins, bornes, dest)
    calques = sorted(set(c for c, _d in chemins), key=lambda c: (len(c), c))
    print("%d chemin(s) sur %d calque(s) %s -> %s (%.1f x %.1f mm)"
          % (len(chemins), len(calques), calques, dest, larg, haut))
    if args.vignette:
        ok = extraire_vignette(args.source, args.vignette)
        print("vignette du projet : %s" % (args.vignette if ok else "absente"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
