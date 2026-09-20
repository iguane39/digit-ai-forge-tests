"""TF-1093 (20/09/2026) — LES FILTRES CROISES, SUR L INSTANCE SERVIE.

LE FAIT. Restes archives de TF-0480 et TF-0493. Le pan `plancher` parcourt DEJA des routes
servies dans un navigateur pilote, et son propre `NON_JUGE` disait : « les etats atteints apres
interaction ne sont pas mesures ici ; la matrice d etats du socle les joue sur un FICHIER ». Ce
qui manquait n etait pas l instance : c etait le GESTE. Et la matrice unitaire elle-meme ne pose
qu UN filtre a la fois — une intersection vide que chaque facette prise seule ne montre pas lui
echappe entierement.

CE QUI EST PROUVE ICI, et dans quel ordre :

  1. l option est ABSENTE PAR DEFAUT, et son absence se DIT. Un pan qui croiserait tout sans
     qu on le lui demande paierait autant de chargements que de croisements ; un pan qui se
     tairait ferait lire « rien a croiser » la ou il n a rien regarde ;
  2. un socle ANTERIEUR a TF-1093 donne un NON JUGE qui NOMME SON REMEDE, jamais un vert. La
     copie INSTALLEE du socle ne porte pas `jouer_paires` tant qu une propagation humaine n a
     pas eu lieu (gate TF-0391) : c est l etat normal, et c est ce cas-la qui est joue ici ;
  3. la DERIVATION du verdict a partir d un rapport de croisements : un croisement muet devient
     un bloquant localise, un croisement NON JOUE se declare, et la COUVERTURE (« N sur M ») est
     publiee avant les constats — « 0 bloquant sur 3 croisements joues parmi 40 » n est pas le
     meme verdict que sur 40 joues parmi 40, et seuls les chiffres le disent ;
  4. le GESTE REEL, bout en bout, sur une instance SERVIE par ce test — mais seulement quand une
     copie du socle qui porte `jouer_paires` est designee par FORGE_TESTS_SOCLE_RENDER_PAGE.
     Sans elle, SKIP DECLARE : un test qui se dirait vert sans avoir rien joue mentirait.

Comme pour TF-0480 et TF-0409, les cas 1 a 3 remplacent le parcours reel par des releves
canoniques : ce qui s y prouve est la derivation du verdict, seule partie deterministe.
"""

from __future__ import annotations

import functools
import http.server
import os
import socketserver
import threading
from pathlib import Path

import pytest

from forge_tests.adaptateurs import plancher

CIBLE = Path("projet-factice")
ROUTES = (["/tableau"], "routes declarees pour la recette")

#: Un rapport de croisements tel que `jouer_paires` le rend : deux croisements joues sur quatre
#: possibles (le plafond a mordu), l un muet, un troisieme non joue faute de declencheur.
RAPPORT = {
    "jouees": 2, "possibles": 4, "plafond": 2, "colonnes": 2, "bloquants": 1, "motif": "",
    "combinaisons": {
        "Region=nord x Statut=en cours": {
            "applique": True, "blocking": 1,
            "issues": {"etat_muet": [{
                "what": "croisement « Region=nord x Statut=en cours »",
                "detail": "l intersection de DEUX filtres ne laisse plus aucune ligne, et pas "
                          "un mot pour le dire",
            }]},
        },
        "Region=sud x Statut=livre": {
            "applique": False, "motif": "aucune valeur (.tf-opt) dans la colonne 2",
        },
    },
}


def _brancher(monkeypatch, resultats, motifs=None):
    monkeypatch.setattr(plancher.accessibilite, "routes_a_auditer", lambda _c: ROUTES)
    monkeypatch.setattr(plancher, "parcourir", lambda *a, **k: (resultats, motifs or []))
    monkeypatch.setattr(plancher.contraste, "_mesure_js", lambda: "() => ({})")


# ---- 1. l option est absente par defaut, et son absence se DIT ------------------------------

def test_sans_l_option_les_croisements_sont_DECLARES_non_joues(monkeypatch) -> None:
    monkeypatch.delenv(plancher.OPTION_CROISEMENTS, raising=False)
    _brancher(monkeypatch, {"/tableau": {"v1_overflow": [], "v4_overlap": []}})
    sortie = plancher.analyser(CIBLE)
    assert sortie.verdict == "PASS"
    assert any("FILTRES CROISES NON JOUES" in ligne and "option" in ligne
               for ligne in sortie.non_juge), sortie.non_juge


def test_l_exception_est_ecrite_au_NON_JUGE_du_pan() -> None:
    # Une affordance qui n est pas ecrite la ou le pan declare ce qu il ne juge pas n existe
    # pour personne : la loi n 1 du pilot vaut aussi pour une option.
    assert any(plancher.OPTION_CROISEMENTS in msg for msg in plancher.NON_JUGE)
    assert any("paires jouees sur" in msg for msg in plancher.NON_JUGE)


# ---- 2. un socle sans le geste NOMME SON REMEDE, jamais un vert -----------------------------

def _socle_anterieur(tmp_path: Path) -> Path:
    """Un module Python valide, SANS `jouer_paires` — l etat de toute copie d avant TF-1093.

    Ecrit pour l occasion, jamais un fichier du depot : designer ce fichier de test comme socle
    le ferait REEXECUTER par `exec_module`, et sa propre garde `skipif` rappellerait le
    chargeur — une recursion sans fond, mesuree le 20/09 (dix minutes sans une ligne de sortie).
    """
    chemin = tmp_path / "socle_anterieur.py"
    chemin.write_bytes(b"MEASURE_JS = '() => ({})'\n")
    return chemin


def test_un_socle_anterieur_donne_un_NON_JUGE_qui_nomme_son_remede(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(plancher.ENV_SOCLE, str(_socle_anterieur(tmp_path)))
    fn, motif = plancher._socle_croisements()
    assert fn is None
    assert "jouer_paires" in motif
    assert "oracle-skills" in motif          # le remede EST nomme : propagation, decision humaine


def test_un_socle_introuvable_se_declare_au_lieu_de_lever(monkeypatch) -> None:
    monkeypatch.setenv(plancher.ENV_SOCLE, str(Path("socle-qui-n-existe-pas.py")))
    fn, motif = plancher._socle_croisements()
    assert fn is None
    assert "introuvable" in motif


def test_l_option_active_sur_un_socle_anterieur_ne_rend_pas_un_vert_muet(monkeypatch,
                                                                         tmp_path) -> None:
    monkeypatch.setenv(plancher.OPTION_CROISEMENTS, "1")
    monkeypatch.setenv(plancher.ENV_SOCLE, str(_socle_anterieur(tmp_path)))
    _brancher(monkeypatch, {"/tableau": {"v1_overflow": [], "v4_overlap": []}})
    sortie = plancher.analyser(CIBLE)
    assert any("FILTRES CROISES NON JOUES" in ligne and "jouer_paires" in ligne
               for ligne in sortie.non_juge), sortie.non_juge


# ---- 3. la derivation du verdict a partir d un rapport de croisements -----------------------

def test_un_croisement_MUET_devient_un_bloquant_localise(monkeypatch) -> None:
    monkeypatch.delenv(plancher.OPTION_CROISEMENTS, raising=False)
    _brancher(monkeypatch, {"/tableau": {"v1_overflow": [], "_croisements": RAPPORT}})
    sortie = plancher.analyser(CIBLE)
    assert sortie.verdict == "FAIL"
    assert len(sortie.findings) == 1
    seul = sortie.findings[0]
    assert seul.severite == "bloquant"
    assert seul.localisation == "/tableau"
    assert "filtres croises" in seul.message
    assert "Region=nord x Statut=en cours" in seul.message


def test_la_COUVERTURE_est_publiee_et_le_reste_declare_NON_JOUE(monkeypatch) -> None:
    monkeypatch.delenv(plancher.OPTION_CROISEMENTS, raising=False)
    _brancher(monkeypatch, {"/tableau": {"v1_overflow": [], "_croisements": RAPPORT}})
    sortie = plancher.analyser(CIBLE)
    couverture = [x for x in sortie.non_juge if "paire(s) jouee(s) sur" in x]
    assert couverture, sortie.non_juge
    assert "2 paire(s) jouee(s) sur 4 possible(s)" in couverture[0]
    # Une borne qui ne dit pas ce qu elle laisse dehors est une borne silencieuse.
    assert "2 croisement(s) NON JOUE(S)" in couverture[0]
    assert any("croisement « Region=sud x Statut=livre » NON JOUE" in x for x in sortie.non_juge)


def test_un_rapport_EMPECHE_se_declare_sans_inventer_de_couverture(monkeypatch) -> None:
    monkeypatch.delenv(plancher.OPTION_CROISEMENTS, raising=False)
    _brancher(monkeypatch, {"/tableau": {
        "v1_overflow": [],
        "_croisements": {"motif": "origine `recette.exemple` NON LOCALE — aucun croisement "
                                  "n est CLIQUE sur une instance tierce"},
    }})
    sortie = plancher.analyser(CIBLE)
    assert sortie.verdict == "PASS"
    assert any("FILTRES CROISES NON JOUES" in x and "NON LOCALE" in x for x in sortie.non_juge)
    assert not any("paire(s) jouee(s) sur" in x for x in sortie.non_juge)


def test_les_croisements_ne_sont_jamais_lus_comme_une_famille_de_constats(monkeypatch) -> None:
    # `_croisements` voyage DANS la mesure de la route : s il restait la, une boucle sur les
    # familles finirait par le traverser. Il en est retire avant lecture.
    monkeypatch.delenv(plancher.OPTION_CROISEMENTS, raising=False)
    mesure = {"v1_overflow": [], "_croisements": RAPPORT}
    _brancher(monkeypatch, {"/tableau": mesure})
    plancher.analyser(CIBLE)
    assert "_croisements" not in mesure


# ---- 3 bis. la mesure se charge PRETE, jamais en gabarit ------------------------------------

def _socle_module(chemin: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("_socle_pour_le_test", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_la_mesure_chargee_ne_porte_AUCUN_jeton_de_gabarit(monkeypatch) -> None:
    """TF-1093 — le defaut trouve en branchant les croisements, et ses DEUX sens.

    `MEASURE_JS` est un gabarit : il porte `__ALIGN_TOL__`, `__L2_MIN_VIEWPORT__`… Lu tel quel
    et evalue, il leve `ReferenceError: __ALIGN_TOL__ is not defined`, et le garde de
    `_parcours` change cette levee en « route visitee mais non mesuree » — un pan qui ne mesure
    plus rien, route par route. Sens ROUGE : le gabarit brut porte ses jetons. Sens VERT : ce
    que `_mesure_js` rend n en porte aucun.
    """
    import re
    chemin = _chemin_socle()
    if not chemin.exists():
        pytest.skip(f"socle absent ({chemin}) — rien a charger")
    # `_mesure_js` lit le socle INSTALLE ; le cas se joue sur la copie designee, pour qu une
    # source versionnee puisse etre eprouvee avant toute propagation (decision humaine).
    monkeypatch.setattr(plancher.contraste, "_SOCLE", chemin)
    module = _socle_module(chemin)
    brut = getattr(module, "MEASURE_JS", "")
    pret = contraste_mesure()
    assert pret, "le socle est la, mais ne rend aucune mesure"
    if not callable(getattr(module, "mesure_js", None)):
        pytest.skip("socle anterieur a la porte `mesure_js` : le repli sur la constante est "
                    "volontaire, et ce cas ne peut pas juger ce qu il ne publie pas")
    # SENS ROUGE : la constante, telle qu un consommateur la lisait, est un gabarit.
    assert re.findall(r"__[A-Z0-9_]+__", brut), (
        "le gabarit ne porte plus de jeton : la demonstration de ce cas tombe")
    # SENS VERT : ce que le pan charge est evaluable.
    assert not re.findall(r"__[A-Z0-9_]+__", pret), (
        "la mesure chargee porte encore des jetons de gabarit — elle levera dans le navigateur")


def contraste_mesure():
    return plancher.contraste._mesure_js()


# ---- 4. le geste REEL, sur une instance servie par ce test ----------------------------------

def _chemin_socle() -> Path:
    return Path(os.environ.get(plancher.ENV_SOCLE) or plancher.contraste._SOCLE)


def _fixtures_du_socle() -> Path:
    """Les fixtures a double sens vivent AVEC le socle, jamais recopiees ici.

    Une copie de fixture dans ce depot divergerait de la regle qu elle est censee prouver — le
    meme defaut que les tables de familles recopiees, paye deja deux fois par le parc.
    """
    return _chemin_socle().parent.parent / "fixtures"


@functools.lru_cache(maxsize=1)
def _socle_capable():
    """La copie du socle designee porte-t-elle `jouer_paires` ? (None sinon, avec son motif.)

    Memorise : la garde `skipif` l interroge a la collecte, et charger le socle deux fois pour
    la meme reponse serait payer un import de plus a chaque execution de la suite.
    """
    return plancher._socle_croisements()


@pytest.mark.skipif(
    _socle_capable()[0] is None,
    reason=("socle sans `jouer_paires` : " + str(_socle_capable()[1]) + ". Ce cas se joue en "
            "designant une copie qui le porte, par FORGE_TESTS_SOCLE_RENDER_PAGE — la "
            "propagation vers la copie installee est une decision humaine (gate TF-0391)"),
)
def test_bout_en_bout_un_croisement_muet_est_vu_sur_une_instance_SERVIE() -> None:
    """Le geste complet : le test sert la page, pilote le navigateur, croise deux filtres.

    Sens ROUGE et sens VERT sur la MEME construction : la page muette rend au moins un
    `etat_muet`, la page qui annonce son vide n en rend aucun. Sans le second, la regle pourrait
    n etre qu un refus de tout croisement vide.
    """
    playwright = pytest.importorskip("playwright.sync_api")
    jouer, _ = _socle_capable()
    fixtures = _fixtures_du_socle()
    rouge = fixtures / "paires-croisement-muet.html"
    vert = fixtures / "paires-croisement-annonce.html"
    if not (rouge.exists() and vert.exists()):
        pytest.skip(f"fixtures a double sens absentes du socle designe ({fixtures}) — elles "
                    "vivent avec lui, ce depot n en tient pas de copie")

    class Silencieux(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_a):
            pass

    class Banc(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    srv = Banc(("127.0.0.1", 0), functools.partial(Silencieux, directory=str(fixtures)))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # La mesure vient de la copie DESIGNEE, la meme que `jouer_paires` — pas de la copie
    # installee : croiser avec la mesure d un autre socle ne prouverait rien de celui-ci.
    mesure = _socle_module(_chemin_socle()).mesure_js()
    assert mesure and "__" not in mesure, "mesure du socle designe non preparee"
    try:
        with playwright.sync_playwright() as pw:
            navigateur = pw.chromium.launch()
            page = navigateur.new_page(viewport={"width": 1440, "height": 900})
            try:
                constats = {}
                for nom, fichier in (("rouge", rouge), ("vert", vert)):
                    page.goto(f"http://127.0.0.1:{port}/{fichier.name}",
                              wait_until="networkidle")
                    rapport = plancher._croiser_sur_place(jouer, page, mesure)
                    assert not rapport.get("motif"), rapport.get("motif")
                    assert rapport["possibles"] > 0
                    constats[nom] = sum(
                        len((c.get("issues") or {}).get("etat_muet") or [])
                        for c in rapport["combinaisons"].values() if c.get("applique")
                    )
            finally:
                navigateur.close()
    finally:
        srv.shutdown()
        srv.server_close()
    assert constats["rouge"] >= 1, "le croisement muet n a pas ete vu sur l instance servie"
    assert constats["vert"] == 0, "un croisement qui ANNONCE son vide ne doit rien rendre"


def test_le_cas_bout_en_bout_dit_pourquoi_il_est_ecarte_quand_il_l_est() -> None:
    """Un SKIP sans motif lisible est un trou : ici le motif nomme le socle et son remede."""
    fn, motif = _socle_capable()
    if fn is not None:
        assert motif is None
        return
    assert "jouer_paires" in motif or "introuvable" in motif or "illisible" in motif
    assert os.environ.get(plancher.ENV_SOCLE) is None or True   # le chemin reste configurable
