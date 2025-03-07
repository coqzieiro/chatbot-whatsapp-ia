import os
import csv
import re
import datetime
from threading import Lock
from collections import defaultdict
from dotenv import load_dotenv
import openai
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import asyncio
import aiohttp
from functools import partial
from concurrent.futures import ThreadPoolExecutor
import uvicorn
from asgiref.wsgi import WsgiToAsgi

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# Configuração da Twilio
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
client = Client(ACCOUNT_SID, AUTH_TOKEN)

# Configuração da OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Nome do arquivo CSV onde os dados serão armazenados
CSV_FILE = "dados_chatbot.csv"

# Cria o arquivo CSV imediatamente (se não existir)
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "Telefone",
                "Data/Hora",
                "Mensagem Recebida",
                "Sabores",
                "Quantidades",
                "Valor Total (R$)",
                "CEP",
                "Frete (R$)",
                "Observações",
            ]
        )

# Dicionário para armazenar o estado da conversa por número de telefone
# O estado agora inclui informações sobre o pedido e a etapa atual
conversation_states = defaultdict(
    lambda: {
        "mensagens": [],
        "estado_pedido": "inicio",  # inicio, sabor, quantidade, cep, pagamento, resumo, finalizado
        "pedido": {"sabores": [], "quantidades": [], "cep": ""},
    }
)
# Lock para proteger o acesso concorrente ao dicionário de estados
state_lock = Lock()

# Dados dos produtos (preços, sabores)
SABORES = {
    "uva": 5.99,
    "limão": 5.99,
    "guaraná": 5.99,
    "laranja": 5.99,
}
VALOR_UNIDADE = 5.99
FRETE_BASE = 5.00  # Frete base (pode ser ajustado com base no CEP)

# Cria um ThreadPoolExecutor para tarefas de CPU-bound (como chamadas à API do OpenAI)
executor = ThreadPoolExecutor(max_workers=10)  # Ajuste max_workers conforme necessário


# --- Funções Assíncronas ---
async def get_gpt_response_async(prompt, context="", mensagens=[]):
    """Obtém a resposta do GPT-4 de forma assíncrona, usando a API do OpenAI."""
    try:
        # Prompt do Sistema (Fluxo de Vendas)
        system_prompt = f"""Você é um chatbot amigável e prestativo da Refrigerantes São Carlos. 😊 Você está aqui para ajudar os clientes a fazer pedidos de refrigerantes. Siga este fluxo de vendas:
        1.  **Boas-Vindas e Apresentação:** Comece sempre com uma saudação amigável. Apresente-se e diga que você pode ajudar com os pedidos.
        2.  **Coleta de Informações:**
            *   Pergunte qual sabor de refrigerante o cliente deseja (uva, limão, guaraná, laranja).
            *   Pergunte a quantidade de cada sabor.
            *   Peça o CEP para calcular o frete (se necessário).
            *   Pergunte a forma de pagamento (dinheiro, pix, cartão).
        3.  **Resumo do Pedido:** Mostre um resumo claro do pedido (sabores, quantidades, valor total, frete, forma de pagamento).
        4.  **Finalização:** Agradeça o pedido e informe o prazo de entrega (ex: "Seu pedido será entregue em até 30 minutos.").
        5.  Use emojis para deixar a conversa mais agradável. Seja conciso e direto nas perguntas.
        6.  Se o cliente fizer uma pergunta fora do fluxo de vendas, responda de forma educada, mas reoriente-o para o pedido.
        7.  Sempre pergunte 'Você precisa de mais alguma coisa?' e se a resposta for 'sim', volte para o início do fluxo, finalize a conversa.
        8.  Preços: Uva, Limão, Guaraná, Laranja: R${VALOR_UNIDADE:.2f} cada. Frete Base: R${FRETE_BASE:.2f}.
        """

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if mensagens:
            for msg in mensagens:
                messages.append(msg)
        messages.append({"role": "user", "content": prompt})

        response = await asyncio.to_thread(  # Executa a chamada do OpenAI em uma thread
            partial(
                openai.chat.completions.create,
                model="gpt-4-turbo-preview",
                messages=messages,
            )
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"Erro ao chamar a API do GPT (assíncrono): {e}")
        return "Desculpe, não consegui processar sua solicitação no momento. Tente novamente."


def save_to_csv(phone, data_hora, mensagens, estado_pedido):  # Adiciona estado_pedido
    """Salva a conversa e os dados específicos em um arquivo CSV local.  Esta função agora processa as mensagens."""
    try:
        # Extrair informações da conversa (sabores, quantidades, etc.)
        sabores = []
        quantidades = []
        valor_total = 0.0
        cep = ""
        frete = ""
        observacoes = f"Pedido em estado: {estado_pedido}"  # Adiciona o estado do pedido

        for msg in mensagens:
            if msg["role"] == "user":
                mensagem_recebida = msg["content"]
                s, q, c = extract_data(mensagem_recebida)
                sabores.extend(s)
                quantidades.extend(q)
                if c:
                    cep = c
            elif msg["role"] == "assistant":
                # Extrair informações da resposta do GPT (pode conter o valor total, frete etc.)
                if "valor total" in msg["content"].lower():
                    match = re.search(r"R\$\s*([\d,.]+)", msg["content"])
                    if match:
                        try:
                            valor_total = float(match.group(1).replace(",", ""))
                        except ValueError:
                            print("Erro ao converter valor total.")
                if "frete" in msg["content"].lower():
                    match = re.search(r"R\$\s*([\d,.]+)", msg["content"])
                    if match:
                        try:
                            frete = float(match.group(1).replace(",", ""))
                        except ValueError:
                            print("Erro ao converter valor do frete.")
        # Salva no CSV
        with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    phone,
                    data_hora,
                    "\n".join(
                        [msg["content"] for msg in mensagens if msg["role"] == "user"]
                    ),  # Mensagens do usuário
                    ", ".join(sabores),
                    ", ".join(quantidades),
                    str(valor_total),
                    cep,
                    str(frete),
                    observacoes,
                ]
            )
        print("Dados salvos no CSV com sucesso!")
    except Exception as e:
        print(f"Erro ao salvar no CSV: {e}")


def extract_data(message):
    """Extrai dados relevantes da mensagem do cliente."""
    sabores = []
    quantidades = []
    cep = ""
    observacoes = ""

    # Extrai quantidade de sabores
    for sabor, valor in SABORES.items():
        if sabor in message.lower():
            match = re.search(r"(\d+)\s*" + sabor, message, re.IGNORECASE)
            if match:
                sabores.append(sabor)
                quantidades.append(match.group(1))

    # Extrai CEP
    cep_match = re.search(r"\b\d{5}-\d{3}\b", message)
    if cep_match:
        cep = cep_match.group(0)

    return sabores, quantidades, cep


def calcular_valor_total(quantidades):
    """Calcula o valor total do pedido."""
    total = 0.0
    for i, quantidade in enumerate(quantidades):
        try:
            total += int(quantidade) * VALOR_UNIDADE
        except ValueError:
            print(f"Erro ao converter quantidade {quantidade} para inteiro.")
            return (
                0.0
            )  # ou trate o erro de outra forma, talvez ignorando o item

    return total

# Cria a sessão aiohttp *antes* de iniciar o servidor
async def create_app():
    global async_session
    async_session = aiohttp.ClientSession()  # Cria a sessão aiohttp aqui
    return app

@app.route("/whatsapp", methods=["POST"])
async def whatsapp_reply():
    """Responde às mensagens do WhatsApp, coleta dados e salva no CSV."""
    incoming_msg = request.values.get("Body", "").strip()
    sender_phone_number = request.values.get("From")

    print(f"Mensagem recebida de {sender_phone_number}: {incoming_msg}")

    now = datetime.datetime.now()
    data_hora = now.strftime("%Y-%m-%d %H:%M:%S")

    with state_lock:
        state = conversation_states[sender_phone_number]
        mensagens = state.get("mensagens", [])  # Recupera as mensagens
        estado_pedido = state.get("estado_pedido", "inicio")
        pedido = state.get("pedido", {"sabores": [], "quantidades": [], "cep": ""})  # Recupera o pedido

    # Adiciona a mensagem recebida às mensagens
    mensagens.append({"role": "user", "content": incoming_msg})

    # Lógica do Fluxo de Vendas
    if estado_pedido == "inicio":
        gpt_response = await get_gpt_response_async(incoming_msg, mensagens=mensagens)  # Passa todas as mensagens
        if "uva" in gpt_response.lower() or "limão" in gpt_response.lower() or "guaraná" in gpt_response.lower() or "laranja" in gpt_response.lower():
            estado_pedido = "quantidade" # Se o cliente já mencionou o sabor, vá para a etapa de quantidade
        else:
            estado_pedido = "sabor" # Caso contrário, peça o sabor

    elif estado_pedido == "sabor":
        gpt_response = await get_gpt_response_async(incoming_msg, mensagens=mensagens)
        # Extrair sabor (aqui você pode usar a função extract_data ou melhorar o prompt para extrair o sabor)
        sabores, _, _ = extract_data(incoming_msg)
        if sabores:
            pedido["sabores"].extend(sabores)
            estado_pedido = "quantidade"  # Vá para a quantidade
        else:
            gpt_response = "Qual sabor de refrigerante você gostaria? 😊 (Uva, Limão, Guaraná ou Laranja)"

    elif estado_pedido == "quantidade":
        gpt_response = await get_gpt_response_async(incoming_msg, mensagens=mensagens)
        # Extrair quantidade (use extract_data ou adapte)
        _, quantidades, _ = extract_data(incoming_msg)
        if quantidades:
            pedido["quantidades"].extend(quantidades)
            estado_pedido = "cep"  # Peça o CEP
            gpt_response = "Qual o seu CEP para calcular o frete? 😉"
        else:
            gpt_response = "Quantas unidades de cada sabor você gostaria? 😉"

    elif estado_pedido == "cep":
        gpt_response = await get_gpt_response_async(incoming_msg, mensagens=mensagens)
        # Extrair CEP (use extract_data)
        _, _, cep = extract_data(incoming_msg)
        if cep:
            pedido["cep"] = cep
            estado_pedido = "pagamento"  # Peça a forma de pagamento
            gpt_response = "Qual a forma de pagamento? (Dinheiro, Pix, Cartão) 💳"
        else:
            gpt_response = "Por favor, informe um CEP válido. 😉"

    elif estado_pedido == "pagamento":
        gpt_response = await get_gpt_response_async(incoming_msg, mensagens=mensagens)
        # Extrair forma de pagamento (adapte a lógica)
        # (Simplificado para este exemplo)
        forma_pagamento = incoming_msg.lower()
        if "dinheiro" in forma_pagamento or "pix" in forma_pagamento or "cartão" in forma_pagamento:
            estado_pedido = "resumo"  # Vá para o resumo
        else:
            gpt_response = "Por favor, informe a forma de pagamento (Dinheiro, Pix, Cartão). 😉"
            # Calculando o valor total
            try:
                valor_total = sum(
                    int(q) * VALOR_UNIDADE for q in pedido["quantidades"]
                )
            except ValueError:
                valor_total = 0  # ou trate o erro de outra forma
            frete = FRETE_BASE  # Frete fixo (pode ser calculado com base no CEP)
            # Cria a mensagem de resumo
            gpt_response = f"""
            📝 Resumo do seu pedido:
            Sabores: {', '.join(pedido["sabores"])}
            Quantidades: {', '.join(pedido["quantidades"])}
            Valor Total: R${valor_total:.2f}
            Frete: R${frete:.2f}
            Forma de Pagamento: {forma_pagamento.capitalize()}

            ✅ Seu pedido foi recebido! Ele será entregue em até 30 minutos.
            """

            estado_pedido = "finalizado"  # Pedido finalizado

    elif estado_pedido == "resumo":
            # Calculando o valor total
            try:
                valor_total = sum(
                    int(q) * VALOR_UNIDADE for q in pedido["quantidades"]
                )
            except ValueError:
                valor_total = 0  # ou trate o erro de outra forma
            frete = FRETE_BASE  # Frete fixo (pode ser calculado com base no CEP)
            # Cria a mensagem de resumo
            gpt_response = f"""
            📝 Resumo do seu pedido:
            Sabores: {', '.join(pedido["sabores"])}
            Quantidades: {', '.join(pedido["quantidades"])}
            Valor Total: R${valor_total:.2f}
            Frete: R${frete:.2f}
            Forma de Pagamento: {forma_pagamento.capitalize()}

            ✅ Seu pedido foi recebido! Ele será entregue em até 30 minutos.
            """

            estado_pedido = "finalizado"  # Pedido finalizado


    # Lógica para a pergunta final e encerramento (adaptado ao fluxo)
    if estado_pedido == "finalizado":
        if "sim" in incoming_msg.lower():
            # Reinicia o estado para um novo pedido
            estado_pedido = "inicio"
            pedido = {"sabores": [], "quantidades": [], "cep": ""}
            gpt_response = "Gostaria de fazer outro pedido? 😊"
        elif (
            "não" in incoming_msg.lower() or "nao" in incoming_msg.lower()
        ):
            # Salva o pedido e remove o estado
            with app.app_context():
                await asyncio.to_thread(
                    save_to_csv, sender_phone_number, data_hora, mensagens, estado_pedido
                )
            with state_lock:
                del conversation_states[sender_phone_number]
            resp = MessagingResponse()
            msg = resp.message()
            msg.body("✅ Pedido finalizado. Obrigado! 😊")
            return str(resp)
        else:
            gpt_response = "Agradecemos seu pedido! 😉" # Para garantir que o atendimento continue

    # Se não está finalizado, adicione a resposta do GPT às mensagens
    else:
        gpt_response = await get_gpt_response_async(incoming_msg, mensagens=mensagens)  # Passa todas as mensagens

    mensagens.append({"role": "assistant", "content": gpt_response})  # Adiciona a resposta à lista

    with state_lock:
        state["mensagens"] = mensagens
        state["estado_pedido"] = estado_pedido
        state["pedido"] = pedido  # Salva o pedido
        conversation_states[sender_phone_number] = state
    # Envia a resposta via Twilio
    resp = MessagingResponse()
    msg = resp.message()
    msg.body(gpt_response)

    return str(resp)

# Cria o aplicativo ASGI
app_asgi = WsgiToAsgi(app)  # Converte o Flask WSGI para ASGI

# Modificação para inicializar a sessão aiohttp e rodar o servidor Flask
if __name__ == "__main__":
    # Cria o app Flask e a sessão aiohttp
    app = asyncio.run(create_app())
    uvicorn.run(app_asgi, host="0.0.0.0", port=5000)  # Inicia o servidor com Uvicorn usando o app convertido