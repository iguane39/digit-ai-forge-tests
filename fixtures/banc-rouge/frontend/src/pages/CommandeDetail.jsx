export default function CommandeDetail() {
  return (
    <section>
      <input data-testid="champ-quantite" type="number" defaultValue={1} />
      <select data-testid="selecteur-plat" defaultValue="curry">
        <option value="curry">Curry</option>
        <option value="soupe">Soupe</option>
      </select>
      <button data-testid="bouton-enregistrer">Enregistrer</button>
      <button data-testid="bouton-annuler">Annuler</button>
      <button data-testid="bouton-supprimer">Supprimer</button>
      <button data-testid="bouton-dupliquer">Dupliquer</button>
    </section>
  );
}
