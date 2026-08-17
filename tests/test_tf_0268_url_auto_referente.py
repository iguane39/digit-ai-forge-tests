"""TF-0268 — le pan qualif voyait les URLs auto-referentes sans jamais les confronter.

Fait mesure (15/08) : 184 routes sur 184 au vert sur une instance SERVIE dont la canonique, les
sept `loc` du sitemap, le `url` du JSON-LD et `og:url` pointaient tous `http://localhost:8000` —
une valeur de developpement figee dans les gabarits. Le produit etait pret a publier, a tout
tiers qui la lit (moteur, reseau social, robot), l adresse d une machine qui n existe nulle part
ailleurs que sur le poste qui l a construite.

Pourquoi ICI et nulle part ailleurs : un test unitaire ne peut pas voir ce defaut. Un TestClient
ne sert aucune origine — il n a rien a comparer a ce que la page annonce. Seul l auditeur d une
instance SERVIE tient les DEUX termes : ce que la page dit d elle-meme, et ou elle est reellement
servie. Le pan les avait tous les deux sous les yeux ; il ne les rapprochait pas.

Regle mecanique : toute URL ABSOLUE par laquelle une page se DESIGNE (canonical, og:url, url et
@id du JSON-LD, loc de sitemap) porte l origine de l instance auditee (`FORGE_TESTS_QUALIF_URL`)
ou une origine publique DECLAREE du produit (`FORGE_TESTS_QUALIF_ORIGINES`) — sinon FAIL.

Comme la garde de precondition et le parcours d entree, le jugement se prouve SANS Chromium :
c est le releve qui decide, et un releve s ecrit.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import qualif

_BASE = "https://qualif.exemple"

_ENTETE_FIGE = """<html><head>
  <link rel="canonical" href="http://localhost:8000/factures">
  <meta property="og:url" content="http://localhost:8000/factures">
  <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"WebPage",
     "@id":"http://localhost:8000/factures","url":"http://localhost:8000/factures",
     "name":"Factures"}
  </script>
</head><body><h1>Factures</h1></body></html>"""

_ENTETE_SAIN = """<html><head>
  <link rel="canonical" href="https://qualif.exemple/factures">
  <meta property="og:url" content="https://qualif.exemple/factures">
  <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"WebPage",
     "@id":"https://qualif.exemple/factures","url":"https://qualif.exemple/factures"}
  </script>
</head><body><h1>Factures</h1></body></html>"""

_ENTETE_RELATIF = """<html><head>
  <link rel="canonical" href="/factures">
  <meta property="og:url" content="/factures">
</head><body><h1>Factures</h1></body></html>"""

_SITEMAP_FIGE = (
    "<html><body><urlset>"
    + "".join(
        f"<url><loc>http://localhost:8000/p{i}</loc></url>" for i in range(7)
    )
    + "</urlset></body></html>"
)


def _page(route: str, corps: str) -> dict:
    """Une route SAINE par ailleurs : 200, marqueur present, aucune affordance, aucune console."""
    return {
        "route": route,
        "statut": 200,
        "problemes": [],
        "affordances": [],
        "corps": corps,
        "console": [],
    }


def _config(origines: list[str] | None = None) -> dict:
    return {"base": _BASE, "marqueurs": {}, "origines": list(origines or [])}


def _findings_url(sortie) -> list:
    return [f for f in sortie.findings if f.classe == qualif.CLASSE_URL_ETRANGERE]


# --- Extraction : les quatre formes sont vues, et elles seules -------------------------------
class TestCeQuiEstLu:
    def test_les_quatre_natures_sont_relevees(self):
        natures = {nature for nature, _ in qualif.urls_auto_referentes(_ENTETE_FIGE)}

        assert natures == {"canonical", "og:url", "json-ld"}, natures

    def test_le_loc_de_sitemap_est_releve(self):
        trouvees = qualif.urls_auto_referentes(_SITEMAP_FIGE)

        assert len(trouvees) == 7, trouvees
        assert {nature for nature, _ in trouvees} == {"sitemap-loc"}

    def test_une_url_relative_ne_porte_aucune_origine_et_n_est_pas_jugee(self):
        """La forme SAINE : une page qui se nomme relativement ne peut pas mentir sur son hote."""
        assert qualif.urls_auto_referentes(_ENTETE_RELATIF) == []

    def test_un_json_ld_illisible_n_atteste_rien(self):
        corps = '<script type="application/ld+json">{ ceci n est pas du JSON</script>'

        assert qualif.urls_auto_referentes(corps) == []


# --- Jugement : le ROUGE, puis les deux formes de vert ---------------------------------------
class TestLeJugement:
    def test_une_origine_de_developpement_figee_est_un_defaut(self, tmp_path: Path):
        """LE defaut de TF-0268 : 184/184 au vert avec `http://localhost:8000` partout."""
        releve = [_page("/factures", _ENTETE_FIGE)]

        sortie = qualif.conclure(tmp_path, _config(), releve, [])

        # ROUGE avant correctif : ZERO finding, verdict PASS, 184 routes vertes.
        assert sortie.verdict == "FAIL", sortie.verdict
        assert {f.id for f in _findings_url(sortie)} == {
            "qualif:url:/factures:canonical",
            "qualif:url:/factures:og:url",
            "qualif:url:/factures:json-ld",
        }

    def test_le_message_nomme_l_origine_servie_et_l_origine_annoncee(self, tmp_path: Path):
        releve = [_page("/factures", _ENTETE_FIGE)]

        message = _findings_url(qualif.conclure(tmp_path, _config(), releve, []))[0].message

        assert _BASE in message
        assert "localhost:8000" in message
        assert "FORGE_TESTS_QUALIF_ORIGINES" in message

    def test_sept_loc_figes_font_UN_defaut_de_gabarit_pas_sept(self, tmp_path: Path):
        """RT-16 : un bloc de constats identiques au meme risque est un defaut de l auditeur."""
        releve = [_page("/sitemap.xml", _SITEMAP_FIGE)]

        constats = _findings_url(qualif.conclure(tmp_path, _config(), releve, []))

        assert len(constats) == 1, [f.id for f in constats]
        assert constats[0].id == "qualif:url:/sitemap.xml:sitemap-loc"
        # Le compte, lui, n est pas perdu : il est DIT.
        assert "7 URL(s)" in constats[0].message, constats[0].message

    def test_l_origine_de_l_instance_auditee_passe(self, tmp_path: Path):
        releve = [_page("/factures", _ENTETE_SAIN)]

        sortie = qualif.conclure(tmp_path, _config(), releve, [])

        assert sortie.verdict == "PASS", [f.id for f in sortie.findings]
        assert not _findings_url(sortie)

    def test_une_origine_publique_DECLAREE_passe(self, tmp_path: Path):
        """Le cas legitime : audite en clair derriere un proxy, publie en https ailleurs."""
        releve = [_page("/factures", _ENTETE_FIGE)]

        sortie = qualif.conclure(tmp_path, _config(["http://localhost:8000"]), releve, [])

        assert sortie.verdict == "PASS", [f.id for f in sortie.findings]
        assert not _findings_url(sortie)

    def test_une_page_sans_url_auto_referente_n_ajoute_rien_a_la_surface(self, tmp_path: Path):
        """Pas de pression inventee : ce controle ne cree d element que la ou il y a matiere."""
        releve = [_page("/factures", _ENTETE_RELATIF)]

        sortie = qualif.conclure(tmp_path, _config(), releve, [])

        assert not [e for e in sortie.surface["elements_exerces"] if e.startswith("qualif:url:")]
        assert sortie.verdict == "PASS"


# --- Declaration : le controle DIT ce qu il a confronte, meme quand il n a rien trouve --------
class TestCeQuiSeDit:
    def test_le_controle_se_declare_au_rapport(self, tmp_path: Path):
        releve = [_page("/factures", _ENTETE_SAIN)]

        sortie = qualif.conclure(tmp_path, _config(), releve, [])

        # TF-0292 — deux declarations desormais : la REGLE (constante `NON_JUGE` du module,
        # comptee au registre de dette : les quatre formes reconnues, le plafond de lecture,
        # les seules routes parcourues) et la MESURE de ce run (combien d URLs confrontees, a
        # quelles origines). Le test verifie les DEUX : un controle de plus, pas un de moins.
        # La REGLE vit dans la constante du module — c est de la qu elle entre au registre de
        # dette (`python -m forge_tests.dette`), et `analyser` la verse dans chaque sortie.
        regles = [ligne for ligne in qualif.NON_JUGE if "auto-referente" in ligne]
        assert regles, qualif.NON_JUGE
        assert "canonical" in regles[0] and "20 000" in regles[0], regles[0]

        mesures = [ligne for ligne in sortie.non_juge if "confrontee(s)" in ligne]
        assert mesures, sortie.non_juge
        assert "4 URL(s)" in mesures[0], mesures[0]
        assert _BASE in mesures[0]

    def test_zero_URL_trouvee_se_dit_aussi(self, tmp_path: Path):
        """« aucune URL auto-referente » et « jamais regardees » ne sont pas le meme rapport."""
        releve = [_page("/factures", _ENTETE_RELATIF)]

        sortie = qualif.conclure(tmp_path, _config(), releve, [])

        assert any("0 URL(s) auto-referente(s)" in ligne for ligne in sortie.non_juge)


class TestLesOriginesAdmises:
    def test_l_instance_auditee_est_toujours_admise(self):
        assert qualif.origines_admises(_config()) == {"https://qualif.exemple"}

    def test_les_origines_declarees_s_ajoutent(self):
        admises = qualif.origines_admises(_config(["https://www.produit.fr", "http://localhost"]))

        assert admises == {
            "https://qualif.exemple",
            "https://www.produit.fr",
            "http://localhost",
        }

    def test_le_schema_fait_partie_de_l_origine(self):
        """`http://` et `https://` sur le meme hote : DEUX origines, comme pour un navigateur."""
        assert qualif._origine("http://qualif.exemple/x") != qualif._origine(
            "https://qualif.exemple/x"
        )
