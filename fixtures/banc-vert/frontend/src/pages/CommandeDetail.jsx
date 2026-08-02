export default function CommandeDetail() {
  return (
    <section>
      <input data-testid="champ-quantite" type="number" />
      <select data-testid="selecteur-plat" />
      <button data-testid="bouton-enregistrer">Enregistrer</button>
      <button data-testid="bouton-annuler">Annuler</button>
      <button data-testid="bouton-supprimer">Supprimer</button>
      <button data-testid="bouton-dupliquer">Dupliquer</button>
    </section>
  );
}
