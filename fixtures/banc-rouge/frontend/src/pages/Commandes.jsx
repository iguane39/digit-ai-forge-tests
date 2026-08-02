export default function Commandes() {
  return (
    <section style={{ padding: "90px 40px", lineHeight: "3rem" }}>
      <select data-testid="filtre-statut" defaultValue="brouillon">
        <option value="brouillon">Brouillon</option>
        <option value="validee">Validee</option>
        <option value="annulee">Annulee</option>
      </select>
      <button data-testid="tri-date">Trier par date</button>
      <button data-testid="bouton-nouvelle">Nouvelle</button>
      <button data-testid="bouton-export">Exporter</button>
      <nav data-testid="pagination"></nav>
    </section>
  );
}
