# Section 152: **2.3.4.4. Structure de la base de données météorologiques**

> Extrait de: MANUEL_DE_LUTTE_PRÉVENTIVE_(VF).md
> Niveau: 2
> Position: ligne 3348

---

## **2.3.4.4. Structure de la base de données météorologiques** 

La base de données météorologiques regroupe les différentes données décadaires du CNA depuis le mois d’octobre 2001 (figure 63). Elle comporte quatre tables : 

– la table **Pluvio_décade** assure le chronoréférencement des informations stockées dans la base (campagne, année, mois et décade). Cette table comporte un identifiant ; 

– la table **Mto_station** contient les informations spatiales relatives aux postes pluviométriques de l’AG de Locusta. Cette table assure le géoréférencement de la base de données ; 

– la table **Décade** fournit des informations complémentaires et permet des contrôles sur les éventuelles erreurs commises lors de la saisie et une évaluation de la performance de l’observateur ; 

– la table **Pluvio_mois_enrg** permet un stockage des données mensuelles, si les données décadaires ne sont pas disponibles. 

Des requêtes sont disponibles et permettent l’accès aux données mensuelles, annuelles ou par campagne acridienne (octobre de l’année “A” à septembre de l’année “A + 1”), à différentes échelles, par station, par secteur acridien ou par région naturelle et les analyses fréquencielles des observations qui permettent l’évaluation de la performance du réseau d’observation en temps réel, en cours de campagne. 

**159** /307 

SURVEILLANCE ET AVERTISSEMENT 


---

## Navigation

← [Section précédente: **2.3.4.3. Structure de la base de données acridiennes**](section_151_2343-structure-de-la-base-de-données-acridiennes.md)

↑ [Retour à l'index](../MANUEL_DE_LUTTE_PRÉVENTIVE_(VF)_INDEX_DETAILLE.md)

→ [Section suivante: **2.3.4.5. Base de données des traitements**](section_153_2345-base-de-données-des-traitements.md)
