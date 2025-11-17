#!/usr/bin/env python3
"""
Extracteur complet EHF - Combine l'extraction des formalités ET du tableau de la dernière page
"""

import pdfplumber
import json
import re
import unicodedata
from typing import List, Dict, Any
from pathlib import Path
from PyPDF2 import PdfReader

def normalize_text(text: str) -> str:
    """Normaliser le texte pour la recherche."""
    # 1. Normaliser les accents/ligatures (fi → fi, é → e)
    text = unicodedata.normalize("NFKD", text)
    # 2. Supprimer les diacritiques
    text = "".join(c for c in text if not unicodedata.combining(c))
    # 3. Remplacer les espaces spéciaux et sauts de ligne par un espace normal
    text = re.sub(r"[\s\u00A0\u202F]+", " ", text)
    return text.lower().strip()

def extract_formalites_from_pdf(pdf_path: str) -> List[Dict[str, str]]:
    """
    Extraire toutes les formalités du PDF basées sur "Date de dépot".
    """
    
    print(f"📋 Extraction des formalités depuis : {pdf_path}")
    
    # Extraire tout le texte du PDF avec PyPDF2
    reader = PdfReader(pdf_path)
    full_text = ""
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        full_text += page_text + "\n"
        print(f"📄 Page {i+1} extraite pour formalités")
    
    print(f"📝 Texte complet extrait ({len(full_text)} caractères)")
    
    # Diviser le texte en formalités basées sur "Date de dépot" SANS normalisation
    # Pattern pour trouver "Date de dépot" (avec variations)
    depot_pattern = r"Date de d[eé]p[oô]t\s*:"
    
    # Diviser le texte original (pas normalisé) en sections
    sections = re.split(depot_pattern, full_text, flags=re.IGNORECASE)
    
    print(f"🔍 Nombre de sections trouvées : {len(sections)}")
    
    # Construire la liste des formalités
    formalites = []
    
    for i, section in enumerate(sections):
        if i == 0:  # Ignorer la première section (avant le premier "Date de dépot")
            continue
        
        # Nettoyer et préparer le contenu (garder la casse originale)
        contenu = section.strip()
        if contenu:  # Seulement si le contenu n'est pas vide
            
            # Extraire la chaîne entre "Nature de l'acte" et "Rédacteur" (CASSE ORIGINALE)
            entre_pattern = r"Nature de l'acte\s*:\s*(.+?)(?:\n|Rédacteur)"
            entre_match = re.search(entre_pattern, contenu, re.IGNORECASE | re.DOTALL)
            chaine_entre = entre_match.group(1).strip() if entre_match else "Non trouvé"
            
            # Extraire la date de dépôt (au début de la section)
            date_depot_pattern = r"(\d{2}/\d{2}/\d{4})"
            date_depot_match = re.search(date_depot_pattern, contenu)
            date_depot = date_depot_match.group(1) if date_depot_match else "Non trouvé"
            
            # Extraire la date de l'acte
            date_acte_pattern = r"Date de l'acte\s*:\s*(\d{2}/\d{2}/\d{4})"
            date_acte_match = re.search(date_acte_pattern, contenu, re.IGNORECASE)
            date_acte = date_acte_match.group(1) if date_acte_match else "Non trouvé"
            
            # Extraire la référence d'enliassement
            ref_enliassement = ""
            ref_match = re.search(r"Réference d'enliassement\s*:\s*([^\n]+)", contenu, re.IGNORECASE)
            if ref_match:
                ref_enliassement = ref_match.group(1).strip()
                # Nettoyer la référence en enlevant la partie "Date de l'acte" redondante
                ref_enliassement = re.sub(r'\s+Date de l\'acte\s*:\s*\d{2}/\d{2}/\d{4}', '', ref_enliassement)
            
            formalite = {
                "numero_ordre": i,
                "date_depot": date_depot,
                "date_acte": date_acte,
                "contenu": f"Date de depot: {contenu}",  # Remettre "Date de depot:" au début
                "nature_acte_redacteur": chaine_entre,
                "reference_enliassement": ref_enliassement
            }
            formalites.append(formalite)
    
    print(f"📋 {len(formalites)} formalités extraites")
    
    # Compter les types d'actes
    comptage_types = {}
    for formalite in formalites:
        nature_acte = formalite.get("nature_acte_redacteur", "").strip()  # GARDER LA CASSE ORIGINALE
        
        # Nettoyer et normaliser le type d'acte pour le comptage
        if nature_acte and nature_acte.upper() != "NON TROUVÉ":
            # Extraire les mots-clés principaux pour classifier les actes
            type_acte = classifier_type_acte(nature_acte)
            
            
            if type_acte in comptage_types:
                comptage_types[type_acte] += 1
            else:
                comptage_types[type_acte] = 1
    
    # Trier par nombre d'occurrences (décroissant)
    comptage_trie = dict(sorted(comptage_types.items(), key=lambda x: x[1], reverse=True))
    
    print(f"📊 Types d'actes détectés : {len(comptage_trie)}")
    for type_acte, count in comptage_trie.items():
        print(f"   - {type_acte}: {count}")
    
    # Analyser les hypothèques actives
    hypotheques_actives = analyser_hypotheques_actives(formalites)
    
    print(f"🏦 Hypothèques actives détectées : {len(hypotheques_actives)}")
    for hyp in hypotheques_actives:
        print(f"   - {hyp['date_depot']} : {hyp['nature_acte']}")
    
    # Analyser les mutations (formalités autres que hypothèques)
    mutations = analyser_mutations(formalites)
    
    print(f"🔄 Mutations détectées : {len(mutations)}")
    for mut in mutations:
        print(f"   - {mut['date_depot']} : {mut['nature_acte']} ({len(mut['mutations']['disposant_donateur'])} disposants → {len(mut['mutations']['beneficiaire_donataire'])} bénéficiaires)")
    
    return formalites, comptage_trie, hypotheques_actives, mutations

def analyser_hypotheques_actives(formalites):
    """
    Analyser les hypothèques pour identifier celles qui sont encore actives.
    Une hypothèque est active si elle n'a pas été radiée.
    """
    hypotheques = []
    radiations = []
    
    # Séparer les hypothèques et les radiations
    for formalite in formalites:
        nature_acte = formalite.get("nature_acte_redacteur", "").upper()
        contenu = formalite.get("contenu", "").upper()
        
        # Une radiation est un acte qui contient "RADIATION" et "TOTALE"
        if "RADIATION" in nature_acte and "TOTALE" in nature_acte:
            radiations.append(formalite)
        else:
            # Une hypothèque est détectée si ce n'est PAS une radiation ET :
            # 1. Contient "HYPOTHEQUE"
            # 2. OU contient à la fois "CRÉANCIERS" et ("DÉBITEUR" ou "PROPRIÉTAIRES IMMEUBLE")
            est_hypotheque_explicite = "HYPOTHEQUE" in nature_acte
            est_hypotheque_implicite = ("CRÉANCIERS" in contenu and 
                                       ("DÉBITEUR" in contenu or "PROPRIÉTAIRES IMMEUBLE" in contenu))
            
            if est_hypotheque_explicite or est_hypotheque_implicite:
                hypotheques.append(formalite)
                if est_hypotheque_implicite and not est_hypotheque_explicite:
                    print(f"   🔍 Hypothèque détectée par critère implicite : {nature_acte}")
    
    # Vérifier quelles hypothèques sont encore actives
    hypotheques_actives = []
    
    for hypotheque in hypotheques:
        date_depot_hyp = hypotheque.get("date_depot", "")
        nature_hyp = hypotheque.get("nature_acte_redacteur", "")
        
        # Chercher une radiation correspondante
        est_radiee = False
        
        for radiation in radiations:
            nature_rad = radiation.get("nature_acte_redacteur", "")
            
            # Vérifier si la date de l'hypothèque figure dans la radiation
            # et que les mots RADIATION et TOTALE sont présents
            if (date_depot_hyp in nature_rad and 
                "RADIATION" in nature_rad.upper() and 
                "TOTALE" in nature_rad.upper()):
                est_radiee = True
                break
        
        # Si l'hypothèque n'est pas radiée, elle est active
        if not est_radiee:
            # Extraire les lots et volumes depuis le contenu
            lots_volumes = extraire_lots_volumes_hypotheque(hypotheque.get("contenu", ""))
            
            hypotheques_actives.append({
                "numero_ordre": hypotheque.get("numero_ordre"),
                "date_depot": hypotheque.get("date_depot"),
                "date_acte": hypotheque.get("date_acte"),
                "nature_acte": hypotheque.get("nature_acte_redacteur"),
                "reference_enliassement": hypotheque.get("reference_enliassement", ""),
                "contenu": hypotheque.get("contenu"),
                "lots_volumes": lots_volumes,
                "statut": "ACTIVE"
            })
    
    return hypotheques_actives

def analyser_mutations(formalites):
    """
    Analyser les formalités pour extraire les mutations (autres que hypothèques).
    """
    mutations = []
    
    for formalite in formalites:
        nature_acte = formalite.get("nature_acte_redacteur", "").upper()
        
        # Analyser seulement les formalités qui ne sont pas des hypothèques
        if "HYPOTHEQUE" not in nature_acte and "RADIATION" not in nature_acte:
            contenu = formalite.get("contenu", "")
            mutations_data = extraire_mutations(contenu)
            
            # Ajouter seulement si des mutations ont été trouvées
            if (mutations_data.get("disposant_donateur") or 
                mutations_data.get("beneficiaire_donataire") or 
                mutations_data.get("immeubles")):
                
                mutations.append({
                    "numero_ordre": formalite.get("numero_ordre"),
                    "date_depot": formalite.get("date_depot"),
                    "date_acte": formalite.get("date_acte"),
                    "nature_acte": formalite.get("nature_acte_redacteur"),
                    "reference_enliassement": formalite.get("reference_enliassement", ""),
                    "mutations": mutations_data
                })
    
    return mutations

def reconstituer_propriete(mutations, immeubles):
    """
    Reconstituer la propriété actuelle en analysant les mutations par ordre chronologique.
    S'arrête quand tous les lots de l'immeuble de la dernière page sont attribués.
    """
    if not mutations or not immeubles:
        return []
    
    print(f"🔍 Analyse de {len(mutations)} mutations pour reconstituer la propriété")
    
    # Récupérer l'immeuble de référence (dernière page)
    immeuble_ref = immeubles[0]  # Premier immeuble extrait
    lots_immeuble = immeuble_ref.get('lot', [])
    
    # Gérer le cas où lot est une chaîne vide ou une liste
    if isinstance(lots_immeuble, str):
        lots_ref = set([lots_immeuble]) if lots_immeuble.strip() else set()
    else:
        lots_ref = set(lots_immeuble) if lots_immeuble else set()
    
    commune_ref = immeuble_ref['commune']
    designation_ref = immeuble_ref['designation_cadastrale']
    
    print(f"🏠 Immeuble de référence : {commune_ref} {designation_ref}")
    print(f"📋 Lots à reconstituer : {sorted(lots_ref) if lots_ref else 'Aucun lot spécifique'}")
    
    # Si pas de lots dans l'immeuble de référence, essayer de les extraire des mutations
    if not lots_ref:
        print("⚠️  Aucun lot dans l'immeuble de référence, extraction depuis les mutations...")
        for mutation in mutations:
            mut_data = mutation.get('mutations', {})
            immeubles_mut = mut_data.get('immeubles', {})
            if (immeubles_mut.get('commune', '').upper() in commune_ref.upper() and 
                immeubles_mut.get('designation_cadastrale', '') == designation_ref):
                lots_mutation = immeubles_mut.get('lots', [])
                lots_ref.update(lots_mutation)
        
        print(f"📋 Lots extraits des mutations : {sorted(lots_ref) if lots_ref else 'Aucun'}")
        
        if not lots_ref:
            # Dernière tentative : utiliser tous les lots trouvés dans les mutations pour cette commune
            print("🔍 Recherche de tous les lots dans les mutations pour cette commune...")
            for mutation in mutations:
                mut_data = mutation.get('mutations', {})
                immeubles_mut = mut_data.get('immeubles', {})
                if immeubles_mut.get('commune', '').upper() in commune_ref.upper():
                    lots_mutation = immeubles_mut.get('lots', [])
                    lots_ref.update(lots_mutation)
            
            if lots_ref:
                print(f"📋 Lots trouvés dans toutes les mutations : {sorted(lots_ref)}")
            else:
                print("ℹ️  Aucun lot spécifique trouvé, traitement de l'immeuble entier")
                # Ne pas retourner [] mais continuer avec lots_ref vide
                # La logique gérera le cas "IMMEUBLE_ENTIER"
    
    # Trier les mutations par date (plus récentes en premier)
    def convertir_date_pour_tri(date_str):
        """Convertir DD/MM/YYYY en YYYY-MM-DD pour tri chronologique correct"""
        try:
            if '/' in date_str:
                jour, mois, annee = date_str.split('/')
                return f"{annee}-{mois.zfill(2)}-{jour.zfill(2)}"
            return date_str
        except:
            return "0000-00-00"  # Date par défaut pour les erreurs
    
    mutations_triees = sorted(mutations, 
                             key=lambda x: convertir_date_pour_tri(x['date_depot']), 
                             reverse=True)
    
    print(f"📅 Mutations triées par date (plus récentes en premier)")
    
    # Debug : afficher l'ordre des dates après tri
    print("🔍 Ordre chronologique des mutations :")
    for i, mut in enumerate(mutations_triees):
        print(f"   {i+1}. {mut['date_depot']} - {mut['nature_acte'][:50]}...")
    
    # Structure pour suivre la propriété de chaque lot
    propriete_lots = {}  # lot_id -> {"proprietaire": {...}, "droits": "...", "date_acquisition": "..."}
    
    # Itérer sur les mutations triées
    for i, mutation in enumerate(mutations_triees):
        print(f"\n📄 Mutation {i+1}/{len(mutations_triees)} - {mutation['date_depot']} : {mutation['nature_acte']}")
        
        mut_data = mutation.get('mutations', {})
        immeubles_mut = mut_data.get('immeubles', {})
        
        # Vérifier si cette mutation concerne notre immeuble de référence
        # Si pas d'immeubles dans la mutation, considérer qu'elle concerne l'immeuble de référence
        concerne_immeuble = False
        if immeubles_mut.get('commune') and immeubles_mut.get('designation_cadastrale'):
            # Cas normal : comparaison avec les données de la mutation
            concerne_immeuble = (immeubles_mut.get('commune', '').upper() in commune_ref.upper() and 
                                immeubles_mut.get('designation_cadastrale', '') == designation_ref)
        else:
            # Cas où les immeubles de la mutation sont vides : considérer que ça concerne l'immeuble de référence
            concerne_immeuble = True
            print(f"   ℹ️  Pas d'immeubles spécifiés dans la mutation, considère l'immeuble de référence")
        
        if concerne_immeuble:
            
            lots_mutation = set(immeubles_mut.get('lots', []))
            
            # Si pas de lots spécifiques (ni dans référence ni dans mutation), considérer que ça concerne l'immeuble entier
            if not lots_ref and not lots_mutation:
                lots_concernes = {'IMMEUBLE_ENTIER'}  # Marqueur pour immeuble sans lots
                print(f"   ✅ Concerne l'immeuble entier : {designation_ref}")
            else:
                lots_concernes = lots_ref.intersection(lots_mutation)
                if lots_concernes:
                    print(f"   ✅ Concerne les lots : {sorted(lots_concernes)}")
            
            if lots_concernes:
                # Identifier les bénéficiaires avec leurs droits spécifiques
                beneficiaires = mut_data.get('beneficiaire_donataire', [])
                lignes_detaillees = immeubles_mut.get('lignes_detaillees', [])
                
                if beneficiaires and lignes_detaillees:
                    # Associer chaque ligne d'immeuble avec le bon bénéficiaire
                    for ligne_immeuble in lignes_detaillees:
                        numero_beneficiaire = ligne_immeuble.get('beneficiaire_numero', '')
                        droits_ligne = ligne_immeuble.get('droits', '')
                        lots_ligne = set(ligne_immeuble.get('lots', []))
                        
                        # Gérer le cas sans lots spécifiques
                        if 'IMMEUBLE_ENTIER' in lots_concernes:
                            lots_ligne_concernes = {'IMMEUBLE_ENTIER'}
                        else:
                            lots_ligne_concernes = lots_concernes.intersection(lots_ligne)
                        
                        if lots_ligne_concernes:
                            # Trouver le bénéficiaire correspondant
                            beneficiaire_correspondant = None
                            for beneficiaire in beneficiaires:
                                if beneficiaire.get('numero', '') == numero_beneficiaire:
                                    beneficiaire_correspondant = beneficiaire
                                    break
                            
                            if beneficiaire_correspondant:
                                # Attribuer la propriété aux lots concernés
                                for lot in lots_ligne_concernes:
                                    if lot not in propriete_lots:  # Première attribution (plus récente)
                                        propriete_lots[lot] = {
                                            "proprietaire": {
                                                "designation": beneficiaire_correspondant.get('designation', ''),
                                                "date_naissance": beneficiaire_correspondant.get('date_naissance', ''),
                                                "numero": beneficiaire_correspondant.get('numero', '')
                                            },
                                            "droits": droits_ligne,
                                            "date_acquisition": mutation['date_depot'],
                                            "nature_acte": mutation['nature_acte'],
                                            "numero_ordre_mutation": mutation['numero_ordre']
                                        }
                                        if lot == 'IMMEUBLE_ENTIER':
                                            print(f"      → Immeuble entier attribué à {beneficiaire_correspondant.get('designation', '')} ({beneficiaire_correspondant.get('date_naissance', '')}) - {droits_ligne}")
                                        else:
                                            print(f"      → Lot {lot} attribué à {beneficiaire_correspondant.get('designation', '')} ({beneficiaire_correspondant.get('date_naissance', '')}) - {droits_ligne}")
                elif beneficiaires:
                    # Fallback : utiliser la méthode simple si pas de lignes détaillées
                    beneficiaire = beneficiaires[0]  # Premier bénéficiaire
                    droits = immeubles_mut.get('droits', '')
                    
                    # Attribuer la propriété aux lots concernés
                    for lot in lots_concernes:
                        if lot not in propriete_lots:  # Première attribution (plus récente)
                            propriete_lots[lot] = {
                                "proprietaire": {
                                    "designation": beneficiaire.get('designation', ''),
                                    "date_naissance": beneficiaire.get('date_naissance', ''),
                                    "numero": beneficiaire.get('numero', '')
                                },
                                "droits": droits,
                                "date_acquisition": mutation['date_depot'],
                                "nature_acte": mutation['nature_acte'],
                                "numero_ordre_mutation": mutation['numero_ordre']
                            }
                            if lot == 'IMMEUBLE_ENTIER':
                                print(f"      → Immeuble entier attribué à {beneficiaire.get('designation', '')} ({droits})")
                            else:
                                print(f"      → Lot {lot} attribué à {beneficiaire.get('designation', '')} ({droits})")
            else:
                print(f"   ❌ Ne concerne pas les lots de référence")
        else:
            print(f"   ❌ Ne concerne pas l'immeuble de référence")
        
        # Vérifier si tous les lots sont attribués
        lots_attribues = set(propriete_lots.keys())
        if lots_ref and lots_attribues == lots_ref:
            print(f"\n🎉 Tous les lots sont attribués ! Arrêt de l'analyse.")
            break
        elif not lots_ref and 'IMMEUBLE_ENTIER' in lots_attribues:
            print(f"\n🎉 Immeuble entier attribué ! Arrêt de l'analyse.")
            break
    
    # Construire le résultat final
    propriete_actuelle = []
    
    if propriete_lots:
        # Grouper par propriétaire
        proprietaires = {}
        for lot, info in propriete_lots.items():
            prop_key = f"{info['proprietaire']['designation']}_{info['proprietaire']['date_naissance']}"
            if prop_key not in proprietaires:
                proprietaires[prop_key] = {
                    "proprietaire": info['proprietaire'],
                    "lots": [],
                    "droits": info['droits'],
                    "date_acquisition_plus_recente": info['date_acquisition']
                }
            proprietaires[prop_key]['lots'].append(lot)
            # Garder la date la plus récente
            if info['date_acquisition'] > proprietaires[prop_key]['date_acquisition_plus_recente']:
                proprietaires[prop_key]['date_acquisition_plus_recente'] = info['date_acquisition']
        
        # Convertir en liste
        for prop_info in proprietaires.values():
            # Gérer le cas IMMEUBLE_ENTIER
            if 'IMMEUBLE_ENTIER' in prop_info['lots']:
                lots_finaux = ['Immeuble entier']
            else:
                lots_finaux = sorted([lot for lot in prop_info['lots'] if lot != 'IMMEUBLE_ENTIER'])
            
            propriete_actuelle.append({
                "immeuble": {
                    "commune": commune_ref,
                    "designation_cadastrale": designation_ref,
                    "code": immeuble_ref.get('code', '')
                },
                "proprietaire": prop_info['proprietaire'],
                "lots": lots_finaux,
                "droits": prop_info['droits'],
                "date_acquisition": prop_info['date_acquisition_plus_recente']
            })
    
    # Identifier les lots non attribués
    lots_non_attribues = lots_ref - set(propriete_lots.keys())
    if lots_non_attribues:
        print(f"\n⚠️  Lots non attribués : {sorted(lots_non_attribues)}")
        propriete_actuelle.append({
            "immeuble": {
                "commune": commune_ref,
                "designation_cadastrale": designation_ref,
                "code": immeuble_ref.get('code', '')
            },
            "proprietaire": {
                "designation": "PROPRIETAIRE INCONNU",
                "date_naissance": "",
                "numero": ""
            },
            "lots": sorted(lots_non_attribues),
            "droits": "INCONNU",
            "date_acquisition": ""
        })
    
    print(f"\n📊 Propriété reconstituée : {len(propriete_actuelle)} propriétaire(s)")
    for prop in propriete_actuelle:
        print(f"   - {prop['proprietaire']['designation']} : lots {prop['lots']} ({prop['droits']})")
    
    return propriete_actuelle

def extraire_mutations(contenu: str) -> dict:
    """
    Extraire les informations de mutation (Disposant/Donateur, Bénéficiaire/Donataire, Immeubles)
    pour les formalités autres que les hypothèques.
    """
    import re
    
    if not contenu:
        return {}
    
    mutations = {
        "disposant_donateur": [],
        "beneficiaire_donataire": [],
        "immeubles": {}
    }
    
    try:
        # 1. Extraire les Disposants/Donateurs
        disposant_patterns = [
            r"Disposant[,\s]*Donateur\s*.*?Numéro\s+Désignation des personnes\s+Date de naissance.*?\n(.*?)(?=\n\s*Bénéficiaire|\n\s*Immeubles|$)",
            r"Disposant\s*.*?Numéro\s+Désignation des personnes\s+Date de naissance.*?\n(.*?)(?=\n\s*Bénéficiaire|\n\s*Immeubles|$)",
            r"Donateur\s*.*?Numéro\s+Désignation des personnes\s+Date de naissance.*?\n(.*?)(?=\n\s*Bénéficiaire|\n\s*Immeubles|$)"
        ]
        
        for pattern in disposant_patterns:
            disposant_match = re.search(pattern, contenu, re.IGNORECASE | re.DOTALL)
            if disposant_match:
                disposant_text = disposant_match.group(1).strip()
                # Extraire les lignes avec numéro, nom, date (plus flexible pour gérer apostrophes et espaces)
                lignes_disposant = re.findall(r'(\d+)\s+([A-Z\'][A-Z\s\']+?)\s+(\d{2}/\d{2}/\d{4}|\d{3}\s+\d{3}\s+\d{3})', disposant_text)
                for numero, nom, date_naissance in lignes_disposant:
                    mutations["disposant_donateur"].append({
                        "numero": numero.strip(),
                        "designation": nom.strip(),
                        "date_naissance": date_naissance.strip()
                    })
                break
        
        # Si pas trouvé avec les patterns standards, essayer une approche plus simple
        if not mutations["disposant_donateur"]:
            # Chercher "Disposant" suivi de données tabulaires
            simple_disposant = re.search(r"Disposant.*?\n.*?(\d+)\s+([A-Z\'][A-Z\s\']+?)\s+(\d{2}/\d{2}/\d{4}|\d{3}\s+\d{3}\s+\d{3})", contenu, re.IGNORECASE | re.DOTALL)
            if simple_disposant:
                mutations["disposant_donateur"].append({
                    "numero": simple_disposant.group(1).strip(),
                    "designation": simple_disposant.group(2).strip(),
                    "date_naissance": simple_disposant.group(3).strip()
                })
        
        # 2. Extraire les Bénéficiaires/Donataires
        beneficiaire_patterns = [
            r"Bénéficiaire[,\s]*Donataire\s*.*?Numéro\s+Désignation des personnes\s+Date de naissance.*?\n(.*?)(?=\n\s*Immeubles|$)",
            r"Bénéficiaire\s*.*?Numéro\s+Désignation des personnes\s+Date de naissance.*?\n(.*?)(?=\n\s*Immeubles|$)",
            r"Donataire\s*.*?Numéro\s+Désignation des personnes\s+Date de naissance.*?\n(.*?)(?=\n\s*Immeubles|$)"
        ]
        
        for pattern in beneficiaire_patterns:
            beneficiaire_match = re.search(pattern, contenu, re.IGNORECASE | re.DOTALL)
            if beneficiaire_match:
                beneficiaire_text = beneficiaire_match.group(1).strip()
                # Extraire les lignes avec numéro, nom, date (plus flexible)
                lignes_beneficiaire = re.findall(r'(\d+)\s+([A-Z\'][A-Z\s\']+?)\s+(\d{2}/\d{2}/\d{4}|\d{3}\s+\d{3}\s+\d{3})', beneficiaire_text)
                for numero, nom, date_ou_siret in lignes_beneficiaire:
                    mutations["beneficiaire_donataire"].append({
                        "numero": numero.strip(),
                        "designation": nom.strip(),
                        "date_naissance": date_ou_siret.strip()
                    })
                break
        
        # Si pas trouvé avec les patterns standards, essayer une approche plus simple
        if not mutations["beneficiaire_donataire"]:
            # Chercher "Bénéficiaire" suivi de données tabulaires
            simple_beneficiaire = re.search(r"Bénéficiaire.*?\n.*?(\d+)\s+([A-Z\'][A-Z\s\']+?)\s+(\d{2}/\d{2}/\d{4}|\d{3}\s+\d{3}\s+\d{3})", contenu, re.IGNORECASE | re.DOTALL)
            if simple_beneficiaire:
                mutations["beneficiaire_donataire"].append({
                    "numero": simple_beneficiaire.group(1).strip(),
                    "designation": simple_beneficiaire.group(2).strip(),
                    "date_naissance": simple_beneficiaire.group(3).strip()
                })
        
        # 3. Extraire le tableau Immeubles
        immeubles_patterns = [
            # Pattern 1: Format standard avec en-têtes complets
            r"Immeubles\s*.*?Bénéficiaires\s+Droits\s+Commune\s+Désignation cadastrale\s+Volume\s+Lot\s*\n(.*?)(?=\n\s*US\s*:|$)",
            # Pattern 2: Format simplifié (comme dans EHF8)
            r"Immeubles\s*\n\s*Bénéficiaires\s+Droits\s+Commune\s+Désignation cadastrale\s+Volume\s+Lot\s*\n(.*?)(?=\n\s*[A-Z]{2,}\s*:|$)"
        ]
        
        immeubles_text = ""
        for pattern in immeubles_patterns:
            immeubles_match = re.search(pattern, contenu, re.IGNORECASE | re.DOTALL)
            if immeubles_match:
                immeubles_text = immeubles_match.group(1).strip()
                break
        
        if immeubles_text:
            # Extraire toutes les lignes du tableau immeubles
            lignes_immeubles = []
            
            # Patterns pour extraire les lignes individuelles
            ligne_patterns = [
                # Pattern 1: Format standard avec lots sur lignes séparées
                r'(\d+(?:\s+à\s+\d+)?)\s+([A-Z/]{1,3})\s+([A-Z\s\d]+?)\s+([A-Z]{1,3}\s*\d+)\s*\n((?:\s*\d+\s*\n?)*)',
                # Pattern 2: Format avec droits longs (US, NI, TP, etc.)
                r'(\d+(?:\s+à\s+\d+)?)\s+([A-Z]{2,})\s+([A-Z\s\d]+?)\s+([A-Z]{1,3}\s*\d+)\s*\n((?:\s*\d+\s*\n?)*)'
            ]
            
            # Chercher toutes les lignes du tableau
            for ligne_pattern in ligne_patterns:
                matches = re.finditer(ligne_pattern, immeubles_text, re.MULTILINE)
                for match in matches:
                    numero_beneficiaire = match.group(1).strip()
                    droits = match.group(2).strip()
                    commune = match.group(3).strip()
                    designation_cadastrale = match.group(4).strip()
                    lots_text = match.group(5) if match.group(5) else ""
                    
                    # Extraire les lots
                    lots = re.findall(r'\d+', lots_text) if lots_text else []
                    
                    lignes_immeubles.append({
                        "beneficiaire_numero": numero_beneficiaire,
                        "droits": droits,
                        "commune": commune,
                        "designation_cadastrale": designation_cadastrale,
                        "volume": "",
                        "lots": lots
                    })
                
                if lignes_immeubles:
                    break
            
            # Si on a trouvé des lignes, garder la structure détaillée
            if lignes_immeubles:
                # Prendre la première ligne comme référence principale
                premiere_ligne = lignes_immeubles[0]
                
                # Fusionner tous les lots de toutes les lignes pour la recherche
                tous_les_lots = []
                for ligne in lignes_immeubles:
                    tous_les_lots.extend(ligne["lots"])
                
                mutations["immeubles"] = {
                    "beneficiaire_numero": premiere_ligne["beneficiaire_numero"],
                    "droits": premiere_ligne["droits"],  # Garder les droits de la première ligne
                    "commune": premiere_ligne["commune"],
                    "designation_cadastrale": premiere_ligne["designation_cadastrale"],
                    "volume": "",
                    "lots": list(dict.fromkeys(tous_les_lots)),  # Tous les lots pour la recherche
                    "lignes_detaillees": lignes_immeubles  # Détail complet pour analyse fine
                }
        
        # 4. Extraire le montant/prix
        montant_patterns = [
            r"Prix/évaluation\s*:\s*([0-9\s,\.]+\s*EUR)",
            r"Prix\s*:\s*([0-9\s,\.]+\s*EUR)",
            r"Évaluation\s*:\s*([0-9\s,\.]+\s*EUR)",
            r"Montant\s*:\s*([0-9\s,\.]+\s*EUR)"
        ]
        
        for pattern in montant_patterns:
            montant_match = re.search(pattern, contenu, re.IGNORECASE)
            if montant_match:
                mutations["montant"] = montant_match.group(1).strip()
                break
        
        if "montant" not in mutations:
            mutations["montant"] = ""
    
    except Exception as e:
        print(f"⚠️  Erreur lors de l'extraction des mutations: {e}")
    
    return mutations

def extraire_lots_volumes_hypotheque(contenu: str) -> dict:
    """
    Extraire les lots et volumes concernés par l'hypothèque depuis le contenu.
    Analyse le tableau "Immeubles" dans le contenu de la formalité.
    """
    import re
    
    if not contenu:
        return {"lots": [], "volume": "", "commune": "", "designation_cadastrale": ""}
    
    # Initialiser les résultats
    lots = []
    volume = ""
    commune = ""
    designation_cadastrale = ""
    
    try:
        # Chercher la section "Immeubles" dans le contenu
        # Pattern pour trouver la section immeubles jusqu'au montant
        immeubles_pattern = r"Immeubles\s*.*?(?=\n\s*Montant|$)"
        immeubles_match = re.search(immeubles_pattern, contenu, re.IGNORECASE | re.DOTALL)
        
        if immeubles_match:
            section_immeubles = immeubles_match.group(0)
            
            # Méthode 1: Chercher le pattern "COMMUNE DESIGNATION\nNUMEROS"
            # Exemple: "PARIS 15 CJ 42\n17\n57"
            pattern_commune_designation = r"([A-Z][A-Z\s\d]+?)\s+([A-Z]{1,3}\s*\d+)\s*\n((?:\s*\d+\s*\n?)+)"
            match_commune_designation = re.search(pattern_commune_designation, section_immeubles)
            
            if match_commune_designation:
                commune = match_commune_designation.group(1).strip()
                designation_cadastrale = match_commune_designation.group(2).strip()
                lots_text = match_commune_designation.group(3)
                lots = re.findall(r'\d+', lots_text)
            else:
                # Méthode 2: Chercher séparément
                # Extraire la commune (patterns comme "PARIS 15", "VANVES")
                commune_patterns = [
                    r"([A-Z][A-Z\s\d]+?)\s+[A-Z]{1,3}\s+\d+",  # "PARIS 15 CJ 42"
                    r"Commune[:\s]*([A-Z][A-Z\s\d]+)",  # "Commune: VANVES"
                ]
                
                for pattern in commune_patterns:
                    commune_match = re.search(pattern, section_immeubles, re.IGNORECASE)
                    if commune_match:
                        commune = commune_match.group(1).strip()
                        break
                
                # Extraire la désignation cadastrale (patterns comme "CJ 42", "O 32")
                designation_patterns = [
                    r"([A-Z]{1,3}\s*\d+)(?:\s*\n|\s*$)",  # "CJ 42" suivi d'un saut de ligne
                    r"cadastrale[:\s]*([A-Z]{1,3}\s*\d+)",  # "cadastrale: CJ 42"
                ]
                
                for pattern in designation_patterns:
                    designation_match = re.search(pattern, section_immeubles, re.IGNORECASE)
                    if designation_match:
                        designation_cadastrale = designation_match.group(1).strip()
                        break
                
                # Extraire les lots (numéros isolés après la désignation)
                if designation_cadastrale:
                    # Chercher après la désignation cadastrale
                    after_designation = section_immeubles.split(designation_cadastrale, 1)
                    if len(after_designation) > 1:
                        remaining_text = after_designation[1]
                        # Chercher les numéros isolés sur des lignes séparées
                        lots = re.findall(r'^\s*(\d+)\s*$', remaining_text, re.MULTILINE)
            
            # Extraire le volume s'il existe (rare mais possible)
            volume_pattern = r"Volume[:\s]*(\d+|[A-Z]\d+)"
            volume_match = re.search(volume_pattern, section_immeubles, re.IGNORECASE)
            if volume_match:
                volume = volume_match.group(1).strip()
        
        # Nettoyer et valider les résultats
        lots = [lot.strip() for lot in lots if lot.strip().isdigit()]
        lots = list(dict.fromkeys(lots))  # Supprimer les doublons en gardant l'ordre
        
        # Debug pour comprendre ce qui se passe
        if not lots and "Immeubles" in contenu:
            print(f"🔍 DEBUG - Section immeubles trouvée mais pas de lots extraits")
            print(f"🔍 DEBUG - Commune: '{commune}', Designation: '{designation_cadastrale}'")
        
    except Exception as e:
        print(f"⚠️  Erreur lors de l'extraction des lots/volumes: {e}")
    
    # Extraire les informations financières après le tableau immeubles
    montant_principal = ""
    accessoires = ""
    taux_interet = ""
    date_extreme_exigibilite = ""
    date_extreme_effet = ""
    complement = ""
    
    try:
        # Chercher les informations financières après "Montant principal"
        montant_pattern = r"Montant principal\s*:\s*([\d\s,\.]+\s*EUR)"
        montant_match = re.search(montant_pattern, contenu, re.IGNORECASE)
        if montant_match:
            montant_principal = montant_match.group(1).strip()
        
        # Accessoires
        accessoires_pattern = r"Accessoires\s*:\s*([\d\s,\.]+\s*EUR)"
        accessoires_match = re.search(accessoires_pattern, contenu, re.IGNORECASE)
        if accessoires_match:
            accessoires = accessoires_match.group(1).strip()
        
        # Taux d'intérêt
        taux_pattern = r"Taux d'intérêt\s*:\s*([\d,\.]+\s*%)"
        taux_match = re.search(taux_pattern, contenu, re.IGNORECASE)
        if taux_match:
            taux_interet = taux_match.group(1).strip()
        
        # Date d'extrême exigibilité
        exigibilite_pattern = r"Date d'extrême exigibilité\s*:\s*(\d{2}/\d{2}/\d{4})"
        exigibilite_match = re.search(exigibilite_pattern, contenu, re.IGNORECASE)
        if exigibilite_match:
            date_extreme_exigibilite = exigibilite_match.group(1).strip()
        
        # Date d'extrême effet
        effet_pattern = r"Date d'extrême effet\s*:\s*(\d{2}/\d{2}/\d{4})"
        effet_match = re.search(effet_pattern, contenu, re.IGNORECASE)
        if effet_match:
            date_extreme_effet = effet_match.group(1).strip()
        
        # Complément (après "Complément :" jusqu'à "Disposition" ou fin de formalité)
        complement_pattern = r"Complément\s*:\s*(.*?)(?=\n\s*Disposition|\n\s*\d+\s*/\s*\d+\s*Demande|$)"
        complement_match = re.search(complement_pattern, contenu, re.IGNORECASE | re.DOTALL)
        if complement_match:
            complement = complement_match.group(1).strip()
            # Nettoyer le complément (supprimer les sauts de ligne excessifs)
            complement = re.sub(r'\n+', ' ', complement).strip()
    
    except Exception as e:
        print(f"⚠️  Erreur lors de l'extraction des informations financières: {e}")
    
    return {
        "lots": lots,
        "volume": volume,
        "commune": commune,
        "designation_cadastrale": designation_cadastrale,
        "montant_principal": montant_principal,
        "accessoires": accessoires,
        "taux_interet": taux_interet,
        "date_extreme_exigibilite": date_extreme_exigibilite,
        "date_extreme_effet": date_extreme_effet,
        "complement": complement
    }

def classifier_type_acte(nature_acte: str) -> str:
    """
    Extraire le type d'acte en prenant tout ce qui est avant "de la formalité" 
    s'il existe, sinon prendre tout le contenu de nature_acte_redacteur.
    """
    import re
    nature_acte_original = nature_acte.strip()
    
    # Chercher "de la formalité" (avec variations possibles)
    patterns_formalite = [
        r'\s+de\s+la\s+formalité',
        r'\s+de\s+la\s+formalite', 
        r'\s+DE\s+LA\s+FORMALITÉ',
        r'\s+DE\s+LA\s+FORMALITE'
    ]
    
    for pattern in patterns_formalite:
        match = re.search(pattern, nature_acte_original, re.IGNORECASE)
        if match:
            # Extraire tout ce qui est avant "de la formalité"
            type_acte = nature_acte_original[:match.start()].strip()
            return type_acte if type_acte else nature_acte_original
    
    # Si "de la formalité" n'est pas trouvé, retourner tout le contenu
    return nature_acte_original

def extract_tableau_derniere_page(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extraire le tableau des immeubles de la dernière page uniquement.
    """
    
    print(f"🏠 Extraction du tableau de la dernière page depuis : {pdf_path}")
    
    immeubles = []
    
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        last_page = pdf.pages[-1]
        page_num = total_pages
        
        print(f"🔍 Analyse de la dernière page ({page_num}) sur {total_pages}")
        
        # Configuration spécifique pour détecter les tableaux
        table_settings = {
            "vertical_strategy": "lines_strict",
            "horizontal_strategy": "lines_strict",
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "edge_min_length": 3,
            "min_words_vertical": 1,
            "min_words_horizontal": 1,
        }
        
        tables = last_page.extract_tables(table_settings)
        
        for table in tables:
            if not table:
                continue
            
            # Chercher une table qui ressemble au tableau des immeubles
            for row_idx, row in enumerate(table):
                if not row:
                    continue
                
                # Vérifier si c'est la ligne d'en-tête
                row_text = ' '.join(str(cell) for cell in row if cell)
                if any(keyword in row_text.upper() for keyword in ["CODE", "COMMUNE", "DESIGNATION"]):
                    print(f"📋 En-têtes trouvés à la ligne {row_idx}: {row}")
                    
                    # Extraire les données suivantes
                    for data_row_idx in range(row_idx + 1, len(table)):
                        data_row = table[data_row_idx]
                        if not data_row or not any(cell for cell in data_row):
                            continue
                        
                        # Mapper les colonnes
                        immeuble = {
                            "code": str(data_row[0]).strip() if len(data_row) > 0 and data_row[0] else "",
                            "commune": str(data_row[1]).strip() if len(data_row) > 1 and data_row[1] else "",
                            "designation_cadastrale": str(data_row[2]).strip() if len(data_row) > 2 and data_row[2] else "",
                            "volume": str(data_row[3]).strip() if len(data_row) > 3 and data_row[3] else "",
                            "lot": str(data_row[4]).strip() if len(data_row) > 4 and data_row[4] else "",
                            "_page": page_num
                        }
                        
                        # Traitement spécial pour les lots multiples (ex: "9\n17\n35\n57")
                        if immeuble["lot"] and '\n' in immeuble["lot"]:
                            lots = [l.strip() for l in immeuble["lot"].split('\n') if l.strip()]
                            immeuble["lot"] = lots  # Garder comme liste pour plus de clarté
                        
                        # Traitement spécial pour les volumes multiples avec plages (ex: "57\n71 à 72")
                        if immeuble["volume"] and '\n' in immeuble["volume"]:
                            volume_parts = [v.strip() for v in immeuble["volume"].split('\n') if v.strip()]
                            processed_volumes = []
                            
                            for volume_part in volume_parts:
                                # Vérifier s'il y a une plage (ex: "71 à 72")
                                if ' à ' in volume_part:
                                    # Extraire les nombres de la plage
                                    parts = volume_part.split(' à ')
                                    if len(parts) == 2:
                                        try:
                                            start = int(parts[0].strip())
                                            end = int(parts[1].strip())
                                            # Générer tous les nombres de la plage
                                            for num in range(start, end + 1):
                                                processed_volumes.append(str(num))
                                        except ValueError:
                                            # Si conversion échoue, garder tel quel
                                            processed_volumes.append(volume_part)
                                    else:
                                        processed_volumes.append(volume_part)
                                else:
                                    processed_volumes.append(volume_part)
                            
                            immeuble["volume"] = processed_volumes  # Liste des volumes individuels
                        
                        # Ne garder que les lignes avec au moins un code ou une commune
                        if immeuble["code"] or immeuble["commune"]:
                            immeubles.append(immeuble)
                            print(f"🏠 Immeuble extrait : {immeuble}")
    
    print(f"🏠 {len(immeubles)} immeubles extraits de la dernière page")
    return immeubles

def extraction_complete_ehf(pdf_path: str, output_dir: str = "extractions") -> Dict[str, str]:
    """
    Extraction complète d'un EHF : formalités + tableau dernière page.
    
    Args:
        pdf_path: Chemin vers le PDF EHF
        output_dir: Dossier de sortie pour les fichiers JSON
    
    Returns:
        Dictionnaire avec les chemins des fichiers générés
    """
    
    print(f"🚀 EXTRACTION COMPLÈTE EHF")
    print(f"📄 Fichier source : {pdf_path}")
    print("=" * 80)
    
    # Créer le dossier de sortie
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Nom de base pour les fichiers de sortie
    pdf_name = Path(pdf_path).stem
    
    # 1. Extraire les formalités
    print("\n📋 ÉTAPE 1: Extraction des formalités")
    print("-" * 50)
    
    formalites, comptage_types, hypotheques_actives, mutations = extract_formalites_from_pdf(pdf_path)
    
    # Créer la structure finale avec formalités + statistiques + hypothèques actives + mutations
    structure_finale = {
        "formalites": formalites,
        "hypotheques_actives": hypotheques_actives,
        "mutations": mutations,
        "statistiques": {
            "nombre_total_formalites": len(formalites),
            "nombre_hypotheques_actives": len(hypotheques_actives),
            "nombre_mutations": len(mutations),
            "comptage_par_type": comptage_types,
            "date_extraction": "2024-10-30",  # Date actuelle
            "fichier_source": pdf_name
        }
    }
    
    # Sauvegarder les formalités avec statistiques
    formalites_file = output_path / f"{pdf_name}_formalites.json"
    with open(formalites_file, 'w', encoding='utf-8') as f:
        json.dump(structure_finale, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Formalités avec statistiques sauvegardées : {formalites_file}")
    
    # 2. Extraire le tableau de la dernière page
    print("\n🏠 ÉTAPE 2: Extraction du tableau de la dernière page")
    print("-" * 50)
    
    immeubles = extract_tableau_derniere_page(pdf_path)
    
    # Sauvegarder les immeubles
    immeubles_file = output_path / f"{pdf_name}_immeubles_derniere_page.json"
    with open(immeubles_file, 'w', encoding='utf-8') as f:
        json.dump(immeubles, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Immeubles sauvegardés : {immeubles_file}")
    
    # 3. Résumé
    print("\n📊 RÉSUMÉ DE L'EXTRACTION")
    print("=" * 80)
    print(f"📋 Formalités extraites : {len(formalites)}")
    print(f"🏠 Immeubles extraits : {len(immeubles)}")
    print(f"📁 Fichiers générés dans : {output_path}")
    
    # Afficher quelques exemples
    if formalites:
        print(f"\n📋 Exemple de formalité :")
        exemple_formalite = formalites[0]
        print(f"   - Numéro ordre : {exemple_formalite['numero_ordre']}")
        print(f"   - Date dépôt : {exemple_formalite['date_depot']}")
        print(f"   - Date acte : {exemple_formalite['date_acte']}")
        print(f"   - Nature acte : {exemple_formalite['nature_acte_redacteur'][:50]}...")
    
    if comptage_types:
        print(f"\n📊 Top 3 des types d'actes :")
        for i, (type_acte, count) in enumerate(list(comptage_types.items())[:3]):
            print(f"   {i+1}. {type_acte}: {count} formalité(s)")
    
    if hypotheques_actives:
        print(f"\n🏦 Hypothèques actives :")
        for hyp in hypotheques_actives[:3]:  # Afficher les 3 premières
            print(f"   - {hyp['date_depot']} : {hyp['nature_acte'][:50]}...")
    
    if mutations:
        print(f"\n🔄 Mutations :")
        for mut in mutations[:3]:  # Afficher les 3 premières
            print(f"   - {mut['date_depot']} : {mut['nature_acte'][:50]}...")
    
    if immeubles:
        print(f"\n🏠 Exemple d'immeuble :")
        exemple_immeuble = immeubles[0]
        print(f"   - Code : {exemple_immeuble['code']}")
        print(f"   - Commune : {exemple_immeuble['commune']}")
        print(f"   - Désignation : {exemple_immeuble['designation_cadastrale']}")
        print(f"   - Volume : {exemple_immeuble['volume']}")
        print(f"   - Lot : {exemple_immeuble['lot']}")
    
    # 3. Reconstituer la propriété actuelle des immeubles
    print("\n🏗️ ÉTAPE 3: Reconstitution de la propriété")
    print("-" * 50)
    
    propriete_actuelle = reconstituer_propriete(mutations, immeubles)
    
    # Ajouter la propriété reconstituée à la structure finale
    structure_finale["propriete_actuelle"] = propriete_actuelle
    structure_finale["statistiques"]["propriete_reconstituee"] = len(propriete_actuelle) > 0
    
    # Re-sauvegarder avec la propriété
    with open(formalites_file, 'w', encoding='utf-8') as f:
        json.dump(structure_finale, f, ensure_ascii=False, indent=2)
    
    return {
        "formalites_file": str(formalites_file),
        "immeubles_file": str(immeubles_file),
        "nb_formalites": len(formalites),
        "nb_immeubles": len(immeubles),
        "nb_hypotheques_actives": len(hypotheques_actives),
        "nb_mutations": len(mutations),
        "comptage_types": comptage_types,
        "hypotheques_actives": hypotheques_actives,
        "mutations": mutations,
        "propriete_actuelle": propriete_actuelle
    }

def main():
    """Fonction principale."""
    
    # Chemin vers le PDF à analyser
    pdf_path = "EHFs/EHF8.pdf"  # Remplace par ton fichier
    
    if not Path(pdf_path).exists():
        print(f"❌ Fichier non trouvé : {pdf_path}")
        print("📝 Fichiers disponibles dans EHFs/:")
        ehf_dir = Path("EHFs")
        if ehf_dir.exists():
            for file in ehf_dir.glob("*.pdf"):
                print(f"   - {file.name}")
        return
    
    try:
        # Lancer l'extraction complète
        resultats = extraction_complete_ehf(pdf_path, output_dir="extractions_ehf")
        
        print(f"\n🎉 EXTRACTION TERMINÉE AVEC SUCCÈS !")
        print(f"📋 Formalités : {resultats['formalites_file']}")
        print(f"🏠 Immeubles : {resultats['immeubles_file']}")
        
    except Exception as e:
        print(f"❌ Erreur lors de l'extraction : {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
