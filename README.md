## Refrigerantes São Carlos - Chatbot WhatsApp (README)

Este é um chatbot para o WhatsApp que permite aos clientes fazer pedidos de refrigerantes da empresa "Refrigerantes São Carlos" de forma automatizada. O chatbot utiliza a API do OpenAI (GPT-4) para processar as mensagens, manter o contexto da conversa e guiar os usuários através de um fluxo de vendas.

**Funcionalidades Principais:**

*   **Fluxo de Vendas:**  Guia os clientes através de um fluxo de vendas completo, desde a saudação inicial até o resumo e finalização do pedido.
*   **Coleta de Informações:** Coleta informações essenciais do pedido, incluindo:
    *   Sabores dos refrigerantes (uva, limão, guaraná, laranja).
    *   Quantidades de cada sabor.
    *   CEP para cálculo do frete.
    *   Forma de pagamento (dinheiro, pix, cartão - *implementação simplificada*).
*   **Cálculo Automático:** Calcula o valor total do pedido e, *opcionalmente* (se integrado a uma API), o frete.
*   **Resumo do Pedido:** Apresenta um resumo claro do pedido antes da finalização.
*   **Armazenamento de Dados:** Salva os dados dos pedidos em um arquivo CSV para análise posterior.
*   **Humanização:** Respostas do chatbot são projetadas para serem amigáveis e cordiais, utilizando emojis e linguagem natural.
*   **Escalabilidade:** Utiliza técnicas assíncronas e thread pools para lidar com múltiplos usuários simultaneamente.

**Tecnologias Utilizadas:**

*   Python 3.10+
*   Flask (framework web)
*   Twilio (API para WhatsApp)
*   OpenAI (API para processamento de linguagem natural - GPT-4)
*   aiohttp (para requisições HTTP assíncronas)
*   asgiref (para compatibilidade Flask com Uvicorn)
*   uvicorn (servidor ASGI para alta performance)
*   python-dotenv (para carregar variáveis de ambiente)
*   csv (para salvar dados em CSV)
*   threading (para operações em threads)
*   concurrent.futures (para thread pools)

**Pré-requisitos:**

1.  **Python:** Certifique-se de ter o Python 3.10+ instalado em seu sistema.
2.  **Bibliotecas Python:**
    ```bash
    pip install flask twilio openai python-dotenv aiohttp uvicorn asgiref
    ```
3.  **Conta Twilio:**
    *   Crie uma conta na [Twilio](https://www.twilio.com/).
    *   Adquira um número de telefone Twilio habilitado para WhatsApp.
    *   Configure o WhatsApp para o seu número Twilio.  Você pode fazer isso no painel da Twilio ou, se estiver em sandbox, enviando uma mensagem para o número designado.
4.  **Chave de API do OpenAI:**
    *   Crie uma conta na [OpenAI](https://openai.com/).
    *   Obtenha uma chave de API.
5.  **ngrok (para testes locais):**
    *   Faça o download do [ngrok](https://ngrok.com/) e instale-o.  O ngrok é uma ferramenta que permite expor um servidor local à internet, o que é necessário para que o Twilio possa se comunicar com seu chatbot durante os testes.

**Configuração:**

1.  **Variáveis de Ambiente:**
    *   Crie um arquivo chamado `.env` no mesmo diretório do seu script Python.
    *   Adicione as seguintes variáveis de ambiente no arquivo `.env` (substituindo pelos seus valores reais):

    ```
    TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  # Seu Account SID da Twilio
    TWILIO_AUTH_TOKEN=your_auth_token                # Seu Auth Token da Twilio
    TWILIO_PHONE_NUMBER=+1234567890                   # Seu número Twilio (formato E.164)
    OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx        # Sua chave de API do OpenAI
    ```

2.  **Código Fonte:**
    *   Salve o código Python fornecido ( `app.py` ) no mesmo diretório que o arquivo `.env`.

3.  **Configuração do Webhook do Twilio:**
    *   Inicie seu aplicativo Flask localmente (veja as instruções de execução abaixo).
    *   Inicie o ngrok em um novo terminal para expor seu servidor local à internet:
        ```bash
        ngrok http 5000
        ```
        *   Anote a URL HTTPS fornecida pelo ngrok (por exemplo, `https://xxxxxxxx.ngrok.io`).
    *   No painel da Twilio, vá para a configuração do número de telefone WhatsApp que você está usando.
    *   Configure o webhook "Quando uma mensagem chega" ( *Messaging* ) para o endpoint `/whatsapp` do seu aplicativo Flask, usando a URL HTTPS do ngrok.  Por exemplo:
        ```
        https://xxxxxxxx.ngrok.io/whatsapp
        ```
    *   Selecione o método HTTP como `POST`.
    *   Salve as configurações.

**Execução:**

1.  **Execute o Servidor Flask:**
    *   Abra um terminal ou prompt de comando.
    *   Navegue até o diretório onde você salvou o arquivo `app.py`.
    *   Execute o seguinte comando:

    ```bash
    python app.py
    ```

    *   O servidor Flask será iniciado e exibirá mensagens no console.

2.  **Teste o Chatbot:**
    *   Envie uma mensagem WhatsApp para o número Twilio configurado.
    *   O chatbot responderá com uma saudação.  Siga as instruções do chatbot para fazer um pedido.

**Uso e Fluxo de Vendas:**

1.  **Início:** O chatbot cumprimenta o cliente e se apresenta.
2.  **Sabor:**  O chatbot pergunta qual sabor de refrigerante o cliente deseja (uva, limão, guaraná, laranja).
3.  **Quantidade:** O chatbot pergunta a quantidade desejada de cada sabor.
4.  **CEP:** O chatbot solicita o CEP para cálculo do frete (se o frete for variável).
5.  **Forma de Pagamento:** O chatbot pergunta sobre a forma de pagamento.
6.  **Resumo:** O chatbot apresenta um resumo do pedido (sabores, quantidades, valor total, frete, forma de pagamento).
7.  **Finalização:** O chatbot agradece o pedido e informa o prazo de entrega.
8.  **Novo Pedido:** O chatbot pergunta se o cliente deseja fazer outro pedido.

**Considerações:**

*   **Custos:** Lembre-se de que você incorrerá em custos associados à utilização das APIs do Twilio (mensagens WhatsApp) e OpenAI (uso do GPT-4).
*   **Limites de Taxa:** A API do OpenAI tem limites de taxa.  Se você tiver um grande volume de tráfego, pode precisar implementar estratégias para evitar exceder esses limites (ex: filas de mensagens).
*   **Testes:** Faça testes exaustivos para garantir que o chatbot funcione corretamente em todos os cenários possíveis.
*   **Segurança:** Proteja suas chaves de API e senhas. Não as inclua diretamente no código. Use variáveis de ambiente.
*   **Escalabilidade:** Para aplicações de produção, considere o uso de um banco de dados (em vez de CSV) para armazenar os dados dos pedidos e a escalabilidade horizontal do aplicativo.

**Próximos Passos (Sugestões):**

*   **Validação de Dados:** Implementar validação de dados (sabor, quantidade, CEP, forma de pagamento).
*   **Integração com API de Frete:** Integrar o chatbot com uma API de cálculo de frete (Correios, etc.).
*   **Pagamento:** Implementar a coleta da forma de pagamento (dinheiro, pix, cartão) e integração com um gateway de pagamento.
*   **Interface do Usuário:** Considerar a utilização de menus interativos no WhatsApp, se suportado, para melhorar a experiência do usuário.
*   **Monitoramento:** Implementar monitoramento para rastrear o desempenho do chatbot (tempo de resposta, taxa de erros, etc.).
