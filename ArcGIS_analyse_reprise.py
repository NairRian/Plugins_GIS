# -*- coding: utf-8 -*-
# Développé par Raphaëlle Camphuis 
# Objectif : Effectuer un traitement ArcGIS pour analyser quantitativement la reprise de atelier vecteur sur des vecteurs extraits par IA

import arcpy
import csv
import sys

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
		self.label = "Analyse de reprise"
		self.description = ""
		self.canRunInBackground = False

	def getParameterInfo(self):
		"""Define parameter definitions"""
		params = [arcpy.Parameter("lieu", "Nom de la ville", "Input", "GPString", "Required"),
				  arcpy.Parameter("Iteration", "Itération de l'outil n° ?", "Input", "GPLong", "Required"),
				  arcpy.Parameter("batIA", "Bâtiments IA", "input", "GPFeatureLayer", "Required"),
				  arcpy.Parameter("batREP", "Bâtiments reprise", "input", "GPFeatureLayer", "Required"),
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
		batIA_original = parameters[2].valueAsText
		batREP_original = parameters[3].valueAsText
		sc = parameters[4].valueAsText
		chemin = parameters[5].value
		t_csv = parameters[6].value

				# PREPARATION DU TRAITEMENT
		
			# Test des systèmes de projection
		# Si les couches ne sont pas dans le même SC, les calculs ne fonctionneront pas correctement car XY non corrélés
		spatial_batIA = arcpy.Describe(batIA_original).spatialReference
		spatial_batREP = arcpy.Describe(batREP_original).spatialReference
		if spatial_batIA.name != spatial_batREP.name :
			arcpy.AddMessage("Le système de coordonnées de {0} est {1}. Le système de coordonnées de {2} est {3}. \nVeuillez les projeter dans un même système de coordonnées projeté ! ".format(batIA,spatial_batIA.name,batREP,spatial_batREP.name))
			sys.exit()
		
			# Fonction de nommage des couches
		# Toutes les couches créées par ce code seront nommés en intégrant la ville et l'itération de l'outil
		def nom(layer) :
			return lieu + str(iteration) + "_" + layer
		
			# Vérifier que les couches en entrée ne sont pas vides
		# Récupérer les totaux de bâtiments des couches EVOIA et atelier vecteur
		tot_batIA = int(arcpy.management.GetCount(batIA_original).getOutput(0))
		tot_batREP = int(arcpy.management.GetCount(batREP_original).getOutput(0))
		if tot_batIA == 0 or tot_batREP == 0 :
			arcpy.AddMessage("La/les couche(s) bâtiments renseignée(s) est/sont vide(s).")
			sys.exit()

			# Copies des couches en entrée
		# On ne modifie pas les couches en entrée, elles sont conservées tel quel.
		# On les copie, et cela crée des feature class en stockage
		batIA_fc = arcpy.management.CopyFeatures(batIA_original, nom("Bati_IA_analysé")).getOutput(0)
		batREP_fc = arcpy.management.CopyFeatures(batREP_original, nom("Reprise_des_batiments_analysé")).getOutput(0)
		# Afin de réaliser des calculs et des sélections correctement sur ces copies, il faut transformer la feature class en layer
		batIA = arcpy.management.MakeFeatureLayer(batIA_fc, "batIA_lyr").getOutput(0)
		batREP = arcpy.management.MakeFeatureLayer(batREP_fc, "batREP_lyr").getOutput(0)
		
			# Créer une couche de centroïdes pour les traitements
		# les bâtiments de la saisie IA sont ramenés à leur centroïdes afin de pouvoir évaluer la détection
		batIA_center = nom("batIA_center")
		arcpy.management.FeatureToPoint(batIA,  batIA_center, "CENTROID")
		if arcpy.management.GetCount(batIA_center).getOutput(0) == "0" :
			arcpy.AddMessage("Erreur de l'outil FeatureToPoint")
			sys.exit()
		# Créer une layer en mémoire à partir de la feature class
		centroidIA = arcpy.management.MakeFeatureLayer(batIA_center,"centroid_IA").getOutput(0)
		
				# TRAITEMENT
		
			# Identification des bâtiments ajoutés
		
		# les bâtiments de la version REP qui n'intersectent pas les centroïdes de la version IA sont dénombrés et identifiés comme état "ajouté"
		arcpy.management.SelectLayerByLocation(batREP, "INTERSECT", centroidIA, "0 Meters", "NEW_SELECTION", "INVERT")
		arcpy.management.CalculateField(batREP, "Etat", '"Ajouté"', "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
		if arcpy.management.GetCount(batREP).getOutput(0) != "0" :
			x_plus = int(arcpy.management.GetCount(batREP).getOutput(0))
		else :
			x_plus = 0
		arcpy.management.SelectLayerByAttribute(batREP, "CLEAR_SELECTION", '', None)
		
			# Identification des bâtiments similaires
		
		# les polygones de la version REP identiques à ceux de la version IA sont dénombrés et identifiés comme état "Invariable"
		arcpy.management.SelectLayerByLocation(batREP, "ARE_IDENTICAL_TO", batIA, None, "NEW_SELECTION", "NOT_INVERT")
		arcpy.management.CalculateField(batREP, "Etat", '"Invariable"', "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
		if arcpy.management.GetCount(batREP).getOutput(0) != "0" :
			x_same = int(arcpy.management.GetCount(batREP).getOutput(0))
		else :
			x_same = 0
		arcpy.management.SelectLayerByAttribute(batREP, "CLEAR_SELECTION", '', None)
		
		
			# Identification des bâtiments supprimés
		
		# les polygones IA dont le centroide n'intersecte pas aux batiments REP sont ajoutés à la couche REP et attribués l'état "Supprimé"
		arcpy.management.SelectLayerByLocation(centroidIA, "INTERSECT", batREP, "0 Meters", "NEW_SELECTION", "INVERT")
		if arcpy.management.GetCount(centroidIA).getOutput(0) != "0" :
			x_suppr = int(arcpy.management.GetCount(centroidIA).getOutput(0))
		else :
			x_suppr = 0
		arcpy.management.SelectLayerByLocation(batIA, "CONTAINS", centroidIA, None, "NEW_SELECTION", "NOT_INVERT")
		arcpy.Append_management(batIA, batREP, "NO_TEST")
		arcpy.management.SelectLayerByLocation(batREP, "CONTAINS", centroidIA, None, "NEW_SELECTION", "NOT_INVERT")
		arcpy.management.CalculateField(batREP, "Etat", '"Supprimé"', "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
		arcpy.management.SelectLayerByAttribute(centroidIA, "CLEAR_SELECTION", '', None)
		arcpy.management.SelectLayerByAttribute(batIA, "CLEAR_SELECTION", '', None)
		
		
				# FIN DU TRAITEMENT
		
			# Par déduction, identification des bâtiments modifiés
		arcpy.management.SelectLayerByAttribute(batREP, "NEW_SELECTION", "Etat IS NULL ", None)
		arcpy.management.CalculateField(batREP, "Etat", '"Modifié"', "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
		arcpy.management.SelectLayerByAttribute(batREP, "CLEAR_SELECTION", '', None)
		
			# Calculs statistiques
		# modifiés
		x_modif_IA = tot_batIA - x_same - x_suppr
		x_modif_REP = tot_batREP - x_same - x_plus

		# proportions par rapport au total de bâtiments IA et au total de bâtiments REP
		p_suppr = round((x_suppr/tot_batIA)*100,0)
		p_same_IA = round((x_same/tot_batIA)*100,0)
		p_same_REP = round((x_same/tot_batREP)*100,0)
		p_plus_IA = round((x_plus/tot_batIA)*100,0)
		p_plus_REP = round((x_plus/tot_batREP)*100,0)
		p_modif_IA = round((x_modif_IA/tot_batIA)*100,0)
		p_modif_REP = round((x_modif_REP/tot_batREP)*100,0)
		
		# calcul des stats pour la détection
		precision_det = (x_same + x_modif_REP) / tot_batIA
		rappel_det = (x_same + x_modif_IA) / tot_batREP
		score_f1_det = 2 * ((precision_det * rappel_det)/(precision_det + rappel_det))
		# calcul des stats pour la vectorisation
		precision_vect = x_same / tot_batIA
		rappel_vect = x_same / tot_batREP
		score_f1_vect = 2 * ((precision_vect * rappel_vect)/(precision_vect + rappel_vect))
		
				# SORTIE
		# création d'un dossier de sortie pour les couches et enregistrement en shapefile dedans
		arcpy.management.CreateFolder(chemin, lieu + str(iteration) + "_Analyse_Changement")
		arcpy.conversion.FeatureClassToShapefile(batIA_original + ";" + batREP_original + ";" + batREP_fc, str(chemin) + "\\" + lieu + str(iteration) + "_Analyse_Changement")

		# Sortir les résultats dans un excel
		output_csv = str(chemin) + "\\" + lieu + str(iteration) + "_Analyse_Changement" + t_csv
		def fmt_pct(val):
			return f"{val:.0f}".replace('.', ',') + " %"
		donnees = [
			['Analyse de reprise', lieu, '', ''],
			['', 'Totaux', '', ''],
			['Batiments IA', tot_batIA, '', ''],
			['Batiments repris', tot_batREP, '', ''],
			['','','',''],
			['','Analyse des reprises','',''],
			['Reprises', 'Quantité', 'Proportion du vecteur IA', 'Proportion du vecteur repris'],
			['Suppression', x_suppr, fmt_pct(p_suppr), ''],
			['Addition', x_plus, fmt_pct(p_plus_IA), fmt_pct(p_plus_REP)],
			['Modification', str(x_modif_IA) + " modifiés pour " + str(x_modif_REP) + " finaux", fmt_pct(p_modif_IA), fmt_pct(p_modif_REP)],
			['Détection similaire', x_same, fmt_pct(p_same_IA), fmt_pct(p_same_REP)],
			['','','',''],
			['','Résultats statistiques pour détection','Résultats statistiques pour vectorisation',''],
			['Précision',round(precision_det,2),round(precision_vect,2),''],
			['Rappel',round(rappel_det,2),round(rappel_vect,2),''],
			['Score_F1',round(score_f1_det,2),round(score_f1_vect,2),'']
			]

		with open (output_csv, mode = 'w', newline = '') as fichier_csv :
			writer = csv.writer(fichier_csv, delimiter = ';')
			for ligne in donnees :
				writer.writerow(ligne)
		
		return
