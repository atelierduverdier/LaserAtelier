# -*- coding: utf-8 -*-
"""Aperçu du job combiné : la teinte vient du nuancier MESURÉ.

Christophe, 04/08/2026 : « j'ai un souci d'aperçu dans job combiné, on
dirait que ça ne prend pas mes valeurs [...] c'est pas du tout un ton clair
mais bien noir que l'on voit ».

`_strokes_from_operation` appelait `_tone_burn` -- le modèle THÉORIQUE --
dans ses cinq branches, alors que les aperçus des modes simples passent tous
par `_teinte_gravure` (mesuré d'abord, théorie en repli). Le matériau
voyageait pourtant déjà jusque-là : il ne servait qu'à la LARGEUR.

CE QUI A CACHÉ LE DÉFAUT SI LONGTEMPS : sur les tons FONCÉS les deux
formules s'accordent à quelques points près (S900/F200 : 94 % mesuré contre
100 % prédit). L'écart n'existe que dans les CLAIRS -- MDF à S400/F2000,
5 % mesuré contre 93 % prédit, quatre-vingt-huit points. Un aperçu qui ne
ment que sur la moitié claire de l'échelle passe pour juste.
"""
import sys

from harness import preparer

h = preparer()
core = h.core
tp = h.tp
import FreeCAD                                            # noqa: E402
import Part                                               # noqa: E402


# --- 1. Il FAUT un cas où les deux formules divergent ------------------
# Sans cela le contrôle ne prouverait rien : sur un ton foncé, mesuré et
# théorique donnent la même chose et n'importe quel code passerait.
_CAS = None
for _mat in core.burn_width_materials():
    for _S, _F, _dz in ((400, 2000, 0.0), (300, 1500, 15.0), (200, 2000, 15.0)):
        _m = tp._tone_measured(_mat, _S, _F, _dz)
        if _m is None or _m > 0.25:
            continue
        _w = core.burn_width_defocus_scaled(_S, _F, _dz, _mat) or core.SPOT_FOCUS_MM
        _t = tp._tone_burn(_S, _F, _w)
        if _t - _m > 0.30:
            _CAS = (_mat, _S, _F, _dz, _m, _t, _w)
            break
    if _CAS:
        break
assert _CAS, ("aucun réglage clair où mesuré et théorique divergent dans "
              "cette config : le contrôle ne pourrait rien discriminer")
_mat, _S, _F, _dz, _mes, _theo, _w = _CAS
print("1. cas discriminant : {} à S{} F{} défocus {:.0f} -- mesuré {:.0f} %, "
      "théorique {:.0f} % ({:+.0f} points) OK".format(
          _mat, _S, _F, _dz, 100 * _mes, 100 * _theo, 100 * (_theo - _mes)))


# --- 2. L'aperçu combiné peint la teinte MESURÉE -----------------------
_doc = FreeCAD.newDocument("EssaiApercuCombine")
try:
    _arete = Part.LineSegment(FreeCAD.Vector(0, 0, 0),
                              FreeCAD.Vector(50, 0, 0)).toShape()
    _op = {
        "type": "filled",
        "label": "essai clair",
        "materiau": _mat,
        "params": {
            "fill_edges": [_arete], "contour_edges": [],
            "draw_contour": False,
            "fill_power": _S, "fill_feed": _F, "defocus": _dz,
        },
    }
    _tr = tp._strokes_from_operation(_op)
    assert _tr, "aucun trait produit par l'aperçu"
    _teintes = [t for _pts, _w2, t in _tr]
    _peint = sum(_teintes) / len(_teintes)
    assert abs(_peint - _mes) < 0.05, (
        "l'aperçu peint {:.0f} % là où le nuancier mesure {:.0f} % : il "
        "utilise le modèle théorique, pas les mesures".format(
            100 * _peint, 100 * _mes), _peint, _mes)
    assert _peint < _theo - 0.25, (
        "la teinte peinte reste celle du modèle théorique", _peint, _theo)

    # (b) SANS MATÉRIAU, on retombe sur la théorie -- et on ne plante pas.
    _op_sans = dict(_op)
    _op_sans.pop("materiau")
    _tr2 = tp._strokes_from_operation(_op_sans)
    assert _tr2, "l'aperçu sans matériau ne produit plus rien"
    _p2 = sum(t for _p, _w2, t in _tr2) / len(_tr2)
    assert _p2 > _peint + 0.20, (
        "sans matériau la teinte devrait retomber sur le modèle théorique",
        _p2, _peint)

    # (c) UN TON FONCÉ ne doit PAS bouger : la correction ne déplace que
    #     les clairs, sinon elle casserait ce qui marchait.
    _fonce = dict(_op)
    _fonce["params"] = dict(_op["params"])
    _fonce["params"].update({"fill_power": 900, "fill_feed": 200,
                             "defocus": 15.0})
    _tf = tp._strokes_from_operation(_fonce)
    _pf = sum(t for _p, _w2, t in _tf) / len(_tf)
    assert _pf > 0.80, ("un ton foncé n'est plus peint foncé", _pf)
    print("2. filled : peint {:.0f} % (mesuré {:.0f} %) au lieu de {:.0f} % ; "
          "sans matériau {:.0f} % ; le foncé reste à {:.0f} % OK".format(
              100 * _peint, 100 * _mes, 100 * _theo, 100 * _p2, 100 * _pf))

    # --- 3. Le marquage aussi -------------------------------------------
    # La même branche `curved` peignait ses dégradés à la théorie : un
    # dégradé de LARGEUR est aussi un dégradé de NOIRCEUR, le nuancier
    # étant mesuré par niveau de défocus.
    _opc = {
        "type": "curved", "label": "marquage clair", "materiau": _mat,
        "params": {"edges": [_arete], "power": _S, "feed": _F,
                   "z_focus": core.Z_WORK_MM + _dz, "style": "plein"},
    }
    _trc = tp._strokes_from_operation(_opc)
    assert _trc, "aucun trait pour le marquage"
    _pc = sum(t for _p, _w2, t in _trc) / len(_trc)
    assert abs(_pc - _mes) < 0.05, (
        "le marquage est peint {:.0f} % au lieu des {:.0f} % mesurés".format(
            100 * _pc, 100 * _mes))
    print("3. curved : peint {:.0f} % pour {:.0f} % mesurés OK".format(
        100 * _pc, 100 * _mes))
finally:
    FreeCAD.closeDocument("EssaiApercuCombine")
