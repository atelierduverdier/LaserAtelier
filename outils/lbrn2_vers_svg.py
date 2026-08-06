#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convertit un projet LightBurn (.lbrn / .lbrn2) en SVG, en ligne de
commande.

    python3 outils/lbrn2_vers_svg.py dessin.lbrn2            # -> dessin.svg
    python3 outils/lbrn2_vers_svg.py dessin.lbrn2 sortie.svg
    python3 outils/lbrn2_vers_svg.py dessin.lbrn2 --vignette v.png

LA CONVERSION N'EST PAS ICI : elle vit dans `svg_import.py`, avec le reste
de la logique d'import, pour que l'atelier puisse l'appeler quand on lui
donne un .lbrn2 sur la même icône que les SVG. Une copie dans ce script
aurait divergé au premier correctif. Ce fichier n'est qu'une façade.
"""
import argparse
import base64
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import svg_import                                             # noqa: E402


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

    chemins, bornes = svg_import.convertir_lightburn(args.source)
    if not chemins:
        print("Aucune forme trouvée dans %s" % args.source)
        return 1
    dest = args.destination or (os.path.splitext(args.source)[0] + ".svg")
    larg, haut = svg_import.ecrire_svg_lightburn(chemins, bornes, dest)
    calques = sorted(set(c for c, _d in chemins), key=lambda c: (len(c), c))
    print("%d chemin(s) sur %d calque(s) %s -> %s (%.1f x %.1f mm)"
          % (len(chemins), len(calques), calques, dest, larg, haut))
    if args.vignette:
        ok = extraire_vignette(args.source, args.vignette)
        print("vignette du projet : %s" % (args.vignette if ok else "absente"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
