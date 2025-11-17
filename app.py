import os
import tempfile
import json
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from extraction_complete import extraction_complete_ehf
import shutil

# Application FastAPI pour l'analyse EHF
app = FastAPI(title="Analyseur EHF", description="Interface d'analyse des documents EHF")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurations
UPLOAD_FOLDER = Path("uploads_ehf")
UPLOAD_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"pdf"}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

# Templates et static
templates = Jinja2Templates(directory="templates")

# Créer le dossier static s'il n'existe pas
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)

# Monter les fichiers statiques
app.mount("/static", StaticFiles(directory="static"), name="static")

def allowed_file(filename: str) -> bool:
    """Vérifier si le fichier est autorisé."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_ehf_document(pdf_path: str, filename: str):
    """Traiter le document EHF avec notre système d'extraction."""
    try:
        print(f"🚀 Début de l'analyse EHF pour : {filename}")
        
        # Utiliser notre système d'extraction complet
        result = extraction_complete_ehf(pdf_path)
        
        print(f"✅ Analyse terminée avec succès pour : {filename}")
        
        # Structurer les résultats pour l'interface
        structured_result = {
            "filename": filename,
            "date_analyse": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "statistiques": {
                "nb_formalites": result["nb_formalites"],
                "nb_mutations": result["nb_mutations"],
                "nb_hypotheques_actives": result["nb_hypotheques_actives"],
                "nb_immeubles": result["nb_immeubles"]
            },
            "propriete_actuelle": result.get("propriete_actuelle", []),
            "hypotheques_actives": result.get("hypotheques_actives", []),
            "mutations": result.get("mutations", []),
            "comptage_types": result.get("comptage_types", {}),
            "success": True
        }
        
        return structured_result, None
        
    except Exception as e:
        error_msg = f"Erreur lors de l'analyse EHF: {str(e)}"
        print(f"❌ {error_msg}")
        return None, error_msg

@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    """Afficher le formulaire d'upload."""
    return templates.TemplateResponse("ehf_upload.html", {"request": request})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze_ehf(request: Request, file: UploadFile = File(...)):
    """Analyser le fichier EHF uploadé."""
    
    # Vérifications
    if not file.filename:
        raise HTTPException(status_code=400, detail="Aucun fichier sélectionné")
    
    if not allowed_file(file.filename):
        return templates.TemplateResponse(
            "ehf_upload.html",
            {"request": request, "error": "Type de fichier non autorisé. Seuls les fichiers PDF sont acceptés."},
        )

    if file.size and file.size > MAX_CONTENT_LENGTH:
        return templates.TemplateResponse(
            "ehf_upload.html",
            {"request": request, "error": "Fichier trop volumineux (max 50 Mo)."},
        )

    # Sauvegarder temporairement le fichier
    filename = file.filename
    filepath = UPLOAD_FOLDER / filename

    try:
        # Écrire le fichier
        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        # Traiter le document EHF
        result, error = process_ehf_document(str(filepath), filename)
        
    finally:
        # Supprimer le fichier temporaire
        try:
            if filepath.exists():
                filepath.unlink()
        except:
            pass

    if error:
        return templates.TemplateResponse(
            "ehf_upload.html", 
            {"request": request, "error": error}
        )

    return templates.TemplateResponse(
        "ehf_result.html", 
        {"request": request, "result": result}
    )

@app.get("/api/health")
async def health_check():
    """Point de contrôle de santé de l'API."""
    return {"status": "ok", "service": "Analyseur EHF"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Démarrage de l'application EHF...")
    print("📋 Interface disponible sur : http://localhost:1000")
    uvicorn.run("app:app", host="0.0.0.0", port=1000, reload=True)
