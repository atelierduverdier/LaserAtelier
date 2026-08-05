# -*- coding: utf-8 -*-
"""Les sept générateurs que personne n'éprouvait.

Christophe, 05/08/2026, en route vers une v3 stable : « refais une recherche
de bug dans le programme ». Un balayage a compté 26 générateurs dans
`laser_core` et cherché leur nom dans les tests : SEPT n'y figuraient nulle
part -- dont `filled_engraving`, `flat_multipass` et `curved_cut`,
c'est-à-dire les modes qui COUPENT VRAIMENT DU BOIS.

Ce fichier ne teste pas leur géométrie -- chacun mériterait la sienne. Il
tient les invariants qui, s'ils tombent, se paient sur la machine :

  * le programme se termine par M2, sinon LinuxCNC attend indéfiniment ;
  * aucun commentaire non fermé, sinon le fichier est REFUSÉ au chargement
    (« Unclosed comment found ») et le job ne démarre jamais ;
  * aucun octet non-ASCII, que l'interpréteur refuse aussi ;
  * aucun G4 faisceau allumé -- le HAL ramène la puissance à zéro à
    l'arrêt, donc un dwell ne grave RIEN et la planche sort blanche.

Un générateur muet est un générateur dont personne ne saura dire, le jour
où il casse, depuis quand il est cassé.
"""
import re

from harness import preparer

h = preparer()
core = h.core

import FreeCAD                                                 # noqa: E402
import Part                                                    # noqa: E402


def _carre(cote=20.0, z=0.0):
    """Un contour fermé simple, suffisant pour tout générateur de trait."""
    p = [FreeCAD.Vector(0, 0, z), FreeCAD.Vector(cote, 0, z),
         FreeCAD.Vector(cote, cote, z), FreeCAD.Vector(0, cote, z),
         FreeCAD.Vector(0, 0, z)]
    return Part.makePolygon(p).Edges


def _verifier(nom, gcode):
    assert gcode, "{} n'a produit aucun G-code".format(nom)
    lignes = [l for l in gcode.splitlines() if l.strip()]
    assert lignes[-1].strip() == "M2", (
        "{} ne finit pas par M2 : LinuxCNC attendrait la fin du programme "
        "indéfiniment".format(nom), lignes[-1])
    for i, l in enumerate(lignes, 1):
        assert l.count("(") == l.count(")"), (
            "{} ligne {} : commentaire non fermé -- LinuxCNC REFUSE le "
            "programme entier au chargement".format(nom, i), l)
        try:
            l.encode("ascii")
        except UnicodeEncodeError:
            raise AssertionError(
                "{} ligne {} : octet non-ASCII, refusé par "
                "l'interpréteur".format(nom, i))
    # Un G4 n'a le droit d'exister qu'à l'armement, faisceau à zéro.
    puissance = 0.0
    for l in lignes:
        m = re.match(r"(?:M67 E\d+ Q|S)([\d.]+)", l.strip())
        if m:
            puissance = float(m.group(1))
        if l.strip().startswith("G4") and puissance > 0:
            raise AssertionError(
                "{} : G4 avec le faisceau à S{:.0f} -- au repos le HAL "
                "ramène la puissance à zéro, ce dwell ne graverait "
                "RIEN".format(nom, puissance))
    return len(lignes)


_edges = _carre()
_cas = [
    ("catalogue", lambda: core.generate_gcode_catalogue(
        400.0, 1000.0, 5.0, quiet=True)),
    ("style_sampler", lambda: core.generate_gcode_style_sampler(
        400.0, 1000.0, 5.0, quiet=True)),
    ("style_showcase", lambda: core.generate_gcode_style_showcase(
        400.0, 1000.0, 5.0, quiet=True)),
    ("offset_test", lambda: core.generate_gcode_offset_test(quiet=True)),
    ("flat_multipass", lambda: core.generate_gcode_flat_multipass(
        _edges, 900.0, 400.0, 4.0, 3, quiet=True)),
    ("curved_cut", lambda: core.generate_gcode_curved_cut(
        _edges, 900.0, 400.0, 4.0, 3, 5.0, 5.0, quiet=True)),
    ("filled_engraving", lambda: core.generate_gcode_filled_engraving(
        _carre(18.0), _edges, 5.0, 0.0, 700.0, 800.0, quiet=True)),
]

_total = 0
for _nom, _appel in _cas:
    _g = _appel()
    _n = _verifier(_nom, _g)
    _total += _n
    print("   {:<18} {:5d} lignes OK".format(_nom, _n))

assert _total > 200, ("les sept générateurs rendent trop peu : le contrôle "
                      "vise sans doute à côté", _total)

# LE CONTRÔLE DOIT POUVOIR ÉCHOUER. Sans cette preuve, sept « OK » ne
# valent rien -- c'est la leçon des trois hasattr survivants d'une règle qui
# se disait appliquée.
try:
    _verifier("sabotage", "G21\nG90\n(commentaire non ferme\nM2\n")
except AssertionError as _exc:
    assert "non fermé" in str(_exc), _exc
else:
    raise AssertionError("un commentaire non fermé passe le contrôle")
try:
    _verifier("sabotage", "G21\nM67 E0 Q500\nG4 P0.5\nM2\n")
except AssertionError as _exc:
    assert "graverait" in str(_exc) or "G4" in str(_exc), _exc
else:
    raise AssertionError("un G4 faisceau allumé passe le contrôle")
try:
    _verifier("sabotage", "G21\nG90\nM30\n")
except AssertionError:
    pass
else:
    raise AssertionError("un programme sans M2 passe le contrôle")

print("les {} générateurs jamais éprouvés le sont : M2, commentaires fermés, "
      "ASCII, aucun G4 allumé -- et les trois sabotages échouent bien OK"
      .format(len(_cas)))
