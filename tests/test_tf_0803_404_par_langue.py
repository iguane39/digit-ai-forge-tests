"""TF-0803 — la 404 personnalisee par langue est JUGEABLE partout, pas seulement la ou on y pense.

Candidature du pilot (lot `digit-ai-factory - RETOURS - 20260905a`, RT-1, classe
`surface-implicite-non-livree`). Le patron P-2 pose cinq exigences mesurables et le controle M-9
de la MEP les juge SUR PREUVE — la sortie d un controle executable. Sans controle generique,
chaque produit reecrit le sien, ou n en a pas : le fait fondateur est un site multilingue qui a
servi le 404 nu de son serveur de fichiers en production du 25/08 au 01/09/2026, vu par
l exploitant et par aucun controle.

DEUX ETAGES, et la separation est deliberee :

  1. le JUGEMENT est une fonction pure — elle n exige ni reseau, ni serveur, ni environnement, et
     c est celle dont un defaut passerait inapercu ;
  2. le SONDAGE est eprouve bout en bout contre des serveurs HTTP LOCAUX de fixture, montes ici
     meme sur un port libre : un serveur conforme, et cinq serveurs qui portent chacun UN des
     refus. Aucun site reel, aucune API, aucun appel sortant — 127.0.0.1 et rien d autre.

Le double sens est le contrat de la forge (TF-0679) : un controle qu on ne voit jamais refuser ne
controle rien. Chaque refus prononcable de la recette a donc ici son serveur qui le declenche.
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "recette"))

import quatre_cent_quatre as recette  # noqa: E402

MENU = (
    '<nav><a href="/fr/">Accueil</a><a href="/fr/tarifs">Tarifs</a>'
    '<a href="/fr/contact">Contact</a></nav>'
)


def _page(lang: str, titre: str, noindex: bool = False, menu: str = MENU) -> bytes:
    robots = '<meta name="robots" content="noindex, follow">' if noindex else ""
    return (f'<!doctype html><html lang="{lang}"><head><title>{titre}</title>{robots}</head>'
            f"<body>{menu}<main>{titre}</main></body></html>").encode()


#: Les pages REELLEMENT servies par les serveurs de fixture — la reference du « meme gabarit ».
PAGES = {
    "/": _page("fr", "Accueil"),
    "/fr/": _page("fr", "Accueil"),
    "/en/": _page("en", "Home", menu=MENU.replace("/fr/", "/en/")),
}
SITEMAP_SAIN = (b'<?xml version="1.0"?><urlset><loc>http://HOTE/fr/</loc>'
                b"<loc>http://HOTE/en/</loc></urlset>")
NU = b"The requested path could not be found"


class _Poignee(http.server.BaseHTTPRequestHandler):
    """Le serveur de fixture. `mode` porte le defaut que ce serveur existe pour declencher."""

    mode = "conforme"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - signature imposee
        return

    def _envoyer(self, code: int, corps: bytes, type_contenu: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self) -> None:  # noqa: N802 - nom impose par la bibliotheque standard
        chemin = self.path.split("?")[0]
        if chemin == "/sitemap.xml":
            corps = SITEMAP_SAIN
            if self.mode == "sitemap-fautif":
                corps = corps.replace(b"</urlset>",
                                      b"<loc>http://HOTE/fr/sonde-404-forge-tests</loc></urlset>")
            self._envoyer(200, corps, "application/xml")
            return
        if chemin in PAGES:
            self._envoyer(200, PAGES[chemin], "text/html; charset=utf-8")
            return

        if self.mode == "pendue":
            # Le piege MESURE de la realisation de reference : les en-tetes sont differes et le
            # client attend. Cote recette, c est un code 000, pas un 404 poli.
            time.sleep(3)
            self._envoyer(404, NU, "text/plain")
            return

        prefixe = chemin.strip("/").split("/")[0]
        lang = prefixe if prefixe in ("fr", "en") else "fr"
        non_html = chemin.rsplit("/", 1)[-1].endswith((".png", ".js", ".css"))

        if self.mode == "nu":  # le defaut fondateur : page blanche, sans menu ni langue
            self._envoyer(404, NU, "text/plain")
            return
        if self.mode == "soft-200":
            self._envoyer(200, _page(lang, "Introuvable", noindex=True), "text/html; charset=utf-8")
            return
        if non_html and self.mode != "html-partout":
            self._envoyer(404, NU, "text/plain")
            return

        menu = "" if self.mode == "sans-menu" else MENU.replace("/fr/", f"/{lang}/")
        langue_servie = "fr" if self.mode == "mauvaise-langue" else lang
        page = _page(langue_servie, "Introuvable", noindex=self.mode != "sans-noindex", menu=menu)
        self._envoyer(404, page, "text/html; charset=utf-8")


def _servir(mode: str) -> Iterator[str]:
    poignee = type("Poignee", (_Poignee,), {"mode": mode})
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), poignee) as serveur:
        serveur.daemon_threads = True
        fil = threading.Thread(target=serveur.serve_forever, daemon=True)
        fil.start()
        try:
            yield f"http://127.0.0.1:{serveur.server_address[1]}"
        finally:
            serveur.shutdown()
            fil.join(timeout=5)


@pytest.fixture
def serveur(request: pytest.FixtureRequest) -> Iterator[str]:
    yield from _servir(getattr(request, "param", "conforme"))


# ============================================================================================
# 1. Le JUGEMENT — fonction pure, sans reseau
# ============================================================================================
def _reponse(code: int = 404, corps: str = "", entetes: dict | None = None,
             **extra: object) -> dict:
    return {"url": "http://exemple/fr/inconnu", "code": code, "corps": corps,
            "entetes": entetes or {"content-type": "text/html; charset=utf-8"}, **extra}


def _corps_404(lang: str = "fr", menu: str = MENU, noindex: bool = True) -> str:
    return _page(lang, "Introuvable", noindex=noindex, menu=menu).decode()


def test_le_cas_nominal_est_tenu() -> None:
    verdict = recette.juger_adresse_inconnue(
        _reponse(corps=_corps_404()), "fr", "fr", recette.liens_de_menu(MENU), None, None)
    assert verdict["verdict"] == "PASS"
    assert verdict["langue"] == "fr"


def test_un_200_sur_une_adresse_inconnue_est_REFUSE() -> None:
    """ROUGE, et c est le refus que la candidature exige nommement : un soft-404 est indexable,
    et rien dans une page rendue en 200 ne dit au moteur que l adresse n existe pas."""
    verdict = recette.juger_adresse_inconnue(
        _reponse(code=200, corps=_corps_404()), "fr", "fr", recette.liens_de_menu(MENU), None, None)
    assert verdict["verdict"] == "FAIL"
    assert "soft-404" in verdict["motif"]


def test_une_reponse_PENDUE_nomme_le_piege_du_patron() -> None:
    """ROUGE. Le code 000 est le piege MESURE de la realisation de reference : envelopper
    `writeHead` sans envelopper `write()`. Sans ce motif, il se lit comme un incident reseau et
    la cause reelle se cherche dans l infrastructure au lieu du code."""
    verdict = recette.juger_adresse_inconnue(
        _reponse(code=0, pendue=True), "fr", "fr", None, None, None)
    assert verdict["verdict"] == "FAIL"
    assert "PENDUE" in verdict["motif"]
    assert "write()" in verdict["motif"]


def test_un_404_NU_sur_une_adresse_de_page_est_le_defaut_fondateur() -> None:
    """ROUGE : c est exactement ce qui a ete servi en production du 25/08 au 01/09/2026."""
    verdict = recette.juger_adresse_inconnue(
        _reponse(corps="The requested path could not be found",
                 entetes={"content-type": "text/plain"}), "fr", "fr", None, None, None)
    assert verdict["verdict"] == "FAIL"
    assert "menu" in verdict["motif"]


def test_la_langue_se_choisit_au_prefixe_du_chemin() -> None:
    """ROUGE : une 404 unique servie en francais sous `/en/` est une page du bon gabarit dans la
    mauvaise langue — le defaut que sept 404 identiques produiraient sans qu un statut le dise."""
    verdict = recette.juger_adresse_inconnue(
        _reponse(corps=_corps_404(lang="fr")), "en", "en", recette.liens_de_menu(MENU), None, None)
    assert verdict["verdict"] == "FAIL"
    assert "prefixe" in verdict["motif"]


def test_une_variante_regionale_de_la_langue_attendue_est_acceptee() -> None:
    """Borne : `fr-FR` sous `/fr/` est la bonne langue, et refuser la refuserait a raison nulle."""
    verdict = recette.juger_adresse_inconnue(
        _reponse(corps=_corps_404(lang="fr-FR")), "fr", "fr",
        recette.liens_de_menu(MENU), None, None)
    assert verdict["verdict"] == "PASS"


def test_un_menu_incomplet_dit_QUELS_liens_manquent() -> None:
    """ROUGE. « Pas du meme gabarit » sans la liste des liens absents laisse le produit chercher."""
    ampute = MENU.replace('<a href="/fr/contact">Contact</a>', "")
    verdict = recette.juger_adresse_inconnue(
        _reponse(corps=_corps_404(menu=ampute)), "fr", "fr",
        recette.liens_de_menu(MENU), None, None)
    assert verdict["verdict"] == "FAIL"
    assert verdict["liens_de_menu_manquants"] == ["/fr/contact"]


def test_sans_nav_de_reference_le_meme_gabarit_est_NON_MESURABLE_jamais_PASS() -> None:
    """Le piege exact du contrat double sens : un site sans `<nav>` n a pas de reference, et
    declarer PASS faute de pouvoir comparer serait un vert obtenu par absence de mesure."""
    verdict = recette.juger_adresse_inconnue(
        _reponse(corps=_corps_404(menu="")), "fr", "fr", None, None, {"url": "http://exemple/fr/"})
    assert verdict["verdict"] == "NON_MESURABLE"
    assert "--marqueur-menu" in verdict["motif"]


def test_un_marqueur_declare_remplace_la_comparaison_de_menu() -> None:
    corps = _corps_404(menu="<header>bandeau maison</header>")
    assert recette.juger_adresse_inconnue(
        _reponse(corps=corps), "fr", "fr", None, "bandeau maison", None)["verdict"] == "PASS"
    absent = recette.juger_adresse_inconnue(
        _reponse(corps=_corps_404(menu="")), "fr", "fr", None, "bandeau maison", None)
    assert absent["verdict"] == "FAIL"


def test_une_404_sans_noindex_est_refusee() -> None:
    """ROUGE : une page d erreur sans `noindex` entre en index — exigence 3 du patron P-2."""
    assert recette.juger_noindex(
        _reponse(corps=_corps_404(noindex=False)), "fr")["verdict"] == "FAIL"


def test_le_noindex_vaut_par_la_meta_OU_par_l_entete() -> None:
    """Borne : refuser un `X-Robots-Tag: noindex` accuserait un produit qui tient l exigence."""
    par_entete = _reponse(corps=_corps_404(noindex=False),
                          entetes={"content-type": "text/html", "x-robots-tag": "noindex"})
    assert recette.juger_noindex(par_entete, "fr")["verdict"] == "PASS"
    assert recette.juger_noindex(_reponse(corps=_corps_404()), "fr")["verdict"] == "PASS"


def test_une_page_HTML_servie_a_la_place_d_un_404_nu_est_refusee() -> None:
    """ROUGE : un navigateur qui attend une image et recoit un document — le defaut se voit en
    console, jamais a l ecran, et c est pourquoi personne ne le trouve a la main."""
    verdict = recette.juger_ressource_non_html(_reponse(corps=_corps_404()), "fr")
    assert verdict["verdict"] == "FAIL"
    assert "404 nu" in verdict["motif"]


def test_un_404_nu_sur_une_ressource_non_html_est_tenu() -> None:
    nu = _reponse(corps="not found", entetes={"content-type": "text/plain"})
    assert recette.juger_ressource_non_html(nu, "fr")["verdict"] == "PASS"


def test_un_sitemap_qui_liste_une_adresse_404_est_refuse() -> None:
    """ROUGE : une page d erreur au sitemap est une invitation a l indexer."""
    xml = "<urlset><loc>https://s/fr/</loc><loc>https://s/fr/sonde-404-forge-tests</loc></urlset>"
    verdict = recette.juger_sitemap(
        {"url": "https://s/sitemap.xml", "code": 200, "corps": xml, "entetes": {}},
        ["https://s/fr/sonde-404-forge-tests"], [])
    assert verdict["verdict"] == "FAIL"
    assert verdict["adresses_listees"] == ["https://s/fr/sonde-404-forge-tests"]


def test_une_page_404_DECLAREE_est_cherchee_au_sitemap_par_son_chemin() -> None:
    xml = "<urlset><loc>https://s/fr/</loc><loc>https://s/fr/404</loc></urlset>"
    verdict = recette.juger_sitemap(
        {"url": "https://s/sitemap.xml", "code": 200, "corps": xml, "entetes": {}}, [], ["/fr/404"])
    assert verdict["verdict"] == "FAIL"


def test_un_sitemap_injoignable_est_NON_MESURABLE_jamais_PASS() -> None:
    """Une absence non lue n est pas une absence prouvee : c est le meme piege que deux campagnes
    vides qui se ressemblent — le silence ne vaut pas verdict."""
    verdict = recette.juger_sitemap(
        {"url": "https://s/sitemap.xml", "code": 404, "corps": "", "entetes": {}}, [], [])
    assert verdict["verdict"] == "NON_MESURABLE"


def test_une_mesure_partielle_n_est_PAS_un_PASS() -> None:
    """Le coeur du contrat : PASS exige que TOUS les cas aient ete joues ET tenus."""
    assert recette.synthetiser([{"verdict": "PASS"}, {"verdict": "PASS"}])["verdict"] == "PASS"
    partielle = recette.synthetiser([{"verdict": "PASS"}, {"verdict": "NON_MESURABLE"}])
    assert partielle["verdict"] == "NON_MESURABLE"
    assert recette.synthetiser([])["verdict"] == "NON_MESURABLE"
    melange = [{"verdict": "PASS"}, {"verdict": "NON_MESURABLE"}, {"verdict": "FAIL"}]
    assert recette.synthetiser(melange)["verdict"] == "FAIL"


def test_les_trois_verdicts_ont_des_codes_de_sortie_distincts() -> None:
    """0 PASS · 1 defaut mesure · 2 « je ne peux pas mesurer » — jamais deux verdicts par code."""
    assert recette.CODES == {"PASS": 0, "FAIL": 1, "NON_MESURABLE": 2}


# ============================================================================================
# 2. Le SONDAGE — bout en bout contre des serveurs locaux, un par refus
# ============================================================================================
@pytest.mark.parametrize("serveur", ["conforme"], indirect=True)
def test_bout_en_bout_un_serveur_conforme_rend_le_code_0(serveur: str) -> None:
    rapport = recette.jouer(serveur, ["fr", "en"], langue_par_defaut="fr", delai=5)
    assert rapport["verdict"] == "PASS", rapport["cas"]
    assert rapport["resume"]["fail"] == 0
    assert recette.CODES[rapport["verdict"]] == 0
    # La piece de preuve nomme le controle qu elle sert : sans cela, le dossier de MEP joint un
    # JSON dont personne ne sait a quelle ligne il repond.
    assert rapport["controle"].startswith("M-9")
    assert "TF-0803" in rapport["candidature"]
    assert rapport["non_mesure"], "les limites de la mesure se declarent, elles ne se devinent pas"


@pytest.mark.parametrize("serveur", ["nu"], indirect=True)
def test_bout_en_bout_le_404_NU_du_serveur_de_fichiers_est_attrape(serveur: str) -> None:
    """Le fait fondateur, rejoue : c est ce serveur-la qui a tenu la production sept jours."""
    rapport = recette.jouer(serveur, ["fr", "en"], delai=5)
    assert rapport["verdict"] == "FAIL"
    assert recette.CODES[rapport["verdict"]] == 1
    motifs = [c["motif"] for c in rapport["cas"] if c["cas"] == "adresse-inconnue"]
    assert len(motifs) == 2 and all("menu" in m for m in motifs)


@pytest.mark.parametrize("serveur", ["soft-200"], indirect=True)
def test_bout_en_bout_un_serveur_qui_rend_200_est_REFUSE(serveur: str) -> None:
    rapport = recette.jouer(serveur, ["fr"], delai=5)
    assert rapport["verdict"] == "FAIL"
    assert any("soft-404" in c["motif"] for c in rapport["cas"])


@pytest.mark.parametrize("serveur", ["html-partout"], indirect=True)
def test_bout_en_bout_une_image_inconnue_qui_rend_une_page_est_refusee(serveur: str) -> None:
    rapport = recette.jouer(serveur, ["fr"], delai=5)
    assert rapport["verdict"] == "FAIL"
    fautifs = [c for c in rapport["cas"] if c["cas"] == "ressource-non-html"]
    assert fautifs and all(c["verdict"] == "FAIL" for c in fautifs)
    # et le cas (a) reste tenu : le rapport isole le defaut au lieu de tout noircir
    assert all(c["verdict"] == "PASS" for c in rapport["cas"] if c["cas"] == "adresse-inconnue")


@pytest.mark.parametrize("serveur", ["sans-noindex"], indirect=True)
def test_bout_en_bout_une_404_sans_noindex_est_refusee(serveur: str) -> None:
    rapport = recette.jouer(serveur, ["fr"], delai=5)
    assert rapport["verdict"] == "FAIL"
    assert any(c["cas"] == "noindex" and c["verdict"] == "FAIL" for c in rapport["cas"])


@pytest.mark.parametrize("serveur", ["mauvaise-langue"], indirect=True)
def test_bout_en_bout_une_404_unique_pour_toutes_les_langues_est_refusee(serveur: str) -> None:
    rapport = recette.jouer(serveur, ["fr", "en"], delai=5)
    assert rapport["verdict"] == "FAIL"
    fautif = [c for c in rapport["cas"] if c["cas"] == "adresse-inconnue" and c["prefixe"] == "en"]
    assert fautif and fautif[0]["verdict"] == "FAIL"


@pytest.mark.parametrize("serveur", ["sitemap-fautif"], indirect=True)
def test_bout_en_bout_le_sitemap_qui_liste_l_adresse_sondee_est_refuse(serveur: str) -> None:
    rapport = recette.jouer(serveur, ["fr"], delai=5)
    assert rapport["verdict"] == "FAIL"
    assert any(c["cas"] == "sitemap" and c["verdict"] == "FAIL" for c in rapport["cas"])


@pytest.mark.parametrize("serveur", ["pendue"], indirect=True)
def test_bout_en_bout_une_reponse_pendue_est_un_defaut_pas_une_non_mesure(serveur: str) -> None:
    """Le piege mesure, joue pour de vrai : le serveur differe sa reponse au-dela du delai.
    Il serait tentant de classer cela « non mesurable » — c est un DEFAUT, et le code 1 le dit."""
    rapport = recette.jouer(serveur, ["fr"], sitemap=None, delai=1)
    assert rapport["verdict"] == "FAIL"
    assert any("PENDUE" in c["motif"] for c in rapport["cas"])


def test_une_instance_injoignable_rend_2_et_n_invente_aucun_verdict() -> None:
    """Aucun serveur n ecoute : la recette REFUSE de mesurer plutot que de rendre un verdict."""
    rapport = recette.jouer("http://127.0.0.1:9", ["fr"], delai=1)
    assert rapport["verdict"] == "NON_MESURABLE"
    assert recette.CODES[rapport["verdict"]] == 2
    assert rapport["cas"] == []


def test_sans_prefixe_de_langue_il_n_y_a_rien_a_sonder() -> None:
    rapport = recette.jouer("http://127.0.0.1:9", [], delai=1)
    assert rapport["verdict"] == "NON_MESURABLE"
    assert "aucun prefixe" in rapport["motif"]


@pytest.mark.parametrize("serveur", ["conforme"], indirect=True)
def test_la_piece_de_preuve_s_ecrit_sur_disque_pour_le_dossier_de_MEP(
        serveur: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """M-9 exige une PREUVE jointe au dossier de MEP : un verdict affiche puis perdu n en est pas
    une. Le fichier est la piece, et le code de sortie est le verdict."""
    import json

    cible = tmp_path / "preuve-m9.json"
    code = recette.main(["quatre_cent_quatre.py", serveur, "--prefixes", "fr,en",
                         "--sortie", str(cible)])
    capsys.readouterr()
    assert code == 0
    ecrit = json.loads(cible.read_text(encoding="utf-8"))
    assert ecrit["verdict"] == "PASS"
    assert ecrit["base"] == serveur
    assert ecrit["prefixes"] == ["fr", "en"]
