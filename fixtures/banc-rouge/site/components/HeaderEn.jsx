// Menu anglais du site VERSIONNE — trois entrees de premier niveau, dont les tarifs.
//
// La production, elle, n en sert que DEUX : `dist/en/index.html` porte « Home » et « Blog », et
// rien vers les tarifs. Le composant est pourtant juste, et c est tout l enjeu du cas fondateur
// INS-0001 (TF-0288) : l ecart vit entre la SOURCE et le SERVI, donc il se repare par un
// redeploiement, jamais en ajoutant au composant une entree qu il porte deja.
//
// C est le defaut H-20 du corpus (TF-0300). Le banc vert, lui, n a pas de source de site : son
// controle reste en SKIP, et le corpus ne lui demande rien.
export default function HeaderEn() {
  return (
    <header>
      <nav>
        <a href="/en">Home</a>
        <a href="/en/blog">Blog</a>
        <a href="/en/tarifs">Pricing</a>
      </nav>
    </header>
  );
}
