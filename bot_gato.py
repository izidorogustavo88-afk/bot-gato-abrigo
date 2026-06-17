import os
import logging
import datetime
import asyncio
import time
import re
import pandas as pd
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
NOME_PLANILHA = os.path.join(PASTA_ATUAL, "gatos_abrigo.xlsx")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Dicionários para controlar o estado da conversa sem depender da IA
estados = {}
dados_gatos = {}
usuarios_ativos = set()

def salvar_no_excel(nome, peso, racao):
    novos_dados = {
        "Data de Cadastro": [datetime.date.today().strftime("%d/%m/%Y")],
        "Nome do Gato": [nome],
        "Peso": [peso],
        "Ração Diária (g)": [racao]
    }
    df_novo = pd.DataFrame(novos_dados)
    if os.path.exists(NOME_PLANILHA):
        df_antigo = pd.read_excel(NOME_PLANILHA)
        df_final = pd.concat([df_antigo, df_novo], ignore_index=True)
    else:
        df_final = df_novo
    df_final.to_excel(NOME_PLANILHA, index=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    usuarios_ativos.add(chat_id)
    estados[chat_id] = "NOME"
    dados_gatos[chat_id] = {}
    
    saudacao = "🐾 <b>Sistema de Cadastro do Abrigo</b> 🐾\n\nVamos registrar um novo gatinho no sistema. Para começar, me diga: Qual é o nome dele(a)?"
    await update.message.reply_text(saudacao, parse_mode="HTML")

async def baixar_planilha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(NOME_PLANILHA):
        await update.message.reply_text("📊 Gerando a planilha de cadastro do abrigo...")
        with open(NOME_PLANILHA, "rb") as arquivo:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=arquivo,
                filename="gatos_abrigo.xlsx",
                caption="🐱 Aqui está a planilha atualizada com os gatinhos cadastrados!"
            )
    else:
        await update.message.reply_text("❌ Nenhuma planilha foi gerada ainda. Cadastre o primeiro gatinho para criá-la!")

async def remover_gato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ <b>Uso incorreto!</b> Digite o comando seguido do nome do gato.\nExemplo: <code>/remover Jack</code>", parse_mode="HTML")
        return
    nome_alvo = " ".join(context.args).strip()
    if os.path.exists(NOME_PLANILHA):
        df = pd.read_excel(NOME_PLANILHA)
        gato_existe = df[df['Nome do Gato'].astype(str).str.lower() == nome_alvo.lower()]
        if not gato_existe.empty:
            df_atualizado = df[df['Nome do Gato'].astype(str).str.lower() != nome_alvo.lower()]
            df_atualizado.to_excel(NOME_PLANILHA, index=False)
            await update.message.reply_text(f"✅ <b>Sucesso!</b> O gato <b>{nome_alvo}</b> foi removido do sistema.", parse_mode="HTML")
        else:
            await update.message.reply_text(f"❌ O gato <b>{nome_alvo}</b> não foi encontrado.", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ A planilha está vazia.", parse_mode="HTML")

async def responder_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    texto_usuario = update.message.text.strip()
    
    if chat_id not in estados:
        estados[chat_id] = "NOME"
        dados_gatos[chat_id] = {}

    estado_atual = estados[chat_id]
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Chamada para a IA (Poolside) para limpar e formatar a resposta do usuário
    try:
        loop = asyncio.get_event_loop()
        resposta = await loop.run_in_executor(
            None, 
            lambda: client.chat.completions.create(
                model="poolside/laguna-m.1:free",
                messages=[
                    {"role": "system", "content": "Você é um extrator de dados. Extraia apenas o dado puro do texto do usuário. Remova pontuações, palavras extras e responda APENAS com o valor bruto."},
                    {"role": "user", "content": f"Extraia o dado puro deste texto baseado no contexto de cadastro: '{texto_usuario}'"}
                ]
            )
        )
        dado_limpo = resposta.choices[0].message.content.strip().replace("*", "")
    except Exception as e:
        dado_limpo = texto_usuario  # se a IA falhar, usa o texto puro do usuário

    if estado_atual == "NOME":
        dados_gatos[chat_id]["nome"] = dado_limpo
        estados[chat_id] = "PESO"
        await update.message.reply_text("Perfeito, anotado. Agora, qual é o peso atual do gato (em kg)?")
        
    elif estado_atual == "PESO":
        dados_gatos[chat_id]["peso"] = dado_limpo
        estados[chat_id] = "PORTE"
        await update.message.reply_text("Qual é o porte ou altura do gato? (Exemplo: pequeno, médio, grande ou em centímetros)")
        
    elif estado_atual == "PORTE":
        # Pegar apenas os números do peso para calcular a ração de forma segura via Python
        try:
            peso_numerico = float(re.findall(r"[-+]?\d*\.\d+|\d+", dados_gatos[chat_id]["peso"])[0])
            racao_calculada = int(peso_numerico * 15)  # 15g por quilo
        except:
            racao_calculada = 60  # Valor padrão caso digitem texto irreconhecível no peso

        nome_final = dados_gatos[chat_id]["nome"]
        peso_final = dados_gatos[chat_id]["peso"]
        
        # Salva fisicamente no Excel usando Python puro
        salvar_no_excel(nome_final, peso_final, racao_calculada)
        
        # Resposta de finalização limpa
        resposta_final = f"O felino {nome_final} foi registrado com sucesso.\n\n<b>✅ [Sistema]: Gato registrado com sucesso na planilha Excel do abrigo!</b>"
        await update.message.reply_text(resposta_final, parse_mode="HTML")
        
        # Reseta o estado para o próximo cadastro
        del estados[chat_id]
        del dados_gatos[chat_id]

async def envio_diario_meio_dia(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in list(usuarios_ativos):
        try:
            if os.path.exists(NOME_PLANILHA):
                df = pd.read_excel(NOME_PLANILHA)
                if df.empty: continue
                mensagem = "🔔 <b>Relatório Diário de Alimentação do Abrigo</b> 🕒\n\n📋 <b>Lista de Felinos Cadastrados:</b>\n───────────────────────────────\n"
                for idx, row in df.iterrows():
                    mensagem += f"🐱 <b>{row['Nome do Gato']}</b> | Peso: {row['Peso']} | 🍽️ Ração: {row['Ração Diária (g)']}\n"
                mensagem += "\n📊 Mantenha as tigelas abastecidas!"
                await context.bot.send_message(chat_id=chat_id, text=mensagem, parse_mode="HTML")
        except Exception as e:
            print(f"Erro relatório diário: {e}")

def main():
    request_config = HTTPXRequest(connect_timeout=20, read_timeout=20)
    
    while True:
        try:
            application = Application.builder().token(TELEGRAM_TOKEN).request(request_config).build()
            application.job_queue.run_daily(envio_diario_meio_dia, time=datetime.time(hour=12, minute=0, second=0))
            
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("baixar", baixar_planilha))
            application.add_handler(CommandHandler("remover", remover_gato))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_mensagem))
            
            print("🚀 Bot ativo com máquina de estados!")
            application.run_polling(drop_pending_updates=True)
        except Exception as erro_rede:
            print(f"Erro: {erro_rede}. Reiniciando em 10 segundos...")
            time.sleep(10)

if __name__ == "__main__":
    main()
    
