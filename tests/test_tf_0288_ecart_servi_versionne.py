"""TF-0288 — l ecart entre ce que la source VERSIONNE promet et ce que la production SERT.

**Le cas fondateur, mesure.** INS-0001, 15/08/2026 : un menu anglais ampute, signale DEUX fois
par l humain. La cause evidente etait fausse — `HeaderEn.tsx` portait bien ses 8 entrees de
premier niveau et ses 36 liens, et il etait utilise par 36 pages EN sur 36. La production en
servait TROIS. L ecart vivait entre la SOURCE et le SERVI, et aucun oracle de l ecosysteme ne
comparait ces deux termes-la : le pan `i18n` compare les locales du SERVI entre elles, le
controle de destinations de TF-0283 juge la coherence INTERNE de la source, le pan `qualif` juge
la sante du servi — un menu ampute mais fonctionnel n est en erreur nulle part.

Sans le bloc (b) de l instruction, la reponse evidente aurait ete d ajouter les entrees
manquantes au composant : un developpement inutile sur un defaut de DEPLOIEMENT, et un troisieme
« toujours pas ». C est pourquoi la classe de constat est distincte et son destinataire aussi —
`mep-config`, pas `development`.

Verdict O3 de l etude d opportunite 20260817a : la DETECTION ici (jouable sur n importe quel
produit servi), la PREVENTION chez forge-ops (empreinte scellee au deploiement).

Trois fixtures, une par issue, et pas une de plus :
  - ROUGE : source a 8 entrees, servi a 3 -> FAIL, les 5 manquantes NOMMEES ;
  - VERTE : les memes, identiques -> PASS ;
  - SKIP : sans source -> pas de versionne opposable, et le motif le DIT.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import interface

# Les 8 entrees de premier niveau du menu anglais reel, telles que `HeaderEn.tsx` les portait.
_ENTREES_SOURCE = (
    ("/en", "Home"),
    ("/en/offer", "Our offer"),
    ("/en/method", "Method"),
    ("/en/references", "References"),
    ("/en/blog", "Blog"),
    ("/en/about", "About us"),
    ("/en/careers", "Careers"),
    ("/en/contact", "Contact"),
)
# Ce que la production servait : trois entrees, et personne ne savait pourquoi.
_ENTREES_SERVIES = ("/en", "/en/blog", "/en/contact")


def _composant(entrees: tuple[tuple[str, str], ...]) -> str:
    """`HeaderEn.tsx` reduit a ce que le controle lit : le `<nav>` et ses liens litteraux.

    Le logo est HORS du `<nav>` a dessein : il ne doit pas compter comme une entree de menu.
    """
    liens = "\n".join(
        f'        <Link href="{cible}">{libelle}</Link>' for cible, libelle in entrees
    )
    return (
        "export default function HeaderEn() {\n"
        "  return (\n"
        "    <header>\n"
        '      <Link href="/en"><img src="/logo.svg" alt="Digit-AI logo" /></Link>\n'
        "      <nav>\n"
        f"{liens}\n"
        "      </nav>\n"
        "    </header>\n"
        "  );\n"
        "}\n"
    )


_PAGE_SERVIE = """<!doctype html>
<html lang="{lang}">
<head><meta charset="utf-8"><title>{titre}</title></head>
<body>
  <header>
    <a href="{accueil}"><img src="/logo.svg" alt="Digit-AI logo"></a>
    <nav>
{entrees}
    </nav>
  </header>
  <main><h1>{titre}</h1></main>
</body>
</html>
"""


def _page(lang: str, titre: str, accueil: str, entrees: tuple[str, ...]) -> str:
    liens = "\n".join(f'      <a href="{cible}">{cible}</a>' for cible in entrees)
    return _PAGE_SERVIE.format(lang=lang, titre=titre, accueil=accueil, entrees=liens)


def _produit(
    racine: Path,
    *,
    entrees_source: tuple[tuple[str, str], ...] | None = _ENTREES_SOURCE,
    entrees_servies: tuple[str, ...] = _ENTREES_SERVIES,
    avec_build: bool = True,
) -> Path:
    """Un produit a deux locales : le francais sans prefixe, l anglais sous `/en`.

    `entrees_source=None` retire le composant : c est la fixture SKIP — un produit dont on ne
    tient pas la source (hors git, build livre seul) n a pas de versionne opposable.
    """
    # L arborescence des routes, pour que les destinations existent (le controle d existence de
    # TF-0283 ne doit pas parasiter la mesure de l ecart).
    for cible, _ in _ENTREES_SOURCE:
        chemin = racine / "app" / cible.strip("/") / "page.tsx"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("export default function Page() { return <main />; }\n", "utf-8")
    (racine / "app" / "page.tsx").write_text(
        "export default function Page() { return <main />; }\n", encoding="utf-8"
    )

    if entrees_source is not None:
        composants = racine / "components"
        composants.mkdir(parents=True, exist_ok=True)
        (composants / "HeaderEn.tsx").write_text(_composant(entrees_source), encoding="utf-8")

    if avec_build:
        build = racine / "dist"
        (build / "en").mkdir(parents=True)
        (build / "index.html").write_text(
            _page("fr", "Accueil", "/", ("/", "/blog", "/contact")), encoding="utf-8"
        )
        (build / "en" / "index.html").write_text(
            _page("en", "Home", "/en", entrees_servies), encoding="utf-8"
        )
    return racine


@pytest.fixture(autouse=True)
def _sans_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORGE_TESTS_I18N_BUILD", raising=False)


# --- Fixture ROUGE : le cas fondateur, 8 entrees promises, 3 servies ---------------------------
def test_rouge_l_ecart_est_constate_et_les_entrees_manquantes_sont_NOMMEES(tmp_path: Path) -> None:
    """LE constat qui manquait le 15/08. « Il y a un ecart » n aurait rien valu : ce sont les
    entrees nommees qui prouvent que la source les porte et que le servi ne les rend pas."""
    ecart = interface.ecart_servi_versionne(_produit(tmp_path))

    assert ecart["verdict"] == "FAIL", ecart
    assert ecart["manquantes"]["en"] == [
        "/about", "/careers", "/method", "/offer", "/references"
    ], ecart["manquantes"]


def test_rouge_le_constat_dit_que_le_CODE_est_correct(tmp_path: Path) -> None:
    """La moitie utile du constat. Sans elle, la reponse evidente est d ajouter au composant des
    entrees qu il porte deja — le developpement inutile qu INS-0001 a failli couter."""
    sortie = interface.analyser(_produit(tmp_path))

    constats = [f for f in sortie.findings if f.classe == interface.CLASSE_ECART_SERVI]
    assert len(constats) == 1, [f.id for f in sortie.findings]
    assert "le SERVI qui a derive" in constats[0].message
    assert "defaut de deploiement" in constats[0].message
    assert sortie.verdict == "FAIL"


def test_rouge_la_suite_a_donner_est_un_REDEPLOIEMENT_pas_un_correctif(tmp_path: Path) -> None:
    """Le destinataire est le coeur du sujet : classer ce constat en `development` renverrait le
    developpeur corriger un code deja juste."""
    from forge_tests.actions import classifier

    sortie = interface.analyser(_produit(tmp_path))
    findings = [{**vars(f), "pan": interface.PAN} for f in sortie.findings]

    actions = {
        action["finding_ref"]: action
        for action in classifier(findings)
        if "ecart-servi" in action["finding_ref"]
    }
    assert actions, [a["finding_ref"] for a in classifier(findings)]
    action = next(iter(actions.values()))
    assert action["etape_cible"] == "mep-config", action
    assert action["categorie"] == "manuelle_utilisateur", action
    assert "REDÉPLOYER" in action["attendu"] and "Ne PAS toucher au code" in action["attendu"]
    assert "DÉFAUT D'AUDITEUR" not in action["attendu"]


def test_rouge_le_logo_hors_du_nav_n_est_pas_compte_comme_une_entree(tmp_path: Path) -> None:
    """Le composant porte un logo vers `/en` HORS du `<nav>` : le compter fausserait les deux
    cotes, et un menu servi sans logo passerait pour ampute."""
    promises, fichiers, liens = interface.navigation_source(_produit(tmp_path))

    assert liens == len(_ENTREES_SOURCE), liens
    assert fichiers == ["components/HeaderEn.tsx"]
    assert promises["en"] == {"/", "/offer", "/method", "/references", "/blog", "/about",
                              "/careers", "/contact"}


# --- Fixture VERTE : les memes entrees des deux cotes ------------------------------------------
def test_vert_une_source_et_un_servi_identiques_passent(tmp_path: Path) -> None:
    """La contrepartie sans laquelle le controle ne prouverait rien : un deploiement fidele ne
    doit produire AUCUN constat."""
    cible = _produit(tmp_path, entrees_servies=tuple(c for c, _ in _ENTREES_SOURCE))

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "PASS", ecart
    assert ecart["manquantes"] == {}
    assert not [
        f for f in interface.analyser(cible).findings if f.classe == interface.CLASSE_ECART_SERVI
    ]


def test_vert_une_entree_SERVIE_de_plus_n_est_pas_un_constat(tmp_path: Path) -> None:
    """La comparaison n est pas symetrique, et c est declare : une entree servie qu aucune source
    ne promet peut venir d un autre composant ou d un gabarit serveur. L accuser serait accuser
    la limite du lecteur, pas le produit."""
    cible = _produit(
        tmp_path,
        entrees_servies=(*(c for c, _ in _ENTREES_SOURCE), "/en/newsroom"),
    )

    assert interface.ecart_servi_versionne(cible)["verdict"] == "PASS"


def test_vert_la_locale_par_defaut_est_confrontee_elle_aussi(tmp_path: Path) -> None:
    """Le composant anglais ne promet rien pour le francais : la locale par defaut ne doit pas
    heriter de ses entrees, sous peine d un ecart massif et faux sur tout produit multilingue."""
    ecart = interface.ecart_servi_versionne(_produit(tmp_path))

    assert "" not in ecart["manquantes"], ecart["manquantes"]


# --- Fixture SKIP : pas de source, donc pas de versionne opposable -----------------------------
def test_skip_sans_source_le_controle_REFUSE_de_conclure_et_dit_pourquoi(tmp_path: Path) -> None:
    """L aggravant du cas fondateur : digit-ai.fr n etait pas sous git, donc rien ne disait ce
    qui etait deploye. Un SKIP muet aurait rendu « aucun ecart » indiscernable de « la
    comparaison n a pas eu lieu » — la confusion exacte qui a coute deux « toujours pas »."""
    ecart = interface.ecart_servi_versionne(
        _produit(tmp_path, entrees_source=None)
    )

    assert ecart["verdict"] == "SKIP", ecart
    assert "pas de versionne OPPOSABLE" in ecart["motif"]
    assert ecart["manquantes"] == {}


def test_skip_sans_build_servi_le_motif_designe_l_AUTRE_terme(tmp_path: Path) -> None:
    """« Pas de source » et « pas de build » ne se reparent pas de la meme facon : le motif doit
    dire lequel des deux termes manque, sinon il envoie chercher au mauvais endroit."""
    ecart = interface.ecart_servi_versionne(_produit(tmp_path, avec_build=False))

    assert ecart["verdict"] == "SKIP", ecart
    assert "AUCUN build servi" in ecart["motif"]
    assert "FORGE_TESTS_I18N_BUILD" in ecart["motif"]


def test_le_controle_se_DECLARE_au_rapport_dans_les_trois_issues(tmp_path: Path) -> None:
    """R-35 sous une autre forme : un controle dont le rapport ne porte pas la trace n a pas eu
    lieu pour son lecteur."""
    for cible, attendu in (
        (_produit(tmp_path / "rouge"), "fail"),
        (_produit(tmp_path / "vert", entrees_servies=tuple(c for c, _ in _ENTREES_SOURCE)),
         "pass"),
        (_produit(tmp_path / "skip", entrees_source=None), "skip"),
    ):
        sortie = interface.analyser(cible)
        declarations = [
            ligne for ligne in sortie.non_juge if ligne.startswith(f"interface/{attendu} —")
        ]
        assert declarations, (attendu, sortie.non_juge)
        assert "ecart servi/versionne" in declarations[0], declarations[0]


# --- Les BANCS du depot : la branche FAIL entre au corpus (TF-0300) ----------------------------
# La campagne TF-0288 avait prouve la branche FAIL par les fixtures ci-dessus, et les branches
# PASS/SKIP en recette sur les deux bancs : la branche qui ACCUSE reposait donc sur pytest seul.
# Le banc rouge porte desormais la source du site servi par son `dist\` (`site/`), et l ecart y
# est plante : entree de corpus H-20. Les deux tests ci-dessous sont le double sens de cette
# entree — sans le second, planter un defaut au rouge pourrait en fabriquer un au vert sans que
# rien ne le dise, et le critere S-01 exige ZERO bloquant au vert.
_BANCS = Path(__file__).resolve().parent.parent / "fixtures"


def test_banc_rouge_l_ecart_est_constate_et_la_page_manquante_est_NOMMEE() -> None:
    """H-20 : le menu anglais versionne promet `/en/tarifs`, `dist/en/index.html` ne le sert pas."""
    cible = _BANCS / "banc-rouge"

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "FAIL", ecart
    assert ecart["manquantes"] == {"en": ["/tarifs"]}, ecart["manquantes"]
    constats = [
        f for f in interface.analyser(cible).findings if f.classe == interface.CLASSE_ECART_SERVI
    ]
    assert [f.id for f in constats] == ["interface:ecart-servi:en"], [f.id for f in constats]
    # Le prefixe que le corpus oppose a H-20 : il apparie ce constat et LUI SEUL.
    assert constats[0].id.startswith("interface:ecart-servi:")


def test_banc_vert_ne_produit_AUCUN_constat_nouveau() -> None:
    """Le second sens, et la condition de S-01 : le banc vert n a pas de source de site, donc pas
    de versionne opposable — SKIP motive, et zero finding pour ce pan."""
    cible = _BANCS / "banc-vert"

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] in ("PASS", "SKIP"), ecart
    assert ecart["manquantes"] == {}, ecart["manquantes"]
    sortie = interface.analyser(cible)
    assert [f.id for f in sortie.findings] == [], [f.id for f in sortie.findings]
    assert sortie.verdict == "PASS"


# --- Ce que le controle ne pretend pas faire ---------------------------------------------------
def test_une_destination_EXPRIMEE_n_entre_pas_dans_les_entrees_promises(tmp_path: Path) -> None:
    """Comparer ce qu on n a pas resolu accuserait un deploiement correct."""
    cible = _produit(tmp_path)
    composant = cible / "components" / "HeaderEn.tsx"
    composant.write_text(
        composant.read_text(encoding="utf-8").replace(
            '<Link href="/en/offer">Our offer</Link>',
            "<Link href={chemin.offre}>Our offer</Link>",
        ),
        encoding="utf-8",
    )

    promises, _fichiers, _liens = interface.navigation_source(cible)

    assert "/offer" not in promises["en"], promises["en"]


def test_un_lien_hors_nav_n_entre_pas_dans_les_entrees_promises(tmp_path: Path) -> None:
    """Les liens du pied de page ou du corps ne sont pas des entrees de menu : les melanger
    produirait un ecart massif et faux des le premier produit reel."""
    cible = _produit(tmp_path)
    (cible / "components" / "FooterEn.tsx").write_text(
        'export default function FooterEn() {\n'
        '  return <footer><a href="/en/legal">Legal</a></footer>;\n'
        "}\n",
        encoding="utf-8",
    )

    promises, fichiers, _liens = interface.navigation_source(cible)

    assert "/legal" not in promises.get("en", set())
    assert "components/FooterEn.tsx" not in fichiers


def test_un_composant_SANS_locale_promet_ses_entrees_a_TOUTES_les_locales(tmp_path: Path) -> None:
    """Un menu unique qui sert les deux langues promet ses entrees partout : les rattacher a une
    seule locale laisserait l autre sans controle."""
    cible = _produit(tmp_path, entrees_source=None)
    composants = cible / "components"
    composants.mkdir(parents=True, exist_ok=True)
    (composants / "Header.tsx").write_text(
        _composant((("/blog", "Blog"), ("/tarifs", "Tarifs"))), encoding="utf-8"
    )

    ecart = interface.ecart_servi_versionne(cible)

    assert ecart["verdict"] == "FAIL", ecart
    # `/tarifs` n est servi dans aucune des deux locales : les deux sont donc constatees.
    assert set(ecart["manquantes"]) == {"", "en"}, ecart["manquantes"]
    assert ecart["manquantes"][""] == ["/tarifs"]
