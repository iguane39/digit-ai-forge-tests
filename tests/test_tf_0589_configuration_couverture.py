"""TF-0589 — la configuration de couverture, lue avant le chiffre qu'elle produit.

Lot Approval2 20260824d. Trois défauts vivaient ensemble sous un seuil VERT : un dénominateur
non déclaré (75,33 % affiché pour 84,68 % réels), un seuil global incapable d'échouer sur un
écran à 1,88 %, et l'indicateur le plus rassurant mis en avant (90,6 % d'instructions pour
37,5 % de fonctions — les boutons rendus, presque aucun cliqué).

LES DEUX SENS, et le second est celui qui a servi tout de suite : au premier passage, la règle
s'est accusée sur le BANC VERT de la forge, parce qu'elle cherchait le mot « coverage » et l'a
trouvé dans une ligne de dépendance. Une règle qui accuse le corpus de référence de sa propre
forge ne survit pas à la première campagne pressée.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import couverture


def _config(racine: Path, nom: str, contenu: str) -> Path:
    chemin = racine / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _ids(findings) -> set[str]:
    return {f.classe for f in findings}


# --- (1) Le dénominateur déclaré ----------------------------------------------------------------
_SANS_PERIMETRE = """import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      exclude: ['e2e/**', 'public/**'],
      thresholds: { statements: 70, functions: 60, perFile: true },
    },
  },
});
"""

_AVEC_PERIMETRE = """import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      include: ['src/**'],
      exclude: ['e2e/**', 'public/**'],
      thresholds: { statements: 80, functions: 60, perFile: true },
    },
  },
});
"""


def test_une_couverture_SANS_perimetre_declare_est_denoncee(tmp_path: Path) -> None:
    """Le cas fondateur : seules des exclusions sont posées, et le dénominateur dérive."""
    _config(tmp_path, "vitest.config.ts", _SANS_PERIMETRE)

    findings = couverture.analyser_configuration(tmp_path)

    assert "couverture-perimetre-non-declare" in _ids(findings), [f.id for f in findings]
    message = next(f.message for f in findings if f.classe == "couverture-perimetre-non-declare")
    assert "illusion" in message, "le message ne dit pas pourquoi des exclusions seules trompent"
    assert "75,33" in message, "le message ne porte pas la mesure qui l'a fait naître"


def test_un_perimetre_declare_en_POSITIF_est_innocent(tmp_path: Path) -> None:
    """La forme corrigée : `include` explicite, et les exclusions gardent leur place."""
    _config(tmp_path, "vitest.config.ts", _AVEC_PERIMETRE)

    assert couverture.analyser_configuration(tmp_path) == []


# --- (2) Le seuil par fichier -------------------------------------------------------------------
_SEUIL_GLOBAL_SEUL = """import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      include: ['src/**'],
      thresholds: { statements: 70, functions: 60 },
    },
  },
});
"""


def test_un_seuil_GLOBAL_sans_seuil_par_fichier_est_denonce(tmp_path: Path) -> None:
    """Aucune valeur de seuil global n'aurait signalé un écran à 1,88 % sans faire échouer tout.

    Le message porte aussi la leçon de POSE — caler le plancher SOUS le niveau atteint — parce
    que c'est le moment exact où quelqu'un choisit un chiffre, et le seul endroit où elle sert.
    """
    _config(tmp_path, "vitest.config.ts", _SEUIL_GLOBAL_SEUL)

    findings = couverture.analyser_configuration(tmp_path)

    assert "couverture-seuil-global-sans-seuil-par-fichier" in _ids(findings)
    message = next(
        f.message for f in findings
        if f.classe == "couverture-seuil-global-sans-seuil-par-fichier"
    )
    assert "1,88" in message, "le message ne porte pas la mesure"
    assert "SOUS LE NIVEAU ATTEINT" in message, (
        "le message ne dit pas comment CALER le plancher — un cliquet à ras de la mesure casse au "
        "premier remaniement légitime, et la règle qui l'évite se perdrait ici"
    )


def test_un_seuil_par_fichier_present_est_innocent(tmp_path: Path) -> None:
    _config(tmp_path, "vitest.config.ts", _AVEC_PERIMETRE)

    assert not [
        f for f in couverture.analyser_configuration(tmp_path)
        if f.classe == "couverture-seuil-global-sans-seuil-par-fichier"
    ]


# --- (3) Les fonctions à côté des instructions --------------------------------------------------
_SANS_FONCTIONS = """import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      include: ['src/**'],
      thresholds: { statements: 80, perFile: true },
    },
  },
});
"""


def test_un_seuil_sur_les_instructions_SANS_seuil_sur_les_fonctions_est_signale(
    tmp_path: Path,
) -> None:
    """SIGNALÉ, jamais bloquant : un projet sans interface peut s'en tenir aux instructions.

    La sévérité n'est pas un confort. Sur du code d'interface, une ligne couverte par un simple
    rendu ne prouve rien d'un geste — mais l'oracle ne sait pas si le projet a une interface, et
    condamner sur une inconnue est ce qui fait désactiver une règle.
    """
    _config(tmp_path, "vitest.config.ts", _SANS_FONCTIONS)

    findings = couverture.analyser_configuration(tmp_path)
    concerne = [f for f in findings if f.classe == "couverture-fonctions-sans-seuil"]

    assert concerne, [f.id for f in findings]
    assert concerne[0].severite == "signale", "cette règle ne doit pas bloquer"
    assert "37,5" in concerne[0].message, "le message ne porte pas la mesure"


# --- Les bornes : ce que la règle NE juge PAS ---------------------------------------------------
def test_une_configuration_qui_ne_CONFIGURE_pas_la_couverture_n_est_pas_jugee(
    tmp_path: Path,
) -> None:
    """Le faux positif du premier passage, tenu par un test.

    Le motif initial cherchait le mot « coverage » et l'a trouvé dans une ligne de DÉPENDANCE du
    banc VERT de la forge — un banc réputé sans défaut se serait mis à rendre un constat
    bloquant. Un contrôle qui accuse à tort ne se corrige pas, il se fait désactiver.
    """
    _config(tmp_path, "pyproject.toml", '[project]\ndependencies = ["coverage>=7.15.2"]\n')

    assert couverture.analyser_configuration(tmp_path) == []


def test_un_pyproject_qui_configure_VRAIMENT_la_couverture_est_jugé(tmp_path: Path) -> None:
    """Et le sens inverse, sans quoi le resserrage aurait pu tout éteindre."""
    _config(
        tmp_path, "pyproject.toml",
        '[tool.coverage.report]\nomit = ["tests/*"]\nfail_under = 80\n',
    )

    assert "couverture-perimetre-non-declare" in _ids(couverture.analyser_configuration(tmp_path))


def test_les_bancs_de_la_forge_ne_rendent_AUCUN_constat(tmp_path: Path) -> None:
    """La mesure d'entrée, jouée sur le corpus RÉEL et non sur des fixtures (leçon N-23 du pilot).

    Ce que la règle attrape à tort se lit avant ce qu'elle attrape à raison. Les deux bancs sont
    le corpus de référence de la forge : un constat ici serait un faux positif, par construction.
    """
    racine = Path(__file__).resolve().parent.parent
    for banc in ("fixtures/banc-vert", "fixtures/banc-rouge"):
        findings = couverture.analyser_configuration(racine / banc)
        assert findings == [], f"{banc} : {[f.id for f in findings]}"


def test_la_regle_est_jouee_par_le_pan_front(tmp_path: Path) -> None:
    """Une règle que le point d'entrée n'appelle pas n'existe pas (loi n° 1)."""
    from forge_tests.adaptateurs import front

    _config(tmp_path, "vitest.config.ts", _SANS_PERIMETRE)
    sortie = front.analyser(tmp_path)

    assert "couverture-perimetre-non-declare" in {f.classe for f in sortie.findings}
