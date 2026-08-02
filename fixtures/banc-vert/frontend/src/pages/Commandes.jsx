export default function Commandes() {
  return (
    <section>
      <select data-testid="filtre-statut" defaultValue="brouillon" aria-label="Filtrer par statut">
        <option value="brouillon">Brouillon</option>
        <option value="validee">Validee</option>
        <option value="annulee">Annulee</option>
      </select>
      <button data-testid="tri-date">Trier par date</button>
      <button data-testid="bouton-nouvelle">Nouvelle</button>
      <button data-testid="bouton-export">Exporter</button>
      <nav data-testid="pagination">1 2 3</nav>
    </section>
  );
}
