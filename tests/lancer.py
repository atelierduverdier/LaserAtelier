#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lanceur des tests headless de l'atelier.

    python3 tests/lancer.py              # tout
    python3 tests/lancer.py lignes am    # ceux dont le nom contient ça
    python3 tests/lancer.py --captures   # régénère les captures de panneaux
    python3 tests/lancer.py --captures curved   # une seule
    python3 tests/lancer.py --sequentiel # un test à la fois (débogage)

Se lance avec le python SYSTÈME : il ne fait que déléguer chaque test à un
sous-processus, avec l'interpréteur de FreeCAD et son PYTHONPATH.

Cet interpréteur vit dans l'AppImage montée, dont le chemin
(`/tmp/.mount_FreeCA*`) CHANGE à chaque relancement de FreeCAD -- de quoi
faire croire à une panne d'environnement alors que le montage a juste
bougé. On le redécouvre donc à chaque exécution.

Chaque test tourne dans son PROPRE processus : un panneau Qt qui plante ou
une config globale modifiée ne contamine pas les suivants, et le rapport
reste lisible.

Et comme ils sont VRAIMENT indépendants -- chacun avec sa propre copie
jetable de la config, créée par `harness.preparer` dans son propre dossier
temporaire -- ils tournent EN PARALLÈLE. Mesuré sur la machine de
Christophe (32 cœurs) : **1 min 54 s en séquentiel, 22,7 s à 16 fronts**,
soit 5x. Au-delà il n'y a plus rien à prendre : à 32 fronts on mesure
20,9 s, exactement la durée du test le plus long (`test_plume`) -- c'est
le plancher.

Le nombre de fronts est plafonné par la MÉMOIRE autant que par les cœurs :
un test pèse ~252 Mo (pic mesuré à 10,5 Go pour 16 en parallèle, contre
6,5 Go au repos). Sur une machine plus petite, `--sequentiel` reste là, et
c'est aussi ce qu'il faut pour lire les `print` d'un test dans l'ordre.

Vérifié avant d'être livré : quatre exécutions parallèles d'affilée, 37
tests OK à chaque fois. Une suite qui rougirait au hasard apprendrait à
ignorer le rouge -- c'est le contraire du but.
"""
import glob
import shutil
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)


def python_freecad():
    """(interpréteur, PYTHONPATH) de FreeCAD, ou (None, None).

    Deux installations possibles, cherchées dans cet ordre :

    1. **AppImage montée** sous `/tmp/.mount_FreeCA*` (ou `.mount_freeca*`, la
       casse dépend du nom du fichier : l'AppImage officielle donne `FreeCA`,
       celle d'appman `freeca`). Ce chemin CHANGE à chaque relancement de
       FreeCAD, d'où la redécouverte à chaque exécution.
    2. **Paquet système** (`extra/freecad`), dont les modules vivent dans
       `/usr/lib/freecad/lib` et s'importent depuis le python ordinaire.

    L'AppImage passe en premier : si elle tourne, c'est elle que Christophe a
    sous les yeux, et tester contre une AUTRE installation que celle qui vient
    de produire le fichier serait une comparaison sans valeur.

    Le cas système est devenu nécessaire le 16/08/2026 : sur le poste
    réinstallé, les deux AppImages 1.1.3 avortent au démarrage
    (« Could not initialize GLX » — leurs bibliothèques Qt/GL figées en juillet
    contre Mesa 26.2). Plus aucune AppImage ne se monte, donc plus aucun test
    ne pouvait tourner, alors que le cœur de FreeCAD, lui, fonctionne
    parfaitement en console.
    """
    for motif in ("/tmp/.mount_FreeCA*", "/tmp/.mount_freeca*"):
        for base in sorted(glob.glob(motif), reverse=True):
            exe = os.path.join(base, "usr", "bin", "python")
            lib = os.path.join(base, "usr", "lib")
            if os.path.exists(exe) and os.path.exists(os.path.join(lib, "FreeCAD.so")):
                return exe, lib

    lib = "/usr/lib/freecad/lib"
    exe = shutil.which("python3")
    if exe and os.path.exists(os.path.join(lib, "FreeCAD.so")):
        return exe, lib
    return None, None


def _purger_pyc():
    """Efface les __pycache__ du dépôt avant de lancer quoi que ce soit.

    UN SABOTAGE PEUT PASSER POUR VERT À CAUSE D'UN .pyc PÉRIMÉ, et ce
    protocole-là est ce sur quoi tout le dossier repose. Python invalide un
    bytecode sur la MTIME EN SECONDES et la TAILLE du source : une
    modification de même longueur, annulée dans la même seconde -- ce que
    fait exactement un aller-retour `cp` de sabotage -- laisse les deux
    inchangés, et le module chargé reste l'ancien.

    Reproduit délibérément le 04/08/2026 en remplaçant `math.sin` par
    `math.cos` (même nombre d'octets) : le fichier revenu sain continuait
    d'échouer, `inspect.getsource` montrait pourtant le bon code. Dans
    l'autre sens, un sabotage aurait tourné contre du bytecode sain et
    l'aurait déclaré inoffensif.

    Trois lignes valent mieux que ce diagnostic-là, une seconde fois."""
    for dossier, sous, _f in os.walk(RACINE):
        for d in list(sous):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dossier, d), ignore_errors=True)
                sous.remove(d)


def _BAVARDAGE(ligne):
    """Vrai pour les lignes de bruit que fontconfig écrit sur stderr.

    Elles n'apprennent rien et il y en a une dizaine par test : les 14
    dernières lignes d'un échec étaient donc SES AVERTISSEMENTS, pas son
    message d'assertion. Le rapport nommait le test fautif et cachait la
    raison -- on lisait la vraie cause en re-lançant à la main."""
    return ("Fontconfig warning" in ligne
            or "invalid constant used" in ligne
            or "invalid attribute" in ligne)


def _fronts(n_tests):
    """Combien de tests lancer de front.

    Borné par les cœurs, par la MÉMOIRE (un test pèse ~252 Mo mesurés, on
    garde 2 Go au système) et par le nombre de tests. Plafonné à 16 : à 32
    fronts on ne gagne plus que 1,8 s, le plancher étant la durée du test
    le plus long."""
    coeurs = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") \
        else (os.cpu_count() or 4)
    limite = 16
    try:
        with open("/proc/meminfo") as fh:
            for ligne in fh:
                if ligne.startswith("MemAvailable:"):
                    dispo_mo = int(ligne.split()[1]) / 1024.0
                    limite = min(limite, max(1, int((dispo_mo - 2048) / 252)))
                    break
    except Exception:
        pass
    return max(1, min(coeurs, limite, n_tests))


def main(filtres):
    exe, lib = python_freecad()
    if exe is None:
        print("FreeCAD introuvable, ni en AppImage ni en paquet système.\n"
              "  • AppImage : lance FreeCAD une fois (les modules vivent dans "
              "son montage /tmp/.mount_*), puis relance ces tests ;\n"
              "  • paquet système : sudo pacman -S freecad "
              "(attendu dans /usr/lib/freecad/lib).")
        return 2
    print("interpréteur : {}\n".format(exe))
    _purger_pyc()

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [lib, ICI, RACINE] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env["QT_QPA_PLATFORM"] = "offscreen"
    # LES POLICES DU SYSTÈME, sinon les captures mentent. L'AppImage impose
    # son propre environnement et fontconfig ne trouvait aucune config
    # (« Cannot load default config file »), si bien que Qt retombait sur
    # une police sans les chiffres cerclés : toutes les captures livrées au
    # manuel et au site affichaient « @ Entrer les mesures » au lieu de
    # « ① Entrer les mesures ». Toute la convention ①②③ -- l'ossature du
    # mode d'emploi -- était invisible pour qui découvre par la doc.
    # Constaté le 03/08/2026 sur une capture publiée depuis la v2.13.2.
    for cle, chemin in (("FONTCONFIG_PATH", "/etc/fonts"),
                        ("FONTCONFIG_FILE", "/etc/fonts/fonts.conf")):
        if os.path.exists(chemin):
            env.setdefault(cle, chemin)

    # `captures.py` n'est pas un test (il n'est pas nommé test_*, donc le glob
    # ne le voit pas) mais il a besoin du MÊME interpréteur et du même
    # harnais -- donc de la config redirigée vers une copie jetable. Son
    # en-tête documentait cette entrée depuis toujours ; elle n'existait pas.
    if filtres and filtres[0] == "--captures":
        r = subprocess.run([exe, os.path.join(ICI, "captures.py")] + filtres[1:],
                           env=env, cwd=RACINE, timeout=1800)
        return r.returncode

    sequentiel = "--sequentiel" in filtres
    filtres = [x for x in filtres if x != "--sequentiel"]

    fichiers = sorted(glob.glob(os.path.join(ICI, "test_*.py")))
    if filtres:
        fichiers = [f for f in fichiers
                    if any(x.lower() in os.path.basename(f).lower()
                           for x in filtres)]
    if not fichiers:
        print("aucun test ne correspond.")
        return 1

    def lancer_un(f):
        nom = os.path.basename(f)[:-3]
        t0 = time.time()
        r = subprocess.run([exe, f], env=env, cwd=RACINE,
                           capture_output=True, text=True, timeout=1800)
        return nom, r, time.time() - t0

    def rapporter(nom, r, dt, ok, rates):
        if r.returncode == 0:
            ok.append(nom)
            print("  OK      {:<32} {:>5.1f} s".format(nom, dt))
        else:
            rates.append(nom)
            print("  ÉCHEC   {:<32} {:>5.1f} s".format(nom, dt))
            sortie = [l for l in (r.stdout + r.stderr).strip().split("\n")
                      if not _BAVARDAGE(l)]
            for l in sortie[-14:]:
                print("          " + l)

    ok, rates = [], []
    if sequentiel or len(fichiers) == 1:
        for f in fichiers:
            rapporter(*lancer_un(f), ok=ok, rates=rates)
    else:
        fronts = _fronts(len(fichiers))
        print("  ({} tests, {} de front)\n".format(len(fichiers), fronts))
        # Les résultats sont rapportés DANS L'ORDRE D'ARRIVÉE, pas dans
        # l'ordre alphabétique : voir défiler les tests finis renseigne
        # pendant l'attente, et le récapitulatif final ne change pas.
        with ThreadPoolExecutor(max_workers=fronts) as ex:
            for nom, r, dt in ex.map(lancer_un, fichiers):
                rapporter(nom, r, dt, ok, rates)
    print("\n{} test(s) OK, {} échec(s)".format(len(ok), len(rates)))
    if rates:
        print("échecs : " + ", ".join(rates))
    return 1 if rates else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
