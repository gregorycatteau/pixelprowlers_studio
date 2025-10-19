// server/plugins/file-polyfill.ts
// Polyfill léger pour globalThis.File côté Node (Nitro) afin d'éviter l'erreur
// « File is not defined » avec undici/ofetch sous Node < 20.
// - Objectif: stabiliser le runtime serveur Nuxt/Nitro sans upgrade de Node/Nuxt.
// - Sécurité: ne s'applique qu'au contexte serveur (aucun impact client).
//
// Explication (FR):
// - Certaines versions d'undici supposent l'existence de l'API Web File (globale).
// - Sur des versions de Node antérieures, cette API n'est pas disponible.
// - Nous définissons une implémentation minimale compatible pour satisfaire les checks
//   de type de ces librairies. Cela suffit pour les proxys HTTP que nous utilisons.
//
// Note: si l'environnement passe à Node >= 20, ce polyfill devient inutile.

export default () => {
  // Vérifie si File n'existe pas dans le contexte Node
  if (typeof (globalThis as any).File === 'undefined') {
    // Implémentation minimale: File étend Blob et expose name/lastModified
    class NodeFile extends Blob {
      name: string
      lastModified: number

      // FR: constructeur compatible Web File(name, lastModified, type via Blob)
      constructor(fileBits: any[] = [], fileName: string = 'unnamed', options: any = {}) {
        super(fileBits, options)
        this.name = String(fileName)
        const lm = options?.lastModified
        this.lastModified = typeof lm === 'number' ? lm : Date.now()
      }

      // FR: toStringTag pour mimer l'objet natif File
      get [Symbol.toStringTag]() {
        return 'File'
      }
    }

    // FR: injecte le polyfill dans le global
    ;(globalThis as any).File = NodeFile as any
  }
}
