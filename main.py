from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from supabase import create_client, Client
import requests
import os
import time

app = FastAPI(title="CV Generator API", version="1.0.0")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://portfolio-storychara.vercel.app",
        "*"  # Para testing, luego restringe
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Configuración de Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def compile_latex_to_pdf(latex_code: str) -> bytes:
    """
    Compila código LaTeX a PDF usando GitHub Gist + LaTeX.Online
    """
    if not GITHUB_TOKEN:
        raise HTTPException(
            status_code=500, 
            detail="GITHUB_TOKEN no configurado"
        )
    
    # Crear Gist temporal
    gist_data = {
        "description": "CV LaTeX compilation",
        "public": True,
        "files": {
            "document.tex": {
                "content": latex_code
            }
        }
    }
    
    # Crear Gist en GitHub
    gist_response = requests.post(
        "https://api.github.com/gists",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        },
        json=gist_data,
        timeout=10
    )
    
    if gist_response.status_code != 201:
        raise HTTPException(
            status_code=500, 
            detail=f"Error creando Gist: {gist_response.text}"
        )
    
    gist = gist_response.json()
    gist_id = gist['id']
    raw_url = gist['files']['document.tex']['raw_url']
    
    try:
        time.sleep(2)
        
        check_response = requests.get(raw_url, timeout=5)
        if check_response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail=f"Gist no accesible: {check_response.status_code}"
            )
        
        compile_url = f"https://latexonline.cc/compile?url={raw_url}"
        pdf_response = requests.get(compile_url, timeout=60)
        
        if pdf_response.status_code != 200:
            raise HTTPException(
                status_code=400, 
                detail=f"LaTeX compilation failed. Status: {pdf_response.status_code}."
            )
        
        return pdf_response.content
        
    finally:
        requests.delete(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
            timeout=10
        )

@app.get("/")
async def root():
    return {
        "message": "CV Generator API",
        "version": "1.0.0",
        "endpoints": {
            "GET /": "API Information",
            "GET /generate-cv": "Generate CV PDF",
            "GET /health": "Health check",
            "GET /test-compile": "Test LaTeX compilation",
            "GET /debug-latex": "Debug LaTeX code"
        }
    }

@app.get("/health")
async def health_check():
    """Verificar que la conexión a Supabase funciona"""
    try:
        response = supabase.rpc('get_latex').execute()
        return {
            "status": "ok",
            "supabase": "connected",
            "latex_length": len(response.data) if response.data else 0
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/generate-cv")
async def generate_cv():
    """Endpoint principal: genera el CV en PDF desde la BD"""
    try:
        response = supabase.rpc('get_latex').execute()
        
        if not response.data:
            raise HTTPException(
                status_code=500, 
                detail="La función get_latex() no devolvió datos"
            )
        
        latex_code = response.data
        pdf_content = compile_latex_to_pdf(latex_code)
        
        return StreamingResponse(
            iter([pdf_content]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=CV.pdf"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test-compile")
async def test_compile():
    """Prueba la compilación con código LaTeX mínimo"""
    simple_latex = r"""\documentclass{article}
\begin{document}
Hello World!
\end{document}"""
    
    try:
        pdf_content = compile_latex_to_pdf(simple_latex)
        return StreamingResponse(
            iter([pdf_content]),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=test.pdf"}
        )
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug-latex")
async def debug_latex():
    """Endpoint temporal para ver qué devuelve get_latex()"""
    try:
        response = supabase.rpc('get_latex').execute()
        
        return {
            "success": True,
            "data": response.data,
            "data_type": type(response.data).__name__,
            "length": len(str(response.data)) if response.data else 0
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Para Vercel
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)