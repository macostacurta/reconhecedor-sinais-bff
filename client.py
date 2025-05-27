import asyncio
import websockets
import json
import base64
import uuid
import os
from datetime import datetime

class TestClient:
    def __init__(self, uri=None):
        # Permite definir URI via variável de ambiente ou usa localhost como fallback
        if uri is None:
            # Prioridade: ENV var > localhost para desenvolvimento
            self.uri = os.environ.get("WEBSOCKET_URI", "ws://localhost:8765")
        else:
            self.uri = uri
            
        self.client_id = str(uuid.uuid4())
        print(f"🌐 URI configurada: {self.uri}")
    
    def create_fake_image_data(self):
        """Cria dados de imagem simulados (base64)"""
        # Simula uma pequena imagem em base64
        fake_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        return fake_image
    
    async def send_ping(self, websocket):
        """Envia ping para testar conexão"""
        ping_msg = {
            "type": "ping",
            "client_id": self.client_id,
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send(json.dumps(ping_msg))
        print("📡 Ping enviado")
    
    async def send_status_request(self, websocket):
        """Solicita status do servidor"""
        status_msg = {
            "type": "status",
            "client_id": self.client_id
        }
        await websocket.send(json.dumps(status_msg))
        print("📊 Solicitação de status enviada")
    
    async def send_image_recognition(self, websocket):
        """Envia solicitação de reconhecimento de imagem"""
        image_data = self.create_fake_image_data()
        
        recognition_msg = {
            "type": "image_recognition",
            "client_id": self.client_id,
            "image_data": image_data,
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send(json.dumps(recognition_msg))
        print("🖼️  Imagem enviada para reconhecimento")
    
    async def listen_for_messages(self, websocket):
        """Escuta mensagens do servidor"""
        try:
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "connection":
                    print(f"✅ {data.get('message')}")
                
                elif msg_type == "pong":
                    print("🏓 Pong recebido")
                
                elif msg_type == "processing":
                    print(f"⏳ {data.get('message')}")
                
                elif msg_type == "recognition_result":
                    print(f"🎯 Resultado do reconhecimento:")
                    print(f"   Status: {data.get('status')}")
                    print(f"   Confiança: {data.get('confidence'):.2%}")
                    print(f"   Predições:")
                    for pred in data.get('predictions', []):
                        print(f"     - {pred['label']}: {pred['confidence']:.2%}")
                    print(f"   Tempo de processamento: {data.get('processing_time')}s")
                
                elif msg_type == "status_response":
                    print(f"📊 Status do servidor:")
                    print(f"   Clientes conectados: {data.get('connected_clients')}")
                    print(f"   Fila de processamento: {data.get('queue_size')}")
                    print(f"   Hora do servidor: {data.get('server_time')}")
                
                elif msg_type == "error":
                    print(f"❌ Erro: {data.get('message')}")
                
                else:
                    print(f"📨 Mensagem recebida: {data}")
                    
        except websockets.exceptions.ConnectionClosed:
            print("🔌 Conexão fechada")
        except Exception as e:
            print(f"❌ Erro ao escutar mensagens: {e}")
    
    async def interactive_test(self):
        """Teste interativo com menu"""
        try:
            # Configura timeout e outras opções para conexões remotas
            connect_kwargs = {}
            if self.uri.startswith("wss://"):
                # Para conexões WSS (Render), define timeout maior
                connect_kwargs = {
                    "ping_interval": 20,
                    "ping_timeout": 10,
                    "close_timeout": 10
                }
            
            async with websockets.connect(self.uri, **connect_kwargs) as websocket:
                print(f"🔗 Conectado ao servidor em {self.uri}")
                print(f"🆔 Client ID: {self.client_id}")
                
                # Inicia listener em background
                listen_task = asyncio.create_task(self.listen_for_messages(websocket))
                
                # Menu interativo
                while True:
                    print("\n" + "="*50)
                    print("MENU DE TESTES:")
                    print("1. Enviar Ping")
                    print("2. Solicitar Status")
                    print("3. Reconhecimento de Imagem")
                    print("4. Teste Automático")
                    print("5. Alterar URI")
                    print("6. Sair")
                    print("="*50)
                    
                    choice = input("Escolha uma opção (1-6): ").strip()
                    
                    if choice == "1":
                        await self.send_ping(websocket)
                    
                    elif choice == "2":
                        await self.send_status_request(websocket)
                    
                    elif choice == "3":
                        await self.send_image_recognition(websocket)
                    
                    elif choice == "4":
                        print("🤖 Executando teste automático...")
                        await self.send_ping(websocket)
                        await asyncio.sleep(1)
                        await self.send_status_request(websocket)
                        await asyncio.sleep(1)
                        await self.send_image_recognition(websocket)
                    
                    elif choice == "5":
                        print("📝 URI atual:", self.uri)
                        new_uri = input("Digite a nova URI (ou Enter para cancelar): ").strip()
                        if new_uri:
                            print("⚠️  Para alterar a URI, reinicie o cliente com a nova configuração.")
                            print("💡 Dica: Use a variável de ambiente WEBSOCKET_URI")
                        continue
                    
                    elif choice == "6":
                        print("👋 Encerrando cliente...")
                        break
                    
                    else:
                        print("❌ Opção inválida!")
                    
                    await asyncio.sleep(0.5)  # Pequena pausa para processar respostas
                
                listen_task.cancel()
                
        except ConnectionRefusedError:
            print(f"❌ Não foi possível conectar ao servidor em {self.uri}")
            print("🔧 Verifique se:")
            print("   - O servidor está rodando")
            print("   - A URI está correta")
            print("   - Não há firewall bloqueando a conexão")
        except websockets.exceptions.InvalidURI:
            print(f"❌ URI inválida: {self.uri}")
            print("💡 Exemplos de URIs válidas:")
            print("   - ws://localhost:8765 (desenvolvimento local)")
            print("   - wss://seu-app.onrender.com (Render.org)")
        except Exception as e:
            print(f"❌ Erro na conexão: {e}")

def show_configuration_help():
    """Mostra ajuda sobre configuração"""
    print("\n" + "="*60)
    print("📋 CONFIGURAÇÃO DO CLIENTE")
    print("="*60)
    print("🏠 DESENVOLVIMENTO LOCAL:")
    print("   python client.py")
    print("   (usa ws://localhost:8765 por padrão)")
    print()
    print("☁️  SERVIDOR NO RENDER:")
    print("   Opção 1 - Variável de ambiente:")
    print("   export WEBSOCKET_URI=wss://seu-app.onrender.com")
    print("   python client.py")
    print()
    print("   Opção 2 - Editar o código:")
    print("   Altere a linha uri=... no main()")
    print()
    print("🔒 IMPORTANTE:")
    print("   - Use ws:// para localhost")
    print("   - Use wss:// para Render.org (conexão segura)")
    print("="*60)

async def main():
    # Mostra ajuda de configuração
    show_configuration_help()
    
    # Permite definir URI via argumento ou variável de ambiente
    print("\n🚀 Iniciando cliente de teste WebSocket")
    
    # Opção para definir URI diretamente (descomente e altere conforme necessário)
    client = TestClient("wss://websocket-image-recognition.onrender.com")
    
    # Usa configuração automática (recomendado)
    #client = TestClient()
    
    await client.interactive_test()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Cliente interrompido pelo usuário")