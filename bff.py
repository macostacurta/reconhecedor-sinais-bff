from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import base64
import io
from PIL import Image
import uvicorn
from typing import Optional
import logging
from pydantic import BaseModel
import os
from datetime import datetime

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="BFF - Reconhecedor de Imagens",
    description="Backend for Frontend para reconhecimento de sinais em imagens",
    version="1.0.0"
)

# Configuração CORS para permitir requisições do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especifique os domínios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos de dados
class ImageAnalysisResponse(BaseModel):
    success: bool
    message: str
    detected_signs: list
    confidence: float
    processing_time: float
    timestamp: str

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    services: dict

# Configurações dos serviços (ajuste conforme necessário)
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")
SIGNAL_RECOGNITION_URL = os.getenv("SIGNAL_RECOGNITION_URL", "http://localhost:8002")

# Cliente HTTP para comunicação com outros serviços
http_client = httpx.AsyncClient(timeout=30.0)

@app.on_event("startup")
async def startup_event():
    logger.info("BFF iniciado com sucesso")

@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()
    logger.info("BFF finalizado")

@app.get("/", response_model=dict)
async def root():
    """Endpoint raiz com informações do BFF"""
    return {
        "service": "BFF - Reconhecedor de Imagens",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "analyze": "/analyze-image",
            "docs": "/docs"
        }
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Verifica a saúde do BFF e dos serviços conectados"""
    services_status = {}
    
    # Verificar serviço de IA
    try:
        ai_response = await http_client.get(f"{AI_SERVICE_URL}/health", timeout=5.0)
        services_status["ai_service"] = "online" if ai_response.status_code == 200 else "offline"
    except:
        services_status["ai_service"] = "offline"
    
    # Verificar serviço de reconhecimento de sinais
    try:
        signal_response = await http_client.get(f"{SIGNAL_RECOGNITION_URL}/health", timeout=5.0)
        services_status["signal_recognition"] = "online" if signal_response.status_code == 200 else "offline"
    except:
        services_status["signal_recognition"] = "offline"
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        services=services_status
    )

async def validate_image(file: UploadFile) -> bool:
    """Valida se o arquivo é uma imagem válida"""
    if not file.content_type.startswith('image/'):
        return False
    
    try:
        contents = await file.read()
        Image.open(io.BytesIO(contents))
        await file.seek(0)  # Reset file pointer
        return True
    except:
        return False

async def process_with_ai_service(image_data: bytes) -> dict:
    """Processa imagem com o serviço de IA"""
    try:
        # Converte imagem para base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        
        # Chama o serviço de IA
        response = await http_client.post(
            f"{AI_SERVICE_URL}/process",
            json={"image": image_b64},
            timeout=30.0
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Erro no serviço de IA: {response.status_code}")
            return {"error": "Falha no processamento da IA"}
            
    except httpx.TimeoutException:
        logger.error("Timeout no serviço de IA")
        return {"error": "Timeout no serviço de IA"}
    except Exception as e:
        logger.error(f"Erro ao comunicar com serviço de IA: {str(e)}")
        return {"error": f"Erro na comunicação: {str(e)}"}

async def process_with_signal_recognition(image_data: bytes) -> dict:
    """Processa imagem com o serviço de reconhecimento de sinais"""
    try:
        # Prepara dados para o serviço de reconhecimento
        files = {"image": ("image.jpg", image_data, "image/jpeg")}
        
        response = await http_client.post(
            f"{SIGNAL_RECOGNITION_URL}/recognize",
            files=files,
            timeout=30.0
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Erro no reconhecimento de sinais: {response.status_code}")
            return {"error": "Falha no reconhecimento de sinais"}
            
    except httpx.TimeoutException:
        logger.error("Timeout no reconhecimento de sinais")
        return {"error": "Timeout no reconhecimento de sinais"}
    except Exception as e:
        logger.error(f"Erro ao comunicar com reconhecimento de sinais: {str(e)}")
        return {"error": f"Erro na comunicação: {str(e)}"}

@app.post("/analyze-image", response_model=ImageAnalysisResponse)
async def analyze_image(file: UploadFile = File(...)):
    """
    Endpoint principal para análise de imagens
    Recebe uma imagem e retorna os sinais detectados
    """
    start_time = datetime.now()
    
    try:
        # Validação da imagem
        if not await validate_image(file):
            raise HTTPException(status_code=400, detail="Arquivo não é uma imagem válida")
        
        # Lê o conteúdo da imagem
        image_data = await file.read()
        
        if len(image_data) == 0:
            raise HTTPException(status_code=400, detail="Imagem vazia")
        
        if len(image_data) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="Imagem muito grande (máximo 10MB)")
        
        # Processa com ambos os serviços em paralelo
        import asyncio
        
        ai_task = asyncio.create_task(process_with_ai_service(image_data))
        signal_task = asyncio.create_task(process_with_signal_recognition(image_data))
        
        ai_result, signal_result = await asyncio.gather(ai_task, signal_task)
        
        # Processa e combina os resultados
        detected_signs = []
        confidence = 0.0
        
        # Combina resultados da IA
        if "error" not in ai_result and ai_result.get("predictions"):
            for prediction in ai_result["predictions"]:
                detected_signs.append({
                    "type": "ai_detection",
                    "label": prediction.get("label", "unknown"),
                    "confidence": prediction.get("confidence", 0.0),
                    "source": "ai_service"
                })
        
        # Combina resultados do reconhecimento de sinais
        if "error" not in signal_result and signal_result.get("signs"):
            for sign in signal_result["signs"]:
                detected_signs.append({
                    "type": "signal_recognition",
                    "label": sign.get("name", "unknown"),
                    "confidence": sign.get("confidence", 0.0),
                    "coordinates": sign.get("coordinates"),
                    "source": "signal_recognition"
                })
        
        # Calcula confiança média
        if detected_signs:
            confidence = sum(sign["confidence"] for sign in detected_signs) / len(detected_signs)
        
        # Calcula tempo de processamento
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Verifica se houve erros em ambos os serviços
        if "error" in ai_result and "error" in signal_result:
            raise HTTPException(
                status_code=503, 
                detail="Todos os serviços de processamento estão indisponíveis"
            )
        
        return ImageAnalysisResponse(
            success=True,
            message="Análise concluída com sucesso",
            detected_signs=detected_signs,
            confidence=confidence,
            processing_time=processing_time,
            timestamp=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro inesperado na análise: {str(e)}")
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return ImageAnalysisResponse(
            success=False,
            message=f"Erro no processamento: {str(e)}",
            detected_signs=[],
            confidence=0.0,
            processing_time=processing_time,
            timestamp=datetime.now().isoformat()
        )

@app.get("/services/status")
async def get_services_status():
    """Retorna status detalhado dos serviços conectados"""
    status = {}
    
    # Status do serviço de IA
    try:
        ai_response = await http_client.get(f"{AI_SERVICE_URL}/status", timeout=5.0)
        status["ai_service"] = ai_response.json() if ai_response.status_code == 200 else {"error": "unavailable"}
    except:
        status["ai_service"] = {"error": "connection_failed"}
    
    # Status do reconhecimento de sinais
    try:
        signal_response = await http_client.get(f"{SIGNAL_RECOGNITION_URL}/status", timeout=5.0)
        status["signal_recognition"] = signal_response.json() if signal_response.status_code == 200 else {"error": "unavailable"}
    except:
        status["signal_recognition"] = {"error": "connection_failed"}
    
    return status

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )