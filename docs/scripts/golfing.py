import json
from typing import Literal
import dspy
from attachments import Attachments
import pandas as pd
import os

lm_flash = dspy.LM('gemini/gemini-2.5-flash-preview-04-17')
dspy.configure(lm=lm_flash)

class ExtractTaxInvoice(dspy.Signature):
    """Extract structured information from Invoices."""
    invoice_pdf_extracted_text: str = dspy.InputField(
        optional=True, description="Extracted text from the invoice pdf")
    invoice_image: dspy.Image = dspy.InputField(
        optional=True, description="Image of the invoice")
    vendor_name: str = dspy.OutputField()
    currency: Literal['CAD', 'USD'] = dspy.OutputField()
    invoice_date: str = dspy.OutputField()
    total_before_tax: float = dspy.OutputField()
    tps_tax_amount: float = dspy.OutputField()
    tvq_tax_amount: float = dspy.OutputField()
    hst_tax_amount: float = dspy.OutputField()
    total_tax_amount: float = dspy.OutputField()
    total_after_tax: float = dspy.OutputField()
    items: str = dspy.OutputField(desc="A list of items separated by ;")
    spending_category: Literal["Alimentation - moulée mélangée","Plants utilisés pour augmenter la superficie (pommiers...)","Pomme de terre, Pommiers de variétés hâtives et tardives","Semences non-couverte par l'ASRA","Fertilisant","Ficelle et contenants","Travaux à forfait (excluant séchage et entreposage)","Location de machinerie","Transport et mise en marché","Fournitures de la ferme","Quincaillerie","Petits outils (construction)","Électricité","Carburants essence et diesel (sauf automobile)","Entretien du terrain","Entretien des bâtisses","Entretien de l'équipement","Carburant de l'automobile","Entretien de l'automobile","Assurance et immatriculation de l'automobile","Assurance-feu, responsabilité","Assurance-vie pour emprunts","Taxes foncières","Honoraires professionnels","Immatriculation de l'entreprise","Téléphone","Publicité et promotion","Papeterie et dépenses de bureau","Formation","Intérêts à court terme et frais bancaires","Intérêts sur la dette à long terme","Entretien mécanique","Abri a outils","Abri de bois temporaire","Achat camion usagé","Allée d'accès","Voiture neuve","Boite de camion","Cloture","Equipements agricoles","immobilisation (champignonnière)","immobilisation (complex agricole)","immobilisation (irrigation)","immobilisation (serre)","immobilisation (tunnel)","Petits outils (jardin)","Animaux","Vétérinaire","Substrats champignons"] = dspy.OutputField()

invoice_extractor = dspy.ChainOfThought(ExtractTaxInvoice)
invoice_extractor.load("invoice_extractor_optimized.json")

def process_invoice(p: str):
    a = Attachments(p)
    if p.lower().endswith(".pdf"):
        print("processing pdf: ", p)
        return invoice_extractor(invoice_pdf_extracted_text=str(a),
                                 invoice_image=dspy.Image.from_url(a.images[0])).to_dict()
    else:
        print("processing image: ", p)
        return invoice_extractor(invoice_image=dspy.Image.from_url(a.images[0])).to_dict()

invoice_path = "goldset_files"
pd.DataFrame([process_invoice(f"{invoice_path}/{f}") for f in os.listdir(invoice_path)]) \
    .to_csv(f"parsed_invoices.csv", index=False)
