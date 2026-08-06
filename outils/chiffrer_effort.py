#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recalcule le TEMPS INVESTI dans l'atelier, et le rend affichable.

    python3 outils/chiffrer_effort.py           # le détail, à l'écran
    python3 outils/chiffrer_effort.py --html    # l'encart du site
    python3 outils/chiffrer_effort.py --md      # l'encart du README

POURQUOI UN OUTIL ET PAS UN CHIFFRE ÉCRIT EN DUR. Christophe, 06/08/2026 :
« il serait bien que dans les futures versions [...] ce soit précisé, et
pas au fond d'une rubrique, car les gens ne s'imaginent pas le temps qu'il
faut ». Un nombre recopié à la main dans trois fichiers vieillit en
silence — c'est exactement ce qui est arrivé à la ligne de version de ce
dépôt, restée fausse pendant **44 livraisons**. Ici on recalcule.

TROIS SOURCES, DE FIABILITÉ DÉCROISSANTE, et le tableau le dit :

1. `git` — dates, commits, versions. Exact.
2. Les `.ngc` réellement produits — relus et chronométrés par l'estimateur
   de l'atelier lui-même. Exact au modèle près, et c'est du temps passé
   DEVANT la machine : un laser ne se laisse pas seul.
3. Le reste de l'établi — montage, zéro, mesures au pied à coulisse, tons
   jugés à l'œil, planches redressées. ESTIMÉ, avec ses hypothèses
   écrites juste à côté pour qu'on puisse les contester.

Le temps de développement est estimé en regroupant les commits en séances
(un écart de plus de deux heures ouvre une séance nouvelle). C'est un
PLANCHER : la réflexion avant le premier commit d'une séance n'y est pas.
"""
import argparse
import glob
import json
import math
import os
import subprocess
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)

# Une séance s'arrête après ce silence, et se voit créditer ce temps
# d'amorce avant son premier commit (ouvrir, relire, retrouver le fil).
ECART_SEANCE_S = 2 * 3600
AMORCE_SEANCE_S = 20 * 60

# Hypothèses de l'établi -- toutes discutables, toutes affichées.
MONTAGE_PAR_JOUR_MIN = 20.0        # bois posé, zéro X/Y, focus, cadrage
REZERO_PAR_JOB_MIN = 5.0           # entre deux jobs d'une même séance
LARGEUR_PAR_POINT_MIN = 1.5        # repérer le trait, mesurer, saisir
TON_PAR_PASTILLE_MIN = 0.5         # jugé à l'œil, à côté de ses voisines
PLANCHE_REDRESSEE_MIN = 15.0       # photo, 4 croix, vérification
PHOTO_RESULTAT_MIN = 3.0


def _git(*args):
    return subprocess.run(["git", "-C", RACINE] + list(args),
                          capture_output=True, text=True).stdout


def developpement():
    """(heures, nb séances, nb commits, nb versions, premier, dernier)."""
    horo = sorted(int(x) for x in _git("log", "--format=%at").split())
    if not horo:
        return 0.0, 0, 0, 0, "?", "?"
    seances, debut, prec = [], horo[0], horo[0]
    for t in horo[1:]:
        if t - prec > ECART_SEANCE_S:
            seances.append((debut, prec))
            debut = t
        prec = t
    seances.append((debut, prec))
    total = sum((f - d) + AMORCE_SEANCE_S for d, f in seances)
    jour = lambda t: time.strftime("%d/%m/%Y", time.localtime(t))
    return (total / 3600.0, len(seances), len(horo),
            len([x for x in _git("tag").split() if x]),
            jour(horo[0]), jour(horo[-1]))


def _dossier_gcode():
    """Où l'atelier écrit ses fichiers, d'après la config de la machine."""
    try:
        import FreeCAD                                    # noqa: F401
        base = FreeCAD.getUserAppDataDir()
    except Exception:
        base = os.path.expanduser("~/.local/share/FreeCAD/v1-1")
    try:
        cfg = json.load(open(os.path.join(base, "laser_atelier_config.json"),
                             encoding="utf-8"))
        return (cfg.get("settings") or {}).get("gcode_dir"), cfg
    except Exception:
        return None, {}


def _estimateur():
    """L'estimateur de l'atelier lui-même, ou None.

    `laser_core` n'a besoin que de bouchons pour s'importer hors de
    FreeCAD -- et on pointe `getUserAppDataDir` sur le VRAI dossier, en
    LECTURE seule : c'est ainsi que l'estimation prend l'avance rapide et
    l'accélération de la machine de l'atelier, et pas des valeurs
    inventées. L'écart n'est pas anecdotique : sans les accélérations, le
    repli ci-dessous annonce 8,0 h là où l'estimateur en compte 11,5 --
    un tiers de moins, parce qu'un remplissage passe son temps à freiner
    et à repartir."""
    global _ESTIMATEUR
    if _ESTIMATEUR is not None:
        return _ESTIMATEUR if _ESTIMATEUR is not False else None
    try:
        import types
        if "FreeCAD" not in sys.modules:
            fc = types.ModuleType("FreeCAD")
            fc.getUserAppDataDir = lambda: os.path.expanduser(
                "~/.local/share/FreeCAD/v1-1/")
            fc.Console = types.SimpleNamespace(
                PrintMessage=lambda m: None, PrintWarning=lambda m: None,
                PrintError=lambda m: None)

            class _V(object):
                def __init__(self, x=0, y=0, z=0):
                    self.x, self.y, self.z = float(x), float(y), float(z)

            fc.Vector = _V
            sys.modules["FreeCAD"] = fc
            sys.modules["Part"] = types.ModuleType("Part")
        sys.path.insert(0, RACINE)
        import laser_core
        _ESTIMATEUR = laser_core.estimate_job_time_seconds
    except Exception:
        _ESTIMATEUR = False
        return None
    return _ESTIMATEUR


_ESTIMATEUR = None


def _duree_gcode(texte, rapide=8000.0, accel=500.0):
    """Chronomètre un fichier avec l'estimateur de l'atelier s'il est
    joignable, sinon avec un repli simple (mêmes règles, sans les
    accélérations -- il sous-estime alors d'environ un tiers)."""
    vrai = _estimateur()
    if vrai is not None:
        try:
            return vrai(texte)
        except Exception:
            pass
    x = y = 0.0
    avance = 1000.0
    total = 0.0
    for ligne in texte.split("\n"):
        ligne = ligne.strip()
        if not (ligne.startswith("G0") or ligne.startswith("G1")):
            continue
        nx, ny = x, y
        for mot in ligne.split()[1:]:
            try:
                v = float(mot[1:])
            except ValueError:
                continue
            if mot[0] == "X":
                nx = v
            elif mot[0] == "Y":
                ny = v
            elif mot[0] == "F":
                avance = max(v, 1.0)
        d = math.hypot(nx - x, ny - y)
        total += d / ((rapide if ligne.startswith("G0") else avance) / 60.0)
        x, y = nx, ny
    return total


def atelier():
    """Ce que l'établi a coûté : mesuré d'abord, estimé ensuite."""
    dossier, cfg = _dossier_gcode()
    fichiers = sorted(glob.glob(os.path.join(dossier, "*.ngc"))) if dossier else []
    machine_s = 0.0
    grave_mm = 0.0
    jours = set()
    for f in fichiers:
        try:
            texte = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        jours.add(time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(f))))
        machine_s += _duree_gcode(texte)
        x = y = 0.0
        for ligne in texte.split("\n"):
            ligne = ligne.strip()
            if not (ligne.startswith("G0") or ligne.startswith("G1")):
                continue
            nx, ny = x, y
            for mot in ligne.split()[1:]:
                try:
                    v = float(mot[1:])
                except ValueError:
                    continue
                if mot[0] == "X":
                    nx = v
                elif mot[0] == "Y":
                    ny = v
            if ligne.startswith("G1"):
                grave_mm += math.hypot(nx - x, ny - y)
            x, y = nx, ny

    def points(bloc):
        if isinstance(bloc, list):
            return len(bloc)
        if isinstance(bloc, dict):
            return sum(points(v) for v in bloc.values())
        return 1

    n_larg = points(cfg.get("burn_widths", {}))
    n_tons = points(cfg.get("nuancier", {}))
    n_photos = points(cfg.get("photos", {}))
    planches = len(glob.glob(os.path.expanduser("~/Planches-LaserAtelier/*.json")))

    n_jours = max(len(jours), 1)
    estime_min = (
        MONTAGE_PAR_JOUR_MIN * n_jours
        + REZERO_PAR_JOB_MIN * max(len(fichiers) - n_jours, 0)
        + LARGEUR_PAR_POINT_MIN * n_larg
        + TON_PAR_PASTILLE_MIN * n_tons
        + PLANCHE_REDRESSEE_MIN * planches
        + PHOTO_RESULTAT_MIN * n_photos)
    return {
        "machine_h": machine_s / 3600.0,
        "estime_h": estime_min / 60.0,
        "fichiers": len(fichiers),
        "jours": len(jours),
        "grave_m": grave_mm / 1000.0,
        "largeurs": n_larg,
        "tons": n_tons,
        "planches": planches,
        "photos": n_photos,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--html", action="store_true", help="l'encart du site")
    ap.add_argument("--md", action="store_true", help="l'encart du README")
    args = ap.parse_args()

    dev_h, seances, commits, versions, premier, dernier = developpement()
    a = atelier()
    total = dev_h + a["machine_h"] + a["estime_h"]
    mesures = a["largeurs"] + a["tons"]

    # VIRGULE DÉCIMALE : le site et le manuel sont en français, et une
    # regénération ne doit pas défaire la typographie à chaque fois.
    def fr(x, dec=1):
        return ("{:.%df}" % dec).format(x).replace(".", ",")

    if args.html:
        # Le bandeau se pose SOUS la rangée de boutons et prend toute la
        # largeur de la COLONNE DE CONTENU -- d'où le `.wrap` qui l'enserre.
        # Pleine fenêtre a été essayé et refusé : « on voit le texte
        # s'étaler à droite et à gauche » du reste de la page.
        print('  <div class="wrap">\n'
              '  <div class="effort">\n'
              '    <b>≈ {tot:.0f} heures</b> pour en arriver là, du {d1} au '
              '{d2} :\n'
              '    <b>≈ {dev:.0f} h</b> de développement ({com} commits, '
              '{ver} versions) et\n'
              '    <b>≈ {ate:.0f} h</b> d\'atelier, dont <b>{mac} h</b> de '
              'laser chronométrées sur\n'
              '    les {fic} fichiers gravés — {gra:.0f} m de trait brûlé et '
              '{mes} mesures relevées\n'
              '    sur le bois.\n'
              # PREMIÈRE PERSONNE SUR LE SITE : c'est la page de
              # Christophe, il y parle en son nom. Demandé le 06/08/2026.
              # Le README et le manuel gardent la troisième personne, où
              # l'auteur n'est pas forcément le lecteur.
              '    <span class="qui">Le code est écrit par Claude '
              '(Anthropic). JE décide,\n'
              '    éprouve chaque version sur le bois et tranche : la '
              'plupart des défauts\n'
              '    corrigés ici ont été trouvés en regardant une planche, '
              'pas en relisant\n'
              '    du code.</span>\n'
              '  </div>\n'
              '  </div>'.format(tot=total, dev=dev_h, com=commits, ver=versions,
                                d1=premier, d2=dernier,
                                ate=a["machine_h"] + a["estime_h"],
                                mac=fr(a["machine_h"]), fic=a["fichiers"],
                                gra=a["grave_m"], mes=mesures))
        return 0
    if args.md:
        print("> **≈ {tot:.0f} heures pour en arriver là**, du {d1} au {d2} : "
              "≈ {dev:.0f} h de développement ({com} commits, {ver} versions) "
              "et ≈ {ate:.0f} h d'atelier, dont **{mac} h de laser** "
              "chronométrées sur les {fic} fichiers gravés — {gra:.0f} m de "
              "trait brûlé et {mes} mesures relevées sur le bois."
              .format(tot=total, dev=dev_h, com=commits, ver=versions,
                      d1=premier, d2=dernier,
                      ate=a["machine_h"] + a["estime_h"],
                      mac=fr(a["machine_h"]), fic=a["fichiers"],
                      gra=a["grave_m"], mes=mesures))
        return 0

    print("=" * 64)
    print("TEMPS INVESTI DANS L'ATELIER -- recalculé le %s"
          % time.strftime("%d/%m/%Y"))
    print("=" * 64)
    print()
    print("EXACT (git) : du %s au %s" % (premier, dernier))
    print("   %d commits, %d versions publiées, %d séances"
          % (commits, versions, seances))
    print("   développement estimé : %.0f h   (séances, +%d min d'amorce"
          " chacune -- c'est un PLANCHER)" % (dev_h, AMORCE_SEANCE_S // 60))
    print()
    print("EXACT (fichiers gravés) :")
    print("   %d fichiers .ngc sur %d jours d'établi" % (a["fichiers"], a["jours"]))
    print("   %.1f h de machine, %.0f m de trait brûlé"
          % (a["machine_h"], a["grave_m"]))
    print()
    print("ESTIMÉ (le reste de l'établi) : %.0f h" % a["estime_h"])
    print("   montage/zéro : %.0f min x %d jours" % (MONTAGE_PAR_JOUR_MIN, a["jours"]))
    print("   re-zéro      : %.0f min x %d jobs"
          % (REZERO_PAR_JOB_MIN, max(a["fichiers"] - a["jours"], 0)))
    print("   largeurs     : %.1f min x %d points" % (LARGEUR_PAR_POINT_MIN, a["largeurs"]))
    print("   tons         : %.1f min x %d pastilles" % (TON_PAR_PASTILLE_MIN, a["tons"]))
    print("   planches     : %.0f min x %d" % (PLANCHE_REDRESSEE_MIN, a["planches"]))
    print("   photos       : %.0f min x %d" % (PHOTO_RESULTAT_MIN, a["photos"]))
    print()
    print("-" * 64)
    print("TOTAL : %.0f h  (%.0f h de code + %.0f h d'atelier)"
          % (total, dev_h, a["machine_h"] + a["estime_h"]))
    print("-" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
