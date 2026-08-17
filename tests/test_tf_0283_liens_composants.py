"""TF-0283 — le pan `interface` lit les destinations des liens des composants React.

**La cause racine, datée.** Le 15/08/2026, sur un produit LEGACY EN PRODUCTION (digit-ai.fr),
quatre liens faux vivaient dans des composants `.tsx`, invisibles à l auditeur parce que le pan
`interface` déclarait les `.jsx`/`.tsx` hors de son périmètre (README.md § « Limites déclarées »,
`interface.py` : « leur câblage est une expression du langage ») :

  1. le logo de l en-tête ANGLAIS pointait vers `/en/blog` au lieu de l accueil anglais `/en` ;
  2. le lien « Contact » de l en-tête ANGLAIS pointait vers `/contact`, la page FRANÇAISE ;
  3. le lien « Contact » du pied de page ANGLAIS faisait la même chose ;
  4. la bascule « Français » pointait vers `/blog` au lieu de l accueil français `/`.

L humain l a signalé DEUX FOIS. Aucun oracle ne pouvait les voir : le câblage est bien réel
(ce sont de vrais `href`), la page cible existe, et la suite de tests ne clique pas dessus.

Ce fichier est la fixture ROUGE (les quatre liens tels qu ils étaient) et la fixture VERTE (les
mêmes composants corrigés). Le sens rouge est vérifié lien par lien : un contrôle qui échouerait
« globalement » ne prouverait pas qu il attrape CE défaut-là.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import interface

# --- L arborescence du produit, réduite à ce que les quatre liens mettent en jeu ---------------
# Convention Next App Router, telle qu elle vit sur le produit réel : le français est servi sans
# préfixe, l anglais sous `/en`.
_PAGES = (
    "app/page.tsx",
    "app/blog/page.tsx",
    "app/contact/page.tsx",
    "app/en/page.tsx",
    "app/en/blog/page.tsx",
    "app/en/contact/page.tsx",
)

_ENTETE_FAUX = """
export default function HeaderEn() {
  return (
    <header>
      <Link href="/en/blog"><img src="/logo.svg" alt="Digit-AI logo" /></Link>
      <nav>
        <Link href="/en/blog">Blog</Link>
        <Link href="/contact">Contact</Link>
        <Link href="/blog">Français</Link>
      </nav>
    </header>
  );
}
"""

_PIED_FAUX = """
export default function FooterEn() {
  return (
    <footer>
      <a href="/contact">Contact</a>
      <a href="https://www.linkedin.com/company/digit-ai">LinkedIn</a>
    </footer>
  );
}
"""

_ENTETE_JUSTE = """
export default function HeaderEn() {
  return (
    <header>
      <Link href="/en"><img src="/logo.svg" alt="Digit-AI logo" /></Link>
      <nav>
        <Link href="/en/blog">Blog</Link>
        <Link href="/en/contact">Contact</Link>
        <Link href="/">Français</Link>
      </nav>
    </header>
  );
}
"""

_PIED_JUSTE = """
export default function FooterEn() {
  return (
    <footer>
      <a href="/en/contact">Contact</a>
      <a href="https://www.linkedin.com/company/digit-ai">LinkedIn</a>
    </footer>
  );
}
"""


def _produit(racine: Path, entete: str, pied: str) -> Path:
    for page in _PAGES:
        chemin = racine / page
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("export default function Page() { return <main />; }\n", "utf-8")
    composants = racine / "components"
    composants.mkdir(parents=True, exist_ok=True)
    (composants / "HeaderEn.tsx").write_text(entete, encoding="utf-8")
    (composants / "FooterEn.tsx").write_text(pied, encoding="utf-8")
    return racine


def _motifs(cible: Path) -> dict[str, str]:
    """Libellé du lien -> motif du constat, pour les seuls liens jugés fautifs."""
    releve, _, _ = interface._relever_composants(cible)
    return {entree["libelle"]: entree["motif"] for entree in releve if entree["motif"]}


# --- Fixture ROUGE : les quatre liens réels du 15/08 --------------------------------------------
def test_rouge_le_logo_anglais_qui_mene_au_blog_est_attrape(tmp_path: Path) -> None:
    """Défaut 1 — le logo promet l accueil ; il menait `/en/blog` depuis CHAQUE écran anglais."""
    cible = _produit(tmp_path, _ENTETE_FAUX, _PIED_FAUX)
    motifs = _motifs(cible)
    assert "logo" in " ".join(motifs.values())
    logo = next(motif for libelle, motif in motifs.items() if "logo" in motif)
    assert "/en/blog" in logo and "/en" in logo


def test_rouge_le_contact_anglais_de_l_entete_pointe_vers_le_francais(tmp_path: Path) -> None:
    """Défaut 2 — `/contact` est la page FRANÇAISE, et `/en/contact` existe."""
    cible = _produit(tmp_path, _ENTETE_FAUX, _PIED_FAUX)
    motif = _motifs(cible)["Contact"]
    assert "/contact" in motif
    assert "/en/contact" in motif  # la contrepartie EXISTE : c est ce qui prouve le défaut


def test_rouge_le_contact_anglais_du_pied_de_page_aussi(tmp_path: Path) -> None:
    """Défaut 3 — le même défaut dans un AUTRE composant : les deux sont nommés, pas un seul."""
    cible = _produit(tmp_path, _ENTETE_FAUX, _PIED_FAUX)
    releve, _, _ = interface._relever_composants(cible)
    fautifs = {
        Path(e["fichier"]).name for e in releve if e["motif"] and e["libelle"] == "Contact"
    }
    assert fautifs == {"HeaderEn.tsx", "FooterEn.tsx"}


def test_rouge_la_bascule_francais_qui_mene_au_blog_est_attrapee(tmp_path: Path) -> None:
    """Défaut 4 — une bascule de langue promet l accueil de la langue visée, pas un article."""
    cible = _produit(tmp_path, _ENTETE_FAUX, _PIED_FAUX)
    motif = _motifs(cible)["Français"]
    assert "bascule de langue" in motif
    assert "/blog" in motif


def test_rouge_les_quatre_liens_et_EUX_SEULS_sont_nommes(tmp_path: Path) -> None:
    """Le compte exact : quatre constats. Un cinquième serait un faux positif, et il coûterait
    autant de confiance que les quatre défauts en coûtent."""
    cible = _produit(tmp_path, _ENTETE_FAUX, _PIED_FAUX)
    releve, _, _ = interface._relever_composants(cible)
    fautifs = [e for e in releve if e["motif"]]
    assert len(fautifs) == 4, [e["motif"] for e in fautifs]


# --- Fixture VERTE : les mêmes composants, corrigés --------------------------------------------
def test_vert_les_memes_composants_corriges_ne_produisent_aucun_constat(tmp_path: Path) -> None:
    cible = _produit(tmp_path, _ENTETE_JUSTE, _PIED_JUSTE)
    releve, _, _ = interface._relever_composants(cible)
    assert [e["motif"] for e in releve if e["motif"]] == []
    assert len(releve) == 6  # les six liens sont bien RELEVÉS, pas ignorés


def test_vert_un_lien_externe_n_est_jamais_juge(tmp_path: Path) -> None:
    """Le lien LinkedIn du pied de page : hors du site, hors de portée d un contrôle statique."""
    cible = _produit(tmp_path, _ENTETE_JUSTE, _PIED_JUSTE)
    releve, _, _ = interface._relever_composants(cible)
    externe = [e for e in releve if e["libelle"] == "LinkedIn"]
    assert len(externe) == 1 and externe[0]["motif"] is None


# --- Les trois contrôles de la lettre, isolés ---------------------------------------------------
def test_une_destination_absente_de_l_arborescence_est_nommee(tmp_path: Path) -> None:
    cible = _produit(tmp_path, _ENTETE_JUSTE, _PIED_JUSTE)
    (cible / "components" / "Menu.tsx").write_text(
        '<a href="/tarifs">Tarifs</a>\n', encoding="utf-8"
    )
    assert "absente de l arborescence" in _motifs(cible)["Tarifs"]


def test_une_destination_qui_existe_ne_l_est_pas(tmp_path: Path) -> None:
    """Sens vert du même contrôle : la page existe, aucun constat."""
    cible = _produit(tmp_path, _ENTETE_JUSTE, _PIED_JUSTE)
    (cible / "components" / "Menu.tsx").write_text(
        '<a href="/blog">Blog</a>\n', encoding="utf-8"
    )
    assert "Blog" not in _motifs(cible)


def test_le_controle_d_existence_se_desactive_quand_rien_n_est_enumerable(tmp_path: Path) -> None:
    """Garde-fou : sans arborescence lisible, on ne juge RIEN — accuser tous les liens d un
    projet dont on n a pas su lire les routes serait un faux positif massif."""
    (tmp_path / "Menu.tsx").write_text('<a href="/nulle-part">Ailleurs</a>\n', encoding="utf-8")
    assert _motifs(tmp_path) == {}


def test_une_destination_exprimee_est_comptee_et_jamais_jugee(tmp_path: Path) -> None:
    cible = _produit(tmp_path, _ENTETE_JUSTE, _PIED_JUSTE)
    (cible / "components" / "Dyn.tsx").write_text(
        "<a href={`/${locale}/blog`}>Blog</a>\n<a href={lien}>Autre</a>\n", encoding="utf-8"
    )
    releve, exprimees, _ = interface._relever_composants(cible)
    assert exprimees == 2
    assert [e["motif"] for e in releve if e["fichier"].endswith("Dyn.tsx")] == [None, None]


def test_un_lien_relatif_n_est_pas_juge(tmp_path: Path) -> None:
    """Sa résolution dépend de l URL de rendu, que l analyse statique ne connaît pas."""
    cible = _produit(tmp_path, _ENTETE_JUSTE, _PIED_JUSTE)
    (cible / "components" / "Rel.tsx").write_text(
        '<a href="tarifs">Tarifs</a>\n', encoding="utf-8"
    )
    assert _motifs(cible) == {}


def test_la_locale_se_lit_aussi_dans_l_arborescence_du_composant(tmp_path: Path) -> None:
    """`components/en/Header.tsx` vaut `HeaderEn.tsx` : deux conventions, un seul verdict."""
    cible = _produit(tmp_path, _ENTETE_JUSTE, _PIED_JUSTE)
    dossier = cible / "components" / "en"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "Nav.tsx").write_text('<a href="/contact">Contact</a>\n', encoding="utf-8")
    motifs = {
        Path(e["fichier"]).parent.name: e["motif"]
        for e in interface._relever_composants(cible)[0]
        if e["motif"]
    }
    assert "en" in motifs and "/en/contact" in motifs["en"]


def test_un_composant_sans_locale_ne_recoit_aucun_verdict_de_locale(tmp_path: Path) -> None:
    """Un composant partagé rend les deux langues : il n a pas de locale propre, on ne juge pas."""
    cible = _produit(tmp_path, _ENTETE_JUSTE, _PIED_JUSTE)
    (cible / "components" / "Partage.tsx").write_text(
        '<a href="/contact">Contact</a>\n', encoding="utf-8"
    )
    partages = [
        e for e in interface._relever_composants(cible)[0] if e["fichier"].endswith("Partage.tsx")
    ]
    assert [e["motif"] for e in partages] == [None]


def test_un_lien_vers_une_page_sans_contrepartie_n_est_pas_accuse(tmp_path: Path) -> None:
    """La contrepartie EXISTE est la preuve du défaut. Sans elle, le lien n a pas d autre choix
    que de pointer vers l unique version de la page — ce n est pas une faute."""
    cible = _produit(tmp_path, _ENTETE_JUSTE, _PIED_JUSTE)
    (cible / "app" / "mentions-legales").mkdir(parents=True, exist_ok=True)
    (cible / "app" / "mentions-legales" / "page.tsx").write_text("export default 1\n", "utf-8")
    (cible / "components" / "LegalEn.tsx").write_text(
        '<a href="/mentions-legales">Legal</a>\n', encoding="utf-8"
    )
    assert _motifs(cible) == {}


# --- Non-régression du scanner -----------------------------------------------------------------
def test_une_fonction_flechee_dans_la_balise_ne_coupe_pas_la_lecture(tmp_path: Path) -> None:
    """`onClick={() => f()}` porte un `>` : une regex `<a[^>]*>` perdait le `href` qui suit."""
    cible = _produit(tmp_path, _ENTETE_JUSTE, _PIED_JUSTE)
    (cible / "components" / "ClicEn.tsx").write_text(
        '<a onClick={() => suivre("nav")} href="/contact">Contact</a>\n', encoding="utf-8"
    )
    assert "/en/contact" in _motifs(cible)["Contact"]


def test_le_pan_publie_ses_constats_de_lien_dans_une_classe_qui_leur_est_propre(
    tmp_path: Path,
) -> None:
    """Un lien faux n est pas une affordance inerte : la suite à donner n est pas la même."""
    from forge_tests.actions import classifier

    cible = _produit(tmp_path, _ENTETE_FAUX, _PIED_FAUX)
    sortie = interface.analyser(cible)
    classes = {f.classe for f in sortie.findings}
    assert classes == {"lien-casse"}
    actions = classifier([{**vars(f), "pan": "interface"} for f in sortie.findings])
    assert all("DÉFAUT D'AUDITEUR" not in a["attendu"] for a in actions)
    assert {a["categorie"] for a in actions} == {"manuelle_dev"}


def test_les_liens_de_composants_comptent_dans_la_surface_du_pan(tmp_path: Path) -> None:
    """Sans cela, le seuil opposable de 100 % ne porterait que sur les gabarits."""
    cible = _produit(tmp_path, _ENTETE_FAUX, _PIED_FAUX)
    sortie = interface.analyser(cible)
    assert sortie.verdict == "FAIL"
    assert sortie.surface["inventorie"] == 6  # 4 liens d en-tête + 2 de pied de page
    assert sortie.surface["exerce"] == 2  # les deux qui tiennent leur promesse
