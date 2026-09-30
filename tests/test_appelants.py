# -*- coding: utf-8 -*-
"""`outils/appelants.py` retrouve TOUS les appels — ceux que grep et CodeGraph manquaient.

Le 30/09/2026, CodeGraph (graphe de code par tree-sitter) trouvait 0 appelant sur 14 à
`save_burn_widths` : il ne relie pas `import laser_core as core` puis `core.f(...)`, la forme
même des panneaux et des tests. L'outil qui le remplace se juge ici sur un petit dépôt fabriqué,
dont on connaît chaque appel par construction :

  - appel direct, appel par alias de module, appel de méthode par `self.` ;
  - rappel passé sans être appelé (`connect(core.f)`) → RÉFÉRENCE, pas appel ;
  - `getattr(core, "f")` → CHAÎNE ;
  - docstring et commentaire qui citent `f()` → rien ;
  - la fonction englobante et la ligne exactes ;
  - `--sans-tests` écarte le dossier tests/.

Plus un regard sur l'atelier réel : `save_burn_widths` a des appelants par `core.` dans
task_panels.py — ceux que CodeGraph ne voyait pas.

Aucun besoin de FreeCAD : on lit des fichiers.
"""
import os
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(RACINE, "outils"))
import appelants  # noqa: E402

echecs = 0


def verifier(ok, quoi):
    global echecs
    print(("  ok   " if ok else "ÉCHEC ") + quoi)
    if not ok:
        echecs += 1


FICHIERS = {
    "coeur.py": '''
def f(x):
    """Doc qui cite f() : ne compte pas."""
    return x

def g():
    return f(1)          # ligne 7 : appel direct, dans g
''',
    "panneau.py": '''
import coeur as core

class Panneau:
    def __init__(self, bouton):
        bouton.connect(core.f)            # ligne 6 : référence (rappel)
    def generer(self):
        # f() dans un commentaire : rien
        return core.f(2)                  # ligne 9 : appel par alias, dans Panneau.generer
    def dynamique(self):
        return getattr(core, "f")(3)      # ligne 11 : chaîne
''',
    "tests/test_x.py": '''
import coeur as core
core.f(4)                                 # ligne 3 : appel au niveau module
''',
}

with tempfile.TemporaryDirectory() as d:
    for nom, texte in FICHIERS.items():
        chemin = os.path.join(d, nom)
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as fh:
            fh.write(texte)
    trouves, definitions, illisibles = appelants.relever(["f"], d)
    appels = sorted((t["fichier"], t["ligne"], t["dans"]) for t in trouves if t["genre"] == "appel")
    refs = [(t["fichier"], t["ligne"]) for t in trouves if t["genre"] == "référence"]
    chaines = [(t["fichier"], t["ligne"]) for t in trouves if t["genre"] == "chaîne"]
    verifier(appels == [("coeur.py", 7, "g"), ("panneau.py", 9, "Panneau.generer"), ("tests/test_x.py", 3, "<module>")],
             f"trois appels, fonction englobante et ligne justes (direct, par alias core., au niveau module) : {appels}")
    verifier(refs == [("panneau.py", 6)], f"le rappel connect(core.f) est une RÉFÉRENCE, pas un appel : {refs}")
    verifier(chaines == [("panneau.py", 11)], f"getattr(core, \"f\") est signalé en CHAÎNE : {chaines}")
    verifier(definitions == [{"nom": "f", "fichier": "coeur.py", "ligne": 2}] and not illisibles,
             "la définition trouvée ; docstring et commentaire ignorés ; rien d'illisible")
    sans_tests, _, _ = appelants.relever(["f"], d, avec_tests=False)
    verifier(not any(t["fichier"].startswith("tests") for t in sans_tests) and len(sans_tests) == len(trouves) - 1,
             "--sans-tests écarte tests/")

# L'atelier réel : les appels par « core. » de task_panels.py, que CodeGraph ne reliait pas.
trouves, definitions, _ = appelants.relever(["save_burn_widths"])
par_core = [t for t in trouves if t["genre"] == "appel" and t["fichier"] == "task_panels.py" and t["detail"] == "core."]
verifier(any(d["fichier"] == "laser_core.py" for d in definitions) and len(par_core) >= 1,
         f"atelier réel : save_burn_widths appelée par core. depuis task_panels.py ({len(par_core)} fois)")

print("\n%s — %d échec(s)" % ("ÉCHEC" if echecs else "tout est vert", echecs))
sys.exit(1 if echecs else 0)
