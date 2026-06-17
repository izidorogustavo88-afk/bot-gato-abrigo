import os
import logging
import datetime
import asyncio
import time
import pandas as pd
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
NOME_PLANILHA = "gatos_abrigo.xlsx"

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

historicos = {}      
usuarios_ativos = set() 

INSTRUCOES_AGENTE = """
Você é o assistente de um abrigo de animais. Sua única função é entrevistar o cuidador humano para cadastrar um gato.
REGRAS OBRIGATÓRIAS:
1. Sempre trate o usuário como um cuidador humano.
2. Nunca pergunte "Qual é o seu peso?". Sempre pergunte "Qual é o peso do gato?".
3. Se o usuário disser um nome, responda exatamente: "Perfeito, anotado. Agora, qual é o peso atual do gato (em kg)?" e aguarde a resposta dele.
4. Seja direto, profissional e foque apenas nos dados do animal (Nome, Peso, Porte/Altura).
5. NUNCA use asteriscos (*) ou símbolos semelhantes para destacar texto. Escreva em texto limpo.
6. Após coletar o Nome, Peso e Porte, calcule a ração diária (regra: 15g a 20g de ração por quilo do gato ao dia) e encerre informando que o felino foi registrado.
"""

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
    historicos[chat_id] = [{"role": "system", "content": INSTRUCOES_AGENTE}]
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
    chat_id = update.effective_chat.id
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
            if chat_id in historicos:
                historicos[chat_id] = [{"role": "system", "content": INSTRUCOES_AGENTE}]
            await update.message.reply_text(f"✅ <b>Sucesso!</b> O gato <b>{nome_alvo}</b> foi removido do sistema.", parse_mode="HTML")
        else:
            await update.message.reply_text(f"❌ O gato <b>{nome_alvo}</b> não foi encontrado.", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ A planilha está vazia.", parse_mode="HTML")

async def responder_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    texto_usuario = update.message.text
    
    if chat_id not in historicos:
        historicos[chat_id] = [{"role": "system", "content": INSTRUCOES_AGENTE}]
    usuarios_ativos.add(chat_id)
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    historicos[chat_id].append({"role": "user", "content": texto_usuario})
    
    prompt_ajuda = "[Instrução interna: Continue o fluxo de perguntas do gato. Se já calculou o resultado final da ração, adicione estritamente no final do texto: 'DATA_UPDATE: NomeDoGato, PesoDoGato, GramasDeRacao'. Não use asteriscos.]"
    historicos[chat_id][-1]["content"] += f"\n{prompt_ajuda}"
    
    try:
        loop = asyncio.get_event_loop()
        resposta = await loop.run_in_executor(
            None, 
            lambda: client.chat.completions.create(
                model="meta-llama/llama-3-8b-instruct:free",
                messages=historicos[chat_id]
            )
        )
        texto_resposta = resposta.choices[0].message.content.replace("*", "")
    except Exception as e:
        print(f"Erro na IA: {e}")
        await update.message.reply_text("⚠️ Ocorreu uma instabilidade na comunicação com a IA. Por favor, tente repetir o envio.")
        return

    historicos[chat_id][-1]["content"] = texto_usuario
    
    if "DATA_UPDATE:" in texto_resposta:
        partes = texto_resposta.split("DATA_UPDATE:")
        texto_exibir = partes[0].strip()
        try:
            dados = partes[1].strip().split(",")
            salvar_no_excel(dados[0].strip(), dados[1].strip(), dados[2].strip())
            texto_exibir += "\n\n<b>✅ [Sistema]: Gato registrado com sucesso na planilha Excel do abrigo!</b>"
        except Exception as e:
            print(f"Erro Excel: {e}")
    else:
        texto_exibir = texto_resposta
        
    historicos[chat_id].append({"role": "assistant", "content": texto_exibir})
    await update.message.reply_text(texto_exibir, parse_mode="HTML")

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
            
            print("🚀 Bot ativo e rodando no servidor!")
            application.run_polling(drop_pending_updates=True)
        except Exception as erro_rede:
            print(f"Desconexão de rede detectada: {erro_rede}. Reiniciando bot em 10 segundos...")
            time.sleep(10)

if __name__ == "__main__":
    main()
            
