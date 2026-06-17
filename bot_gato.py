import os
import logging
import datetime
import asyncio
import time
import re
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
import pandas as pd

# PROTEÇÃO: Chaves lidas direto da Railway
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Garantindo o caminho correto para salvar e baixar na Railway
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
NOME_PLANILHA = os.path.join(PASTA_ATUAL, "gatos_abrigo.xlsx")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

historicos = {}      
usuarios_ativos = set() 

# PROMPT DO AGENTE DE IA (Otimizado para o Nvidia Nemotron)
INSTRUCOES_AGENTE = """
Você é o assistente virtual de IA de um abrigo de animais. Sua única função é entrevistar o cuidador para cadastrar um gato.
Você deve coletar três informações de forma natural e conversacional:
1. O Nome do gato.
2. O Peso atual do gato (em kg).
3. O Porte ou Altura (ex: pequeno, médio, grande ou em cm).

REGRAS OBRIGATÓRIAS:
- Faça apenas uma pergunta por vez. Seja simpático, profissional e direto.
- NUNCA use asteriscos (*) ou símbolos para destacar textos nas suas respostas.
- Assim que o usuário fornecer o Porte/Altura (a última informação), você deve calcular a ração diária (regra: 15g de ração por quilo do gato).
- Ao encerrar, informe ao usuário que o felino foi registrado com sucesso e adicione OBRIGATORIAMENTE no final do seu texto o marcador oculto exatamente neste formato:
DATA_UPDATE: NomeDoGato, PesoDoGato, GramasDeRacao
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

def tentar_salvar_backup_preventivo(historico_conversa):
    """
    Função extra de segurança: Se a IA esquecer o formato 'DATA_UPDATE:', 
    esta função varre o texto atrás dos dados e tenta salvar de qualquer forma.
    """
    texto_completo = " ".join([m["content"] for m in historico_conversa if m["role"] == "user"])
    texto_ia = " ".join([m["content"] for m in historico_conversa if m["role"] == "assistant"])
    
    # Procura padrões de peso (ex: 4kg, 4.5 kg, 5 quilos)
    pesos_encontrados = re.findall(r"(\d+[\.,]?\d*)\s*(?:kh|kg|quilo|kilo|kg)", texto_completo.lower())
    peso = pesos_encontrados[-1] if pesos_encontrados else "4"
    
    # Tenta estimar a ração baseado no peso encontrado
    try:
        peso_num = float(peso.replace(",", "."))
        racao = int(peso_num * 15)
    except:
        racao = 60

    # Pega a primeira palavra longa enviada como possível nome
    palavras = [p for p in texto_completo.split() if len(p) > 2 and "/" not in p and "kg" not in p.lower()]
    nome = palavras[0] if palavras else "Gato_Abrigo"
    
    # Se o fluxo parece ter terminado na IA, salva preventivamente
    if "registrado" in texto_ia.lower() or "sucesso" in texto_ia.lower() or "ração" in texto_ia.lower():
        salvar_no_excel(nome, f"{peso} kg", racao)
        return True
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    usuarios_ativos.add(chat_id)
    
    # Limpeza total da memória antiga ao digitar /start
    historicos[chat_id] = [{"role": "system", "content": INSTRUCOES_AGENTE}]
    
    saudacao = "🐾 <b>Sistema de Cadastro do Abrigo (Agente de IA Nvidia)</b> 🐾\n\nOlá! Sou o assistente de Inteligência Artificial do abrigo. Vamos registrar um novo gatinho.\n\nPara começar, me diga: Qual é o nome dele(a)?"
    await update.message.reply_text(saudacao, parse_mode="HTML")

async def baixar_planilha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(NOME_PLANILHA):
        await update.message.reply_text("📊 Gerando a planilha de cadastro do abrigo...")
        with open(NOME_PLANILHA, "rb") as arquivo:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=arquivo,
                filename="gatos_abrigo.xlsx",
                caption="🐱 Aqui está a planilha atualizada com os gatinhos cadastrados pelo Agente de IA!"
            )
    else:
        await update.message.reply_text("❌ Nenhuma planilha foi gerada ainda. Termine o cadastro de um gatinho com a IA para criá-la!")

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
            
            # Limpa a memória se o usuário estiver no meio de um cadastro errôneo
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
    
    try:
        loop = asyncio.get_event_loop()
        resposta = await loop.run_in_executor(
            None, 
            lambda: client.chat.completions.create(
                model="nvidia/nemotron-3-ultra-550b-a55b:free",
                messages=historicos[chat_id],
                temperature=0.3
            )
        )
        texto_resposta = resposta.choices[0].message.content.replace("*", "")
    except Exception as e:
        print(f"Erro na IA: {e}")
        await update.message.reply_text("⚠️ Ocorreu uma instabilidade temporária na IA. Por favor, tente enviar novamente.")
        return

    # Processamento do salvamento via IA ou via sistema de redundância
    if "DATA_UPDATE:" in texto_resposta:
        partes = texto_resposta.split("DATA_UPDATE:")
        texto_exibir = partes[0].strip()
        try:
            dados = partes[1].strip().split(",")
            salvar_no_excel(dados[0].strip(), dados[1].strip(), dados[2].strip())
            texto_exibir += "\n\n<b>✅ [Sistema]: Gato registrado com sucesso na planilha Excel pelo Agente de IA!</b>"
            
            # Limpa totalmente a memória assim que o cadastro é concluído com sucesso
            historicos[chat_id] = [{"role": "system", "content": INSTRUCOES_AGENTE}]
        except Exception as e:
            print(f"Erro ao processar dados da IA: {e}")
    else:
        texto_exibir = texto_resposta
        # Redundância de segurança caso a IA mude levemente o formato final de resposta
        if "registrado" in texto_resposta.lower() or "sucesso" in texto_resposta.lower():
            if tentar_salvar_backup_preventivo(historicos[chat_id]):
                texto_exibir += "\n\n<b>✅ [Sistema]: Dados salvos via redundância na planilha!</b>"
                
                # Limpa totalmente a memória na redundância também
                historicos[chat_id] = [{"role": "system", "content": INSTRUCOES_AGENTE}]

    # Só adiciona ao histórico se a memória não tiver sido resetada acima
    if chat_id in historicos and len(historicos[chat_id]) > 1:
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
            
            print("🚀 Agente de IA Nvidia ativo com isolamento de memória!")
            application.run_polling(drop_pending_updates=True)
        except Exception as erro_rede:
            print(f"Erro de rede: {erro_rede}. Reiniciando em 10 segundos...")
            time.sleep(10)

if __name__ == "__main__":
    main()
    
