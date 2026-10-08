# 🐱 CatFeed Bot - Gestão & Nutrição Felina

Bot para Telegram projetado para auxiliar no cálculo nutricional, controle alimentar e gestão de gatos em abrigos ou lares temporários, integrado à inteligência artificial (Llama-3 via OpenRouter) e sincronizado com planilhas Excel.

---

## 🚀 Funcionalidades

- **🧮 Cálculo Nutricional Personalizado:** Determina a porção diária ideal de ração com base no peso, idade e porte do felino.
- **📊 Gestão de Abrigo:** Cadastra, atualiza e remove gatos cadastrados em uma planilha Excel centralizada.
- **⏰ Relatórios Diários Automáticos:** Envio programado do relatório de alimentação todos os dias às 12:00.
- **🤖 Assistente IA com Llama-3:** Respostas inteligentes e contextualizadas sobre nutrição e cuidados felinos via OpenRouter API.

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.10+
- **Manipulação de Dados:** `pandas`, `openpyxl`
- **IA & LLM:** Llama-3 (via OpenRouter API)
- **Integração Telegram:** `python-telegram-bot`
- **Agendamento:** `APScheduler` / `schedule`
- **Deploy:** Railway

---

## 📂 Estrutura do Projeto

```text
.
├── bot.py                # Ponto de entrada e manipuladores do bot
├── config.py             # Leitura de variáveis de ambiente
├── excel_manager.py      # Operações de leitura/escrita na planilha Excel
├── ai_service.py         # Integração com OpenRouter (Llama-3)
├── scheduler.py          # Agendador de tarefas (Relatório diário das 12h)
├── data/
│   └── gatos.xlsx        # Base de dados dos gatos em formato Excel
├── requirements.txt      # Dependências do projeto
└── README.md

⚙️ Configuração e Instalação
Pré-requisitos
 * Python 3.10 ou superior
 * Token do Bot do Telegram (gerado via @BotFather)
 * Chave de API do OpenRouter
1. Clonar o repositório
git clone [https://github.com/seu-usuario/catfeed-bot.git](https://github.com/seu-usuario/catfeed-bot.git)
cd catfeed-bot

2. Criar e ativar o ambiente virtual
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

3. Instalar dependências
pip install -r requirements.txt

4. Configurar variáveis de ambiente
Crie um arquivo .env na raiz do projeto com as seguintes chaves:
TELEGRAM_BOT_TOKEN=seu_token_aqui
OPENROUTER_API_KEY=sua_chave_openrouter_aqui
CHAT_ID_RELATORIO=seu_chat_id_para_relatorios

🚀 Execução Local
python bot.py

☁️ Deploy no Railway
 * Crie um novo projeto no Railway apontando para o seu repositório no GitHub.
 * Adicione as variáveis de ambiente (TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY, etc.) no painel Variables do Railway.
 * O Railway identificará automaticamente o arquivo requirements.txt e fará o deploy da aplicação.
💬 Comandos do Bot
| Comando | Descrição |
|---|---|
| /start | Inicia a interação com o bot e exibe o menu principal. |
| /calcular | Inicia o fluxo de cálculo da porção diária de ração. |
| /cadastrar | Registra um novo gato na planilha do abrigo. |
| /remover | Remove um gato cadastrado da planilha. |
| /relatorio | Gera um relatório de alimentação imediato. |
| /ajuda | Exibe a lista de comandos e instruções gerais. |
📄 Licença
Este projeto está sob a licença MIT. Veja o arquivo LICENSE para mais detalhes.

