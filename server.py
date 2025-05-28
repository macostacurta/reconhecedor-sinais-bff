import asyncio
import websockets
import json
import base64
import logging
import os
from datetime import datetime
from typing import Dict, Set
import uuid

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageRecognitionBFF:
    def __init__(self):
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.processing_queue: Dict[str, dict] = {}
    
    async def register_client(self, websocket):
        """Registra um novo cliente conectado"""
        self.connected_clients.add(websocket)
        logger.info(f"Cliente conectado. Total: {len(self.connected_clients)}")
        
        # Envia mensagem de boas-vindas
        welcome_msg = {
            "type": "connection",
            "status": "connected",
            "message": "Conectado ao BFF de Reconhecimento de Imagens",
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send(json.dumps(welcome_msg))
    
    async def unregister_client(self, websocket):
        """Remove cliente desconectado"""
        self.connected_clients.discard(websocket)
        logger.info(f"Cliente desconectado. Total: {len(self.connected_clients)}")
    
    async def process_image_recognition(self, image_data: str, client_id: str):
        """Simula o processamento de reconhecimento de imagem"""
        # Aqui você integraria com sua IA de reconhecimento
        # Por enquanto, vamos simular um processamento
        
        logger.info(f"Processando imagem para cliente {client_id}")
        
        # Simula tempo de processamento
        await asyncio.sleep(2)
        
        # Resultado simulado - substitua pela chamada real da IA
        result = {
            "client_id": client_id,
            "status": "completed",
            "confidence": 0.95,
            "predictions": [
                {"label": "Cachorro", "confidence": 0.95},
                {"label": "Golden Retriever", "confidence": 0.87},
                {"label": "Animal Doméstico", "confidence": 0.92}
            ],
            "processing_time": 2.1,
            "timestamp": datetime.now().isoformat()
        }
        
        return result
    
    async def handle_message(self, websocket, message: str):
        """Processa mensagens recebidas dos clientes"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "ping":
                # Responde ao ping para manter conexão viva
                logger.info("Estou vivo e funcionando!")
                pong_msg = {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(pong_msg))

            elif message_type == "gesture":
                logger.info(data.get("gesture"))
                logger.info(data.get("timestamp"))
            
            elif message_type == "image_recognition":
                # Processa solicitação de reconhecimento de imagem
                client_id = data.get("client_id", str(uuid.uuid4()))
                image_data = data.get("image_data")
                
                if not image_data:
                    error_msg = {
                        "type": "error",
                        "message": "Dados da imagem não fornecidos",
                        "client_id": client_id
                    }
                    await websocket.send(json.dumps(error_msg))
                    return
                
                # Envia confirmação de recebimento
                ack_msg = {
                    "type": "processing",
                    "message": "Imagem recebida, iniciando processamento...",
                    "client_id": client_id,
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(ack_msg))
                
                # Processa a imagem (assíncrono)
                result = await self.process_image_recognition(image_data, client_id)
                
                # Envia resultado
                response_msg = {
                    "type": "recognition_result",
                    **result
                }
                await websocket.send(json.dumps(response_msg))
            
            elif message_type == "status":
                # Retorna status do servidor
                
                status_msg = {
                    "type": "status_response",
                    "connected_clients": len(self.connected_clients),
                    "queue_size": len(self.processing_queue),
                    "server_time": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(status_msg))
            
            else:
                error_msg = {
                    "type": "error",
                    "message": f"Tipo de mensagem não reconhecido: {message_type}"
                }
                await websocket.send(json.dumps(error_msg))
                
        except json.JSONDecodeError:
            error_msg = {
                "type": "error",
                "message": "Formato JSON inválido"
            }
            await websocket.send(json.dumps(error_msg))
        except Exception as e:
            logger.error(f"Erro ao processar mensagem: {e}")
            error_msg = {
                "type": "error",
                "message": "Erro interno do servidor"
            }
            await websocket.send(json.dumps(error_msg))
    
    async def client_handler(self, websocket):
        """Handler principal para conexões de clientes"""
        await self.register_client(websocket)
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Conexão fechada pelo cliente")
        except Exception as e:
            logger.error(f"Erro na conexão: {e}")
        finally:
            await self.unregister_client(websocket)

# Instância do BFF
bff = ImageRecognitionBFF()

async def main():
    """Função principal para iniciar o servidor"""
    # Render.org fornece a porta através da variável de ambiente PORT
    port = int(os.environ.get("PORT", 8765))
    host = "0.0.0.0"  # Render requer bind em todas as interfaces
    
    logger.info(f"Iniciando servidor WebSocket em ws://{host}:{port}")
    
    async with websockets.serve(bff.client_handler, host, port):
        logger.info("Servidor WebSocket iniciado com sucesso!")
        logger.info("Aguardando conexões...")
        await asyncio.Future()  # Mantém o servidor rodando

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Servidor interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro ao iniciar servidor: {e}")