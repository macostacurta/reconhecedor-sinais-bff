import asyncio
import websockets
import json
import logging
import os
import aiohttp
from datetime import datetime
from typing import Dict, Set
import uuid

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSocketBFF:
    def __init__(self):
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.service_endpoints = {
            "image_recognition": os.environ.get("IMAGE_RECOGNITION_URL", "ws://localhost:8766"),
            "ai_chat": os.environ.get("AI_CHAT_URL", "ws://localhost:8767"),
            "general_ai": os.environ.get("GENERAL_AI_URL", "ws://localhost:8768")
        }
        self.http_endpoints = {
            "image_recognition_http": os.environ.get("IMAGE_RECOGNITION_HTTP_URL", "http://localhost:3001/recognize"),
            "ai_chat_http": os.environ.get("AI_CHAT_HTTP_URL", "http://localhost:3002/chat")
        }
    
    async def register_client(self, websocket):
        """Registra um novo cliente conectado"""
        self.connected_clients.add(websocket)
        logger.info(f"Cliente conectado. Total: {len(self.connected_clients)}")
        
        welcome_msg = {
            "type": "connection",
            "status": "connected",
            "message": "Conectado ao BFF Router",
            "available_services": list(self.service_endpoints.keys()),
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send(json.dumps(welcome_msg))
    
    async def unregister_client(self, websocket):
        """Remove cliente desconectado"""
        self.connected_clients.discard(websocket)
        logger.info(f"Cliente desconectado. Total: {len(self.connected_clients)}")
    
    async def route_to_websocket_service(self, service_name: str, data: dict, client_websocket):
        """Roteia mensagem para serviço via WebSocket"""
        try:
            service_url = self.service_endpoints.get(service_name)
            if not service_url:
                raise ValueError(f"Serviço {service_name} não encontrado")
            
            logger.info(f"Roteando para {service_name} via WebSocket: {service_url}")
            
            # Conecta ao serviço
            async with websockets.connect(service_url) as service_ws:
                # Envia dados para o serviço
                await service_ws.send(json.dumps(data))
                
                # Escuta resposta do serviço e repassa para o cliente
                async for response in service_ws:
                    response_data = json.loads(response)
                    await client_websocket.send(json.dumps(response_data))
                    
                    # Se for uma resposta final, break
                    if response_data.get("type") in ["recognition_result", "chat_response", "ai_response", "error"]:
                        break
                        
        except Exception as e:
            logger.error(f"Erro ao rotear para {service_name}: {e}")
            error_msg = {
                "type": "error",
                "service": service_name,
                "message": f"Erro ao conectar com o serviço: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
            await client_websocket.send(json.dumps(error_msg))
    
    async def route_to_http_service(self, service_name: str, data: dict, client_websocket):
        """Roteia mensagem para serviço via HTTP"""
        try:
            service_url = self.http_endpoints.get(f"{service_name}_http")
            if not service_url:
                raise ValueError(f"Serviço HTTP {service_name} não encontrado")
            
            logger.info(f"Roteando para {service_name} via HTTP: {service_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(service_url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        await client_websocket.send(json.dumps(result))
                    else:
                        error_msg = {
                            "type": "error",
                            "service": service_name,
                            "message": f"Erro HTTP {response.status}",
                            "timestamp": datetime.now().isoformat()
                        }
                        await client_websocket.send(json.dumps(error_msg))
                        
        except Exception as e:
            logger.error(f"Erro ao rotear para {service_name} via HTTP: {e}")
            error_msg = {
                "type": "error",
                "service": service_name,
                "message": f"Erro ao conectar com o serviço: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
            await client_websocket.send(json.dumps(error_msg))
    
    async def handle_message(self, websocket, message: str):
        """Processa mensagens recebidas dos clientes e roteia para serviços"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            target_service = data.get("service")
            
            if message_type == "ping":
                pong_msg = {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(pong_msg))
                return
            
            if message_type == "status":
                status_msg = {
                    "type": "status_response",
                    "connected_clients": len(self.connected_clients),
                    "available_services": list(self.service_endpoints.keys()),
                    "server_time": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(status_msg))
                return
            
            # Roteamento baseado no serviço solicitado
            if target_service:
                # Adiciona ID único para rastreamento
                data["request_id"] = str(uuid.uuid4())
                data["timestamp"] = datetime.now().isoformat()
                
                # Envia confirmação de recebimento
                ack_msg = {
                    "type": "routing",
                    "message": f"Roteando para {target_service}...",
                    "request_id": data["request_id"],
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(ack_msg))
                
                # Decide se usa WebSocket ou HTTP baseado no tipo de mensagem
                use_http = data.get("use_http", False)
                
                if use_http:
                    await self.route_to_http_service(target_service, data, websocket)
                else:
                    await self.route_to_websocket_service(target_service, data, websocket)
            
            # Roteamento baseado no tipo de mensagem (compatibilidade)
            elif message_type == "image_recognition":
                data["service"] = "image_recognition"
                await self.route_to_websocket_service("image_recognition", data, websocket)
            
            elif message_type == "ai_chat":
                data["service"] = "ai_chat"
                await self.route_to_websocket_service("ai_chat", data, websocket)
            
            else:
                error_msg = {
                    "type": "error",
                    "message": f"Tipo de mensagem não reconhecido ou serviço não especificado: {message_type}",
                    "available_services": list(self.service_endpoints.keys())
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
bff = WebSocketBFF()

async def main():
    """Função principal para iniciar o servidor"""
    port = int(os.environ.get("PORT", 8765))
    host = "0.0.0.0"
    
    logger.info(f"Iniciando BFF WebSocket Router em ws://{host}:{port}")
    logger.info(f"Serviços configurados: {list(bff.service_endpoints.keys())}")
    
    async with websockets.serve(bff.client_handler, host, port):
        logger.info("BFF Router iniciado com sucesso!")
        logger.info("Aguardando conexões...")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Servidor interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro ao iniciar servidor: {e}")