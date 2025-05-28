import asyncio
import websockets
import json
import logging
import os
from datetime import datetime
from typing import Dict, Set, Optional
import uuid
import aiohttp

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSocketRouterBFF:
    def __init__(self):
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.active_sessions: Dict[str, dict] = {}
        
        # Configuração dos serviços disponíveis
        self.services = {
            "image_recognition": {
                "url": os.environ.get("IMAGE_RECOGNITION_SERVICE_URL", "ws://localhost:8001"),
                "type": "websocket",
                "description": "Serviço de reconhecimento de imagens"
            },
            "text_analysis": {
                "url": os.environ.get("TEXT_ANALYSIS_SERVICE_URL", "ws://localhost:8002"),
                "type": "websocket", 
                "description": "Serviço de análise de texto"
            },
            "chat_ai": {
                "url": os.environ.get("CHAT_AI_SERVICE_URL", "ws://localhost:8003"),
                "type": "websocket",
                "description": "Serviço de chat com IA"
            },
            "speech_recognition": {
                "url": os.environ.get("SPEECH_RECOGNITION_SERVICE_URL", "http://localhost:8004"),
                "type": "http",
                "description": "Serviço de reconhecimento de fala"
            }
        }
        
        # Pool de conexões WebSocket para serviços
        self.service_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
    
    async def register_client(self, websocket):
        """Registra um novo cliente conectado"""
        self.connected_clients.add(websocket)
        client_id = f"client_{len(self.connected_clients)}_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"Cliente {client_id} conectado. Total: {len(self.connected_clients)}")
        
        # Envia informações de conexão e serviços disponíveis
        welcome_msg = {
            "type": "connection",
            "status": "connected",
            "client_id": client_id,
            "message": "Conectado ao BFF Router",
            "available_services": list(self.services.keys()),
            "services_info": {k: v["description"] for k, v in self.services.items()},
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send(json.dumps(welcome_msg))
        return client_id
    
    async def unregister_client(self, websocket):
        """Remove cliente desconectado"""
        self.connected_clients.discard(websocket)
        logger.info(f"Cliente desconectado. Total: {len(self.connected_clients)}")
    
    async def get_or_create_service_connection(self, service_name: str) -> Optional[websockets.WebSocketClientProtocol]:
        """Obtém ou cria uma conexão WebSocket com o serviço"""
        if service_name not in self.services:
            return None
            
        service_config = self.services[service_name]
        
        # Só funciona para serviços WebSocket
        if service_config["type"] != "websocket":
            return None
            
        # Verifica se já existe uma conexão ativa
        if service_name in self.service_connections:
            connection = self.service_connections[service_name]
            if not connection.closed:
                return connection
            else:
                # Remove conexão fechada
                del self.service_connections[service_name]
        
        # Cria nova conexão
        try:
            logger.info(f"Conectando ao serviço {service_name} em {service_config['url']}")
            connection = await websockets.connect(service_config["url"])
            self.service_connections[service_name] = connection
            return connection
        except Exception as e:
            logger.error(f"Erro ao conectar com serviço {service_name}: {e}")
            return None
    
    async def route_to_websocket_service(self, service_name: str, message_data: dict, client_websocket):
        """Roteia mensagem para serviço WebSocket"""
        connection = await self.get_or_create_service_connection(service_name)
        
        if not connection:
            error_msg = {
                "type": "error",
                "service": service_name,
                "message": f"Não foi possível conectar ao serviço {service_name}",
                "timestamp": datetime.now().isoformat()
            }
            await client_websocket.send(json.dumps(error_msg))
            return
        
        try:
            # Adiciona metadados de roteamento
            routed_message = {
                **message_data,
                "bff_session_id": message_data.get("session_id", str(uuid.uuid4())),
                "bff_timestamp": datetime.now().isoformat()
            }
            
            # Envia mensagem para o serviço
            await connection.send(json.dumps(routed_message))
            logger.info(f"Mensagem roteada para {service_name}")
            
            # Aguarda resposta do serviço
            try:
                response = await asyncio.wait_for(connection.recv(), timeout=30.0)
                response_data = json.loads(response)
                
                # Adiciona informações de roteamento na resposta
                response_data["routed_from"] = service_name
                response_data["bff_timestamp"] = datetime.now().isoformat()
                
                # Envia resposta de volta para o cliente
                await client_websocket.send(json.dumps(response_data))
                logger.info(f"Resposta de {service_name} enviada ao cliente")
                
            except asyncio.TimeoutError:
                timeout_msg = {
                    "type": "error",
                    "service": service_name,
                    "message": f"Timeout aguardando resposta do serviço {service_name}",
                    "timestamp": datetime.now().isoformat()
                }
                await client_websocket.send(json.dumps(timeout_msg))
                
        except Exception as e:
            logger.error(f"Erro ao rotear para {service_name}: {e}")
            error_msg = {
                "type": "error",
                "service": service_name,
                "message": f"Erro interno ao comunicar com {service_name}",
                "timestamp": datetime.now().isoformat()
            }
            await client_websocket.send(json.dumps(error_msg))
    
    async def route_to_http_service(self, service_name: str, message_data: dict, client_websocket):
        """Roteia mensagem para serviço HTTP"""
        service_config = self.services[service_name]
        
        try:
            async with aiohttp.ClientSession() as session:
                # Prepara dados para envio HTTP
                payload = {
                    **message_data,
                    "bff_session_id": message_data.get("session_id", str(uuid.uuid4())),
                    "bff_timestamp": datetime.now().isoformat()
                }
                
                async with session.post(
                    service_config["url"],
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        result["routed_from"] = service_name
                        result["bff_timestamp"] = datetime.now().isoformat()
                        
                        await client_websocket.send(json.dumps(result))
                        logger.info(f"Resposta HTTP de {service_name} enviada ao cliente")
                    else:
                        error_msg = {
                            "type": "error",
                            "service": service_name,
                            "message": f"Serviço {service_name} retornou status {response.status}",
                            "timestamp": datetime.now().isoformat()
                        }
                        await client_websocket.send(json.dumps(error_msg))
                        
        except Exception as e:
            logger.error(f"Erro ao fazer requisição HTTP para {service_name}: {e}")
            error_msg = {
                "type": "error",
                "service": service_name,
                "message": f"Erro ao comunicar com serviço HTTP {service_name}",
                "timestamp": datetime.now().isoformat()
            }
            await client_websocket.send(json.dumps(error_msg))
    
    async def handle_message(self, websocket, message: str):
        """Processa mensagens e roteia para serviços apropriados"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            target_service = data.get("service")
            
            if message_type == "ping":
                # Responde ao ping para manter conexão viva
                pong_msg = {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(pong_msg))
                return
            
            elif message_type == "list_services":
                # Lista serviços disponíveis
                services_msg = {
                    "type": "services_list",
                    "services": self.services,
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(services_msg))
                return
            
            elif message_type == "route_request":
                # Processa solicitação de roteamento
                if not target_service:
                    error_msg = {
                        "type": "error",
                        "message": "Serviço de destino não especificado",
                        "timestamp": datetime.now().isoformat()
                    }
                    await websocket.send(json.dumps(error_msg))
                    return
                
                if target_service not in self.services:
                    error_msg = {
                        "type": "error",
                        "message": f"Serviço '{target_service}' não encontrado",
                        "available_services": list(self.services.keys()),
                        "timestamp": datetime.now().isoformat()
                    }
                    await websocket.send(json.dumps(error_msg))
                    return
                
                # Envia confirmação de recebimento
                ack_msg = {
                    "type": "routing",
                    "message": f"Roteando para {target_service}...",
                    "target_service": target_service,
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(ack_msg))
                
                # Roteia baseado no tipo do serviço
                service_config = self.services[target_service]
                if service_config["type"] == "websocket":
                    await self.route_to_websocket_service(target_service, data, websocket)
                elif service_config["type"] == "http":
                    await self.route_to_http_service(target_service, data, websocket)
            
            elif message_type == "status":
                # Retorna status do BFF
                status_msg = {
                    "type": "status_response",
                    "connected_clients": len(self.connected_clients),
                    "active_sessions": len(self.active_sessions),
                    "service_connections": len(self.service_connections),
                    "available_services": list(self.services.keys()),
                    "server_time": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(status_msg))
            
            else:
                error_msg = {
                    "type": "error",
                    "message": f"Tipo de mensagem não reconhecido: {message_type}",
                    "supported_types": ["ping", "list_services", "route_request", "status"]
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
        client_id = await self.register_client(websocket)
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Conexão do cliente {client_id} fechada")
        except Exception as e:
            logger.error(f"Erro na conexão do cliente {client_id}: {e}")
        finally:
            await self.unregister_client(websocket)
    
    async def cleanup_connections(self):
        """Limpa conexões fechadas com serviços"""
        while True:
            try:
                await asyncio.sleep(30)  # Verifica a cada 30 segundos
                closed_services = []
                
                for service_name, connection in self.service_connections.items():
                    if connection.closed:
                        closed_services.append(service_name)
                
                for service_name in closed_services:
                    logger.info(f"Removendo conexão fechada com {service_name}")
                    del self.service_connections[service_name]
                    
            except Exception as e:
                logger.error(f"Erro na limpeza de conexões: {e}")

# Instância do BFF Router
bff_router = WebSocketRouterBFF()

async def main():
    """Função principal para iniciar o servidor"""
    # Porta para o BFF Router
    port = int(os.environ.get("PORT", 8765))
    host = "0.0.0.0"
    
    logger.info(f"Iniciando BFF WebSocket Router em ws://{host}:{port}")
    logger.info("Serviços configurados:")
    for name, config in bff_router.services.items():
        logger.info(f"  - {name}: {config['url']} ({config['type']})")
    
    # Inicia tarefa de limpeza de conexões
    cleanup_task = asyncio.create_task(bff_router.cleanup_connections())
    
    try:
        async with websockets.serve(bff_router.client_handler, host, port):
            logger.info("BFF WebSocket Router iniciado com sucesso!")
            logger.info("Aguardando conexões...")
            await asyncio.Future()  # Mantém o servidor rodando
    finally:
        cleanup_task.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Servidor interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro ao iniciar servidor: {e}")
        