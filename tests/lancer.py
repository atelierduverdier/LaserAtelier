#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lanceur des tests headless de l'atelier.

    python3 tests/lancer.py              # tout
    python3 tests/lancer.py lignes am    # ceux dont le nom contient ça

Se lance avec le python SYSTÈME : il ne fait que déléguer chaque test à un
sous-processus, avec l'interpréteur de FreeCAD et son PYTHONPATH.

Cet interpréteur vit dans l'AppImage montée, dont le chemin
(`/tmp/.mount_FreeCA*`) CHANGE à chaque relancement de FreeCAD -- de quoi
faire croire à une panne d'environnement alors que le montage a juste
bougé. On le redécouvre donc à chaque exécution.

Chaque test tourne dans son PROPRE processus : un panneau Qt qui plante ou
une config globale modifiée ne contamine pas les suivants, et le rapport
reste lisible.
"""
import glob
import os
import subprocess
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)


def python_freecad():
    """(interpréteur, PYTHONPATH) de FreeCAD, ou (None, None)."""
    for base in sorted(glob.glob("/tmp/.mount_FreeCA*"), reverse=True):
        exe = os.path.join(base, "usr", "bin", "python")
        lib = os.path.join(base, "usr", "lib")
        if os.path.exists(exe) and os.path.exists(os.path.join(lib, "FreeCAD.so")):
            return exe, lib
    return None, None


def main(filtres):
    exe, lib = python_freecad()
    if exe is None:
        print("FreeCAD introuvable : aucune AppImage montée sous "
              "/tmp/.mount_FreeCA*.\nLance FreeCAD une fois, puis relance "
              "ces tests (les modules FreeCAD/Part y vivent).")
        return 2
    print("interpréteur : {}\n".format(exe))

    fichiers = sorted(glob.glob(os.path.join(ICI, "test_*.py")))
    if filtres:
        fichiers = [f for f in fichiers
                    if any(x.lower() in os.path.basename(f).lower()
                           for x in filtres)]
    if not fichiers:
        print("aucun test ne correspond.")
        return 1

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [lib, ICI, RACINE] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env["QT_QPA_PLATFORM"] = "offscreen"

    ok, rates = [], []
    for f in fichiers:
        nom = os.path.basename(f)[:-3]
        t0 = time.time()
        r = subprocess.run([exe, f], env=env, cwd=RACINE,
                           capture_output=True, text=True, timeout=1800)
        dt = time.time() - t0
        if r.returncode == 0:
            ok.append(nom)
            print("  OK      {:<32} {:>5.1f} s".format(nom, dt))
        else:
            rates.append(nom)
            print("  ÉCHEC   {:<32} {:>5.1f} s".format(nom, dt))
            sortie = (r.stdout + r.stderr).strip().split("\n")
            for l in sortie[-14:]:
                print("          " + l)
    print("\n{} test(s) OK, {} échec(s)".format(len(ok), len(rates)))
    if rates:
        print("échecs : " + ", ".join(rates))
    return 1 if rates else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
