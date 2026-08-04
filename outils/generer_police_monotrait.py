#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convertit une police SVG mono-trait en module
`polices_monotrait/hershey_font_<clé>.py`.

    python3 outils/generer_police_monotrait.py source.svg cle "Nom affiché"

Ce script MANQUAIT : les deux modules livrés portent « Généré
automatiquement -- ne pas éditer à la main », mais rien ne permettait de
les régénérer. Une donnée qu'on ne sait plus produire est une donnée qu'on
n'ose plus corriger -- et c'est exactement ce qui a laissé « ç », « æ » et
« œ » muets dans la police par défaut pendant des mois.

L'ANALYSE DU CHEMIN passe par `svg_import`, le parseur déjà écrit pour
l'import de dessins : même tokeniseur, même aplatissement de courbes, mêmes
pièges déjà réglés (les drapeaux d'arc collés aux nombres, la répétition
implicite de commande). Réécrire un second parseur ici, c'était s'offrir un
second jeu de bogues.

MONO-TRAIT, pas contour : une police dont les glyphes se REFERMENT dessine
chaque branche deux fois et ruine l'intérêt du mode. Le script le détecte
et refuse, au lieu de livrer une police qui grave tout en double.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import svg_import

SVG_NS = "{http://www.w3.org/2000/svg}"
# Flèche d'aplatissement, en unités POLICE. À 1000 unités par cadratin et
# une capitale gravée à 10 mm, 4 unités valent 0,04 mm sur le bois -- sous
# la plus fine brûlure mesurée (0,10 mm), donc invisible.
FLECHE = 4.0


def traits_par_lettre(glyphes, cars="AEHOBMSnmoe"):
    """Nombre moyen de traits par lettre de référence -- l'indicateur qui
    sépare une police MONO-TRAIT d'une police à fût contourné.

    Les variantes « Med » / « Bold » de Hershey ne doublent pas un trait
    à côté de lui-même : elles dessinent le CONTOUR du fût. Le 'H' de
    HersheySansMed compte 6 traits contre 3 à HersheySans1, et son fût est
    un rectangle de 32 unités de large sur une capitale de 500. Au laser,
    ça grave deux fois et ça élargit -- ce que le mode « trait simple »
    existe justement pour éviter.

    UN DÉTECTEUR PAR PROXIMITÉ A ÉTÉ ESSAYÉ ET JETÉ : cherchant les points
    ayant un autre trait à moins de 6 % de la capitale, il rendait 27 %
    pour la police simple contre 28 % pour la contournée -- il attrapait
    les jonctions, pas les doublages. Un chiffre qui ne sépare rien est
    pire qu'aucun chiffre : il rassure. Le compte de traits, lui, sépare
    du simple au double."""
    n = tot = 0
    for c in cars:
        traits = glyphes.get(c, (0, []))[1]
        if traits:
            tot += len(traits)
            n += 1
    return tot / float(n) if n else 0.0


def _attr(el, *noms):
    for n in noms:
        v = el.get(n)
        if v not in (None, ""):
            return v
    return None


def lire_police(chemin):
    """(glyphes, cap_height, adv_defaut, nom) depuis une police SVG."""
    racine = ET.parse(chemin).getroot()
    # `or` SUR UN ÉLÉMENT EST UN PIÈGE : ElementTree rend FAUX un élément
    # SANS ENFANT, et <font-face> n'en a aucun. Le `or` retombait donc sur la
    # recherche sans espace de noms, qui ne trouve rien -- « pas de <font> »
    # sur un fichier qui en contient un. Toujours tester `is not None`.
    def _trouve(nom):
        for chemin in (".//{}{}".format(SVG_NS, nom), ".//" + nom):
            el = racine.find(chemin)
            if el is not None:
                return el
        return None

    font, face = _trouve("font"), _trouve("font-face")
    if font is None or face is None:
        raise SystemExit("{} : pas de <font>/<font-face>".format(chemin))
    upem = float(_attr(face, "units-per-em") or 1000)
    cap_declaree = float(_attr(face, "cap-height") or _attr(face, "ascent")
                         or upem * 0.7)
    adv_def = float(_attr(font, "horiz-adv-x") or upem * 0.5)
    nom = _attr(face, "font-family") or os.path.basename(chemin)

    glyphes, fermes, total = {}, 0, 0
    for g in font.iter():
        if not g.tag.endswith("glyph"):
            continue
        uni = g.get("unicode")
        if uni is None:
            continue
        # Les entités numériques (&#xE9;) sont déjà décodées par ElementTree.
        if len(uni) != 1:
            continue
        adv = float(g.get("horiz-adv-x") or adv_def)
        d = (g.get("d") or "").strip()
        if not d:
            glyphes[uni] = (adv, [])
            continue
        total += 1
        if re.search(r"[Zz]\s*$", d) or re.search(r"[Zz]", d):
            fermes += 1
        sous, _avert = svg_import.path_d_to_subpaths(d, tol=FLECHE)
        traits = []
        for sp in sous:
            pts = [(round(x, 1), round(y, 1)) for x, y in sp["points"]]
            # Points consécutifs identiques : rien à graver entre eux.
            propre = [pts[0]] if pts else []
            for p in pts[1:]:
                if p != propre[-1]:
                    propre.append(p)
            if len(propre) >= 2:
                traits.append(propre)
        glyphes[uni] = (adv, traits)

    # LA HAUTEUR DE CAPITALE SE MESURE, elle ne se croit pas. Les polices
    # d'oskay déclarent `cap-height="500"` alors que leurs capitales montent
    # à 662 : un rapport de 1,324. Le mode Texte met ce nombre au
    # dénominateur de son échelle, donc un texte demandé à 2,5 mm sortait à
    # 3,31 -- 32 % trop haut, sur toutes les planches de calibration.
    # Attrapé par test_mire_planches, qui mesure la hauteur gravée du nom du
    # laser ; sans lui, chaque étiquette serait partie fausse.
    # ... et c'est l'ÉCART du 'H', pas son sommet. Dans les polices EMS le
    # trait est l'AXE du fût, donc rentré : leur 'H' court de y=22 à 652,
    # soit 630 de haut pour un sommet à 652. Prendre le sommet gravait 3,4 %
    # trop court -- et surtout, la définition « hauteur de capitale » cesse
    # d'être celle que Christophe mesure au pied à coulisse sur le bois.
    # Sur les Hershey d'origine, qui posent leurs capitales sur la ligne de
    # base, l'écart vaut le sommet : 662 avant comme après.
    cap = 0.0
    for ref in "HXEIT":
        g = glyphes.get(ref)
        if g and g[1]:
            ys = [y for t in g[1] for _x, y in t]
            cap = max(ys) - min(ys)
            break
    if cap <= 0:
        cap = cap_declaree
    return glyphes, cap, adv_def, nom, fermes, total


def ecrire_module(chemin_py, glyphes, cap, adv_def, nom, source, licence):
    lignes = ['# -*- coding: utf-8 -*-',
              '"""Police vectorielle MONO-TRAIT (un seul trait par branche).',
              '',
              '{}'.format(nom),
              'Source : {}'.format(source),
              'Licence : {}'.format(licence),
              '',
              'Généré par outils/generer_police_monotrait.py -- ne pas éditer',
              'à la main. GLYPHES[car] = (avance_x, [trait, ...]) ;',
              'trait = [(x, y), ...] en unités police (ligne de base y=0,',
              'hauteur de capitale = CAP_HEIGHT).',
              '"""',
              '',
              'CAP_HEIGHT = {:.0f}'.format(cap),
              'ADV_DEFAULT = {:.0f}'.format(adv_def),
              '',
              'GLYPHES = {']
    for car in sorted(glyphes, key=ord):
        adv, traits = glyphes[car]
        rep = repr(car)
        corps = ",".join(
            "[" + ",".join("({:g},{:g})".format(x, y) for x, y in t) + "]"
            for t in traits)
        lignes.append("    {}: ({:.0f}, [{}]),".format(rep, adv, corps))
    lignes.append("}")
    with open(chemin_py, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n")


def main():
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    src, cle, nom_affiche = sys.argv[1], sys.argv[2], sys.argv[3]
    licence = sys.argv[4] if len(sys.argv) > 4 else "voir la source"
    glyphes, cap, adv, nom, fermes, total = lire_police(src)
    if total and fermes > total * 0.2:
        raise SystemExit(
            "REFUS : {}/{} glyphes se referment (Z) -- c'est une police à "
            "CONTOUR, pas mono-trait. Elle graverait chaque branche deux "
            "fois.".format(fermes, total))
    tpl = traits_par_lettre(glyphes)
    vides = [c for c, (a, t) in glyphes.items() if not t and c != " "]
    dest = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "polices_monotrait",
        "hershey_font_{}.py".format(cle))
    ecrire_module(dest, glyphes, cap, adv, nom_affiche, src, licence)
    print("{:34} {:4} gl. | cap {:4.0f} | {:4.1f} traits/lettre{} | {} vides {}"
          .format(nom_affiche, len(glyphes), cap, tpl,
                  "  <-- FUT CONTOURNE" if tpl >= 4.0 else "              ",
                  len(vides),
                  "(" + " ".join(sorted(vides)[:8]) + ")" if vides else ""))


if __name__ == "__main__":
    main()
