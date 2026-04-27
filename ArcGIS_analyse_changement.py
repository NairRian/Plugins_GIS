# -*- coding: utf-8 -*-
# Développé par Raphaëlle Camphuis 
# Objectif : Effectuer un traitement ArcGIS pour analyser quantitativement la reprise de atelier vecteur sur des vecteurs extraits par IA

import arcpy
import csv

class Toolbox(object):
	def __init__(self):
		"""Define the toolbox (the name of the toolbox is the name of the
		.pyt file)."""
		self.label = "Toolbox"
		self.alias = "toolbox"

		# List of tool classes associated with this toolbox
		self.tools = [Tool]


class Tool(object):
	def __init__(self):
		"""Define the tool (tool name is the name of the class)."""
		self.label = "Analyse de changement"
		self.description = ""
		self.canRunInBackground = False

	def getParameterInfo(self):
		"""Define parameter definitions"""
		params = [arcpy.Parameter("lieu", "Nom de la ville", "Input", "GPString", "Required"),
				  arcpy.Parameter("Iteration", "Itération de l'outil n° ?", "Input", "GPLong", "Required"),
				  arcpy.Parameter("batv1", "Bâtiments version 1", "input", "GPFeatureLayer", "Required"),
				  arcpy.Parameter("batv2", "Bâtiments version 2", "input", "GPFeatureLayer", "Required"),
				  arcpy.Parameter("sc", "Système de coordonnées PROJETE", "Input", "GPCoordinateSystem", "Required"),
				  arcpy.Parameter("chemin", "Chemin de sortie des fichiers de statistiques", "Input", "DEFolder", "Required"),
				  arcpy.Parameter("t_csv", "Nom du fichier .csv de sortie", "Input", "GPString", "Required")
		]
		params[6].value = "\\Nommez_le.csv"
		
		return params

	def isLicensed(self):
		"""Set whether tool is licensed to execute."""
		return True

	def updateParameters(self, parameters):
		"""Modify the values and properties of parameters before internal
		validation is performed.  This method is called whenever a parameter
		has been changed."""
		return

	def updateMessages(self, parameters):
		"""Modify the messages created by internal validation for each tool
		parameter.  This method is called after internal validation."""
		return

	def execute(self, parameters, messages):
		"""The source code of the tool."""
		lieu = parameters[0].value
		iteration = parameters[1].value
		batv1 = parameters[2].valueAsText
		batv2 = parameters[3].valueAsText
		sc = parameters[4].valueAsText
		chemin = parameters[5].value
		t_csv = parameters[6].value

		############ PREPARATION DU TRAITEMENT
		# test des systèmes de projection
		# si les couches ne sont pas dans le même SC, les calculs de longueur vont bugger et il y a un risque qu'ils ne se superposent pas bien et que les XY des points ne soient pas correctement corrélés
		spatial_batv1 = arcpy.Describe(batv1).spatialReference
		spatial_batv2 = arcpy.Describe(batv2).spatialReference
		if spatial_batv1.name != spatial_batv2.name :
			arcpy.AddMessage("Le système de coordonnées de {0} est {1}. Le système de coordonnées de {2} est {3}. \nVeuillez les projeter dans un même système de coordonnées projeté ! ".format(batv1,spatial_batv1.name,batv2,spatial_batv2.name))
			sys.exit()

		# cette fonction permet de nommer les couches correctement selon le lieu étudié et l'itération de l'outil
		def nom(layer) :
			return lieu + str(iteration) + "_" + layer

		# récupérer les totaux de bâtiments des couches EVOIA et atelier vecteur
		tot_batv1 = int(arcpy.management.GetCount(batv1).getOutput(0))
		tot_batv2 = int(arcpy.management.GetCount(batv2).getOutput(0))
		if tot_batv1 == "0" or tot_batv2 == "0" :
			arcpy.AddMessage("La/les couche(s) bâtiments renseignée(s) est/sont vide(s).")
			sys.exit()

		# COPIES DES COUCHES D'ENTREE
		# comme les couches en entrée seront modifiées par les manipulations, il est judicieux de créer des copies de leur état d'origine
		batv1_copie = nom(f"{batv1}_original")
		arcpy.management.CopyFeatures(batv1, batv1_copie)
		batv2_copie = nom(f"{batv2}_original")
		arcpy.management.CopyFeatures(batv2, batv2_copie)
		
		# CENTROIDES
		# les bâtiments des deux saisies sont ramenés à leur centroïdes afin de pouvoir évaluer la détection
		batv1_center = nom("batv1_center")
		arcpy.management.FeatureToPoint(batv1,  batv1_center, "CENTROID")
		batv2_center = nom("batv2_center")
		arcpy.management.FeatureToPoint(batv2,  batv2_center, "CENTROID")
		if arcpy.management.GetCount(batv1_center).getOutput(0) == "0" or arcpy.management.GetCount(batv2_center).getOutput(0) == "0":
			arcpy.AddMessage("Erreur de l'outil FeatureToPoint")
			sys.exit()
		
		# BUFFER
		# marge de détection d'après v1
		batv1_buff = nom("batv1_buffer")
		arcpy.analysis.Buffer(batv1,  batv1_buff, "2 Meters", "FULL", "ROUND", "NONE", None, "PLANAR")
		
		# les centroides des bâtiments de la version 1 sont bufferisés pour inclure la marge de détection des bâtiments ajoutés
		batv1_margedet = nom("batv1_margedet")
		arcpy.analysis.Buffer(batv1_center,  batv1_margedet, "2 Meters", "FULL", "ROUND", "NONE", None, "PLANAR")
		if arcpy.management.GetCount(batv1_margedet).getOutput(0) == "0":
			arcpy.AddMessage("Erreur du buffer de détection des bâtiments")
			sys.exit()

		# les centroides des bâtiments de la version 2 sont bufferisés pour inclure la marge de détection des bâtiments supprimés
		batv2_margedet = nom("batv2_margedet")
		arcpy.analysis.Buffer(batv2_center,  batv2_margedet, "2 Meters", "FULL", "ROUND", "NONE", None, "PLANAR")
		if arcpy.management.GetCount(batv2_margedet).getOutput(0) == "0":
			arcpy.AddMessage("Erreur du buffer de détection des bâtiments")
			sys.exit()
		
		########### TRAITEMENT
		# BATIMENTS SUPPRIMES
		# créer une layer en mémoire à partir des centroides de la version 1
		arcpy.management.MakeFeatureLayer(batv1_center,"centroid_v1")

		# les centroides des bâtiments de la version 1 en dehors de la version 2 sont séparés dans la couche "ajoutés"
		centroidv1_suppr = nom("batiments_supprimes")
		arcpy.management.SelectLayerByLocation("centroid_v1", "INTERSECT", batv2_margedet, "0 Meters", "NEW_SELECTION", "INVERT")
		arcpy.management.CopyFeatures("centroid_v1", centroidv1_suppr)
		arcpy.management.SelectLayerByAttribute("centroid_v1", "CLEAR_SELECTION", '', None)
		
		if arcpy.management.GetCount(centroidv1_suppr).getOutput(0) != "0" :
			x_suppr = int(arcpy.management.GetCount(centroidv1_suppr).getOutput(0))
		else :
			x_suppr = 0
		
		# BATIMENTS AJOUTES
		# créer une layer en mémoire à partir des centroides de la version 2
		arcpy.management.MakeFeatureLayer(batv2_center,"layer_v2")

		# les centroides des bâtiments de la version 2 en dehors de la version 1 sont séparés dans la couche "ajoutés"
		batv2_add = nom("batiments_ajoutes")
		arcpy.management.SelectLayerByLocation("layer_v2", "INTERSECT", batv1_margedet, "0 Meters", "NEW_SELECTION", "INVERT")
		arcpy.management.CopyFeatures("layer_v2", batv2_add)
		arcpy.management.SelectLayerByAttribute("layer_v2", "CLEAR_SELECTION", '', None)
		
		if arcpy.management.GetCount(batv2_add).getOutput(0) != "0" :
			x_plus = int(arcpy.management.GetCount(batv2_add).getOutput(0))
		else :
			x_plus = 0
		
		# BATIMENTS SIMILAIRES EN DETECTTION
		
		# les polygones de la version 2 dans la marge de détection de la version 1 sont séparés dans une couche "similaires"
		batv2_same = nom("batv2_same")
		arcpy.management.SelectLayerByLocation(batv2, "COMPLETELY_WITHIN", batv1_buff, None, "NEW_SELECTION", "NOT_INVERT")
		arcpy.management.CopyFeatures(batv2, batv2_same)
		arcpy.management.SelectLayerByAttribute(batv2, "CLEAR_SELECTION", '', None)
		
		if arcpy.management.GetCount(batv2_same).getOutput(0) != "0" :
			x_same = int(arcpy.management.GetCount(batv2_same).getOutput(0))
		else :
			x_same = 0
		p_same_v1 = round((x_same/tot_batv1)*100,2)
		p_same_v2 = round((x_same/tot_batv2)*100,2)
				
		############ SORTIE DU TRAITEMENT
		# INSCRIRE LE TOUT EN ATTRIBUT DANS UNE COPIE DE LA COUCHE V1
		
		### Supprimés
		# Obtenir la liste des champs
		fields_bv1 = arcpy.ListFields(batv1)
		# Obtenir le nom de la 1ere colonne 
		col1 = fields_bv1[0].name
		# Ajouter à cette couche la colonne ORIG_FID de la couche des centroides des éléments supprimés
		arcpy.JoinField_management(batv1, col1, centroidv1_suppr, "ORIG_FID", ["ORIG_FID"])
		# Sélectionner les bâtiments dont les ORIG_FID sont différents de 0, ce qui indique qu'ils ont été supprimés
		arcpy.management.SelectLayerByAttribute(batv1, "NEW_SELECTION", "ORIG_FID = 0 Or ORIG_FID IS NULL", "INVERT")
		# Leur ajouter l'état supprimé
		arcpy.management.CalculateField(batv1, "Etat", '"Supprimé"', "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
		arcpy.management.SelectLayerByAttribute(batv1, "CLEAR_SELECTION", '', None)

		# Sélectionner les bâtiments supprimés et créer une couche temporaire
		bat_suppr = nom("bat_suppr")
		arcpy.management.MakeFeatureLayer(batv1, bat_suppr, "Etat = 'Supprimé'")
		
		# INSCRIRE LE TOUT EN ATTRIBUT DANS UNE COPIE DE LA COUCHE V2
		
		### Ajoutés
		# Obtenir la liste des champs
		fields_bv2 = arcpy.ListFields(batv2)
		# Obtenir le nom de la 1ere colonne 
		col2 = fields_bv2[0].name
		# Ajouter à cette couche la colonne ORIG_FID de la couche des centroides des éléments ajoutés
		arcpy.JoinField_management(batv2, col2, batv2_add, "ORIG_FID", ["ORIG_FID"])
		# Sélectionner les bâtiments dont les ORIG_FID sont différents de 0, ce qui indique qu'ils ont été ajoutés
		arcpy.management.SelectLayerByAttribute(batv2, "NEW_SELECTION", "ORIG_FID = 0 Or ORIG_FID IS NULL", "INVERT")
		# Leur ajouter l'état ajouté
		arcpy.management.CalculateField(batv2, "Etat", '"Ajouté"', "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
		arcpy.management.SelectLayerByAttribute(batv2, "CLEAR_SELECTION", '', None)

		### Similaires
		# Sélectionner les bâtiments qui sont identiques à la couche prédéfinie
		arcpy.management.SelectLayerByLocation(batv2, "ARE_IDENTICAL_TO", batv2_same, None, "NEW_SELECTION", "NOT_INVERT")
		# Leur ajouter l'état invariable
		arcpy.management.CalculateField(batv2, "Etat", '"Invariable"', "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
		arcpy.management.SelectLayerByAttribute(batv2, "CLEAR_SELECTION")
		
		### Modifiés
		# Sélectionner les bâtiments ajoutés qui s'intersectent avec les supprimés
		arcpy.management.SelectLayerByLocation(batv2, "INTERSECT", bat_suppr, None, "ADD_TO_SELECTION", "NOT_INVERT")
		# leur ajouter l'état modifié
		arcpy.management.CalculateField(batv2, "Etat", '"Modifié"', "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
		# récupérer le nombre de bâtiments modifiés finaux dans la v2
		if arcpy.management.GetCount(batv2).getOutput(0) != "0" :
			x_modif = int(arcpy.management.GetCount(batv2).getOutput(0))
		else :
			x_modif = 0
		p_modif_v2 = round((x_modif/tot_batv2)*100,2)
		# Désélectionner la couche
		arcpy.management.SelectLayerByAttribute(batv2, "CLEAR_SELECTION", '', None)
		
		# récupérer le nombre de bâtiments modifiés de la v1 en trouvant le nombre de supprimés intersectant des ajoutés
		arcpy.management.SelectLayerByLocation(bat_suppr, "INTERSECT", batv2, None, "ADD_TO_SELECTION", "NOT_INVERT")
		# récupérer le nombre de bâtiments modifiés supprimés dans la v1
		if arcpy.management.GetCount(bat_suppr).getOutput(0) != "0" :
			x_a_modif = int(arcpy.management.GetCount(bat_suppr).getOutput(0))
		else :
			x_a_modif = 0
		p_modif_v1 = round((x_a_modif/tot_batv1)*100,2)
		# Désélectionner la couche
		arcpy.management.SelectLayerByAttribute(bat_suppr, "CLEAR_SELECTION", '', None)

		### Mise à jour des totaux de suppr et add, car les modifiés ont été identifiés et en font partie
		x_plus = abs(x_plus - x_modif)
		x_suppr = abs(x_suppr - x_a_modif)
		p_suppr = round((x_suppr/tot_batv1)*100,2)
		p_plus_v1 = round((x_plus/tot_batv1)*100,2)
		p_plus_v2 = round((x_plus/tot_batv2)*100,2)
		p_v1 = p_suppr + p_modif_v1 + p_same_v1
		p_v2 = p_plus_v2 + p_modif_v2 + p_same_v2
		
		### Supprimés
		# Ajouter les éléments supprimés de V1 à V2
		arcpy.Append_management(bat_suppr, batv2, "NO_TEST")
		
		############# SORTIE
		# création d'un dossier de sortie pour les couches et enregistrement en shapefile dedans
		arcpy.management.CreateFolder(chemin, lieu + str(iteration) + "_Analyse_Changement")
		arcpy.conversion.FeatureClassToShapefile(centroidv1_suppr + ";" + batv2_add + ";" + batv1_copie + ";" + batv2_copie + ";" + batv1 + ";" + batv2, str(chemin) + "\\" + lieu + str(iteration) + "_Analyse_Changement")
		
		# Sortir les résultats dans un excel
		output_csv = str(chemin) + "\\" + lieu + str(iteration) + "_Analyse_Changement" + t_csv
		donnees = [['Analyse de changement', lieu, '', ''],
			['', 'Totaux', '', ''],
			['Vecteur passé', tot_batv1, '', ''],
			['Vecteur présent', tot_batv2, '', ''],
			['','','',''],
			['Reprises', 'Quantité', 'Proportion du vecteur passé', 'Proportion du vecteur présent'],
			['Suppression', x_suppr, str(p_suppr).replace('.', ','), ''],
			['Addition', x_plus, str(p_plus_v1).replace('.', ','), str(p_plus_v2).replace('.', ',')],
			['Modification', str(x_a_modif) + " modifiés pour " + str(x_modif) + " finaux", str(p_modif_v1).replace('.', ','), str(p_modif_v2).replace('.', ',')],
			['Détection similaire', x_same, str(p_same_v1).replace('.', ','), str(p_same_v2).replace('.', ',')],
			['Vérification des % totaux', '', str(p_v1).replace('.', ','), str(p_v2).replace('.', ',')]
			]

		with open (output_csv, mode = 'w', newline = '') as fichier_csv :
			writer = csv.writer(fichier_csv, delimiter = ';')
			for ligne in donnees :
				writer.writerow(ligne)
		
		return
