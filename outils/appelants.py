#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QUI APPELLE CETTE FONCTION ? Tous les appels, dans tout l'atelier, en une commande.

    python3 outils/appelants.py save_burn_widths
    python3 outils/appelants.py generate_gcode_halftone burn_width_at   # plusieurs d'un coup
    python3 outils/appelants.py _on_save --sans-tests                    # hors tests/
    python3 outils/appelants.py dot_micro_stroke --json

POURQUOI UN OUTIL. La règle « corriger tous les appelants » (un correctif branché sur toute la
famille, pas sur le premier cas vu) suppose de les TROUVER tous. `grep` mêle les appels aux
docstrings, aux commentaires et au CHANGELOG, et ne dit pas dans quelle fonction tombe
chaque appel ; il faut relire chaque occurrence. Essayé le 30/09/2026 : CodeGraph (un graphe
de code bâti par tree-sitter) ne relie PAS les appels par alias de module — or les panneaux et
les tests appellent le cœur par `import laser_core as core` puis `core.fonction(...)`. Il
trouvait 0 appelant sur 8 à `generate_gcode_halftone`, 0 sur 14 à `save_burn_widths`, et son
« impact » annonçait 1 symbole touché : une fausse assurance, pire que pas d'outil.

Ici, l'analyseur de Python lui-même (`ast`) : chaque `f(...)` et chaque `x.f(...)` est un
appel, où que ce soit, avec la fonction (ou la méthode) qui l'englobe et sa ligne. Trois
choses que `grep` confondait sont rangées à part :

  - APPELS : `f(...)`, `core.f(...)`, `self.f(...)` — le receveur est affiché, parce qu'une
    méthode `_on_save` de deux classes différentes porte le même nom ;
  - RÉFÉRENCES sans appel : la fonction passée en rappel (`bouton.clicked.connect(self._on_save)`,
    `QTimer.singleShot(0, self._generer)`, une table `{"diffusion": core.generate_...}`) —
    changer sa signature les touche aussi ;
  - CHAÎNES égales au nom (`getattr(core, "save_burn_widths")`, une clé de dispatch) — un appel
    que l'analyse ne peut pas suivre, montré pour qu'on le regarde.

Les commentaires et les docstrings ne sont jamais comptés. `polices_monotrait/` (des données),
`.codegraph/`, `__pycache__/` et `.git/` sont ignorés. Ce qui reste hors de portée : un appel
construit dynamiquement autrement que par une chaîne littérale.

Sans FreeCAD, sans dépendance : le python du système suffit.
"""
import argparse
import ast
import json
import os
import sys
import warnings

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
IGNORES = {"polices_monotrait", ".codegraph", "__pycache__", ".git"}


def fichiers_python(racine, avec_tests=True):
    for dossier, sous, noms in os.walk(racine):
        sous[:] = sorted(d for d in sous if d not in IGNORES and not (not avec_tests and d == "tests"))
        for nom in sorted(noms):
            if nom.endswith(".py"):
                yield os.path.join(dossier, nom)


def receveur(noeud):
    """« core », « self », « self.panneau »… : ce qui est devant `.f`, lisiblement."""
    try:
        return ast.unparse(noeud)
    except Exception:
        return "?"


class Releveur(ast.NodeVisitor):
    def __init__(self, cibles, fichier):
        self.cibles = cibles
        self.fichier = fichier
        self.pile = []
        self.appels_vus = set()   # id() des nœuds déjà comptés comme fonction appelée
        self.trouves = []

    def _englobant(self):
        return ".".join(self.pile) or "<module>"

    def _noter(self, genre, nom, ligne, detail=""):
        self.trouves.append({"genre": genre, "nom": nom, "fichier": self.fichier, "ligne": ligne,
                             "dans": self._englobant(), "detail": detail})

    def _portee(self, noeud):
        self.pile.append(noeud.name)
        self.generic_visit(noeud)
        self.pile.pop()

    def visit_FunctionDef(self, noeud):
        self._portee(noeud)

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = _portee

    def visit_Call(self, noeud):
        f = noeud.func
        if isinstance(f, ast.Name) and f.id in self.cibles:
            self._noter("appel", f.id, noeud.lineno)
            self.appels_vus.add(id(f))
        elif isinstance(f, ast.Attribute) and f.attr in self.cibles:
            self._noter("appel", f.attr, noeud.lineno, receveur(f.value) + ".")
            self.appels_vus.add(id(f))
        self.generic_visit(noeud)

    def visit_Name(self, noeud):
        if noeud.id in self.cibles and isinstance(noeud.ctx, ast.Load) and id(noeud) not in self.appels_vus:
            self._noter("référence", noeud.id, noeud.lineno)

    def visit_Attribute(self, noeud):
        if noeud.attr in self.cibles and isinstance(noeud.ctx, ast.Load) and id(noeud) not in self.appels_vus:
            self._noter("référence", noeud.attr, noeud.lineno, receveur(noeud.value) + ".")
        self.generic_visit(noeud)

    def visit_Constant(self, noeud):
        if isinstance(noeud.value, str) and noeud.value in self.cibles:
            self._noter("chaîne", noeud.value, noeud.lineno)

    def visit_Expr(self, noeud):
        # Une chaîne seule en instruction est une docstring (ou un commentaire en chaîne) : ignorée.
        if isinstance(noeud.value, ast.Constant) and isinstance(noeud.value.value, str):
            return
        self.generic_visit(noeud)


def relever(cibles, racine=RACINE, avec_tests=True):
    """Tous les appels, références et chaînes des noms `cibles`, plus leurs définitions."""
    trouves, definitions, illisibles = [], [], []
    for chemin in fichiers_python(racine, avec_tests):
        relatif = os.path.relpath(chemin, racine)
        try:
            with open(chemin, encoding="utf-8") as f:
                source = f.read()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)   # les « \s » des vieux motifs
                arbre = ast.parse(source, filename=relatif)
        except (SyntaxError, UnicodeDecodeError, ValueError) as e:
            illisibles.append(f"{relatif} : {e}")
            continue
        for n in ast.walk(arbre):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name in cibles:
                definitions.append({"nom": n.name, "fichier": relatif, "ligne": n.lineno})
        r = Releveur(set(cibles), relatif)
        r.visit(arbre)
        trouves += r.trouves
    return trouves, definitions, illisibles


def main(argv=None):
    p = argparse.ArgumentParser(description="Tous les appels d'une fonction dans l'atelier (analyseur de Python).")
    p.add_argument("noms", nargs="+", help="nom(s) de fonction ou de méthode")
    p.add_argument("--sans-tests", action="store_true", help="ignorer tests/")
    p.add_argument("--json", action="store_true", help="sortie JSON")
    p.add_argument("--racine", default=RACINE, help="dossier à parcourir (défaut : l'atelier)")
    a = p.parse_args(argv)
    trouves, definitions, illisibles = relever(a.noms, a.racine, not a.sans_tests)
    if a.json:
        print(json.dumps({"definitions": definitions, "trouves": trouves, "illisibles": illisibles},
                         ensure_ascii=False, indent=1))
        return 0
    for nom in a.noms:
        defs = [d for d in definitions if d["nom"] == nom]
        les = [t for t in trouves if t["nom"] == nom]
        appels = [t for t in les if t["genre"] == "appel"]
        appelants = {(t["fichier"], t["dans"]) for t in appels}
        print(f"{nom} — {len(appels)} appel(s) dans {len(appelants)} fonction(s)"
              + "".join(f", {n} {g}(s)" for g in ("référence", "chaîne")
                        for n in [sum(t['genre'] == g for t in les)] if n))
        for d in defs:
            print(f"  défini   {d['fichier']}:{d['ligne']}")
        if not defs:
            print("  (aucune définition trouvée : méthode héritée, nom mal tapé, ou fonction d'une bibliothèque)")
        for g in ("appel", "référence", "chaîne"):
            for t in (x for x in les if x["genre"] == g):
                print(f"  {g:9} {t['fichier']}:{t['ligne']}  dans {t['dans']}  {t['detail'] if g != 'chaîne' else ''}"
                      f"{t['nom'] if g != 'chaîne' else repr(t['nom'])}")
        print()
    for i in illisibles:
        print(f"  ILLISIBLE {i}", file=sys.stderr)
    return 1 if illisibles else 0


if __name__ == "__main__":
    sys.exit(main())
