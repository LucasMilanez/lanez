# Documento de Requisitos — Lanez Fase 1: Fundação

## Introdução

A Fase 1 do Lanez estabelece a fundação do pipeline de dados do Microsoft 365. O objetivo é implementar o fluxo completo de autenticação OAuth 2.0 com Microsoft Entra ID, integração com a Microsoft Graph API para quatro serviços (Calendar, Mail, OneNote, OneDrive), recebimento de notificações em tempo real via webhooks, cache Redis com TTLs diferenciados por serviço, e armazenamento persistente em PostgreSQL. Esta fase não inclui embeddings, busca semântica, MCP server ou frontend.

## Glossário

- **Sistema**: A aplicação backend Lanez construída com FastAPI
- **Servidor_Auth**: Módulo responsável pelo fluxo OAuth 2.0 com Microsoft Entra ID
- **Cliente_Graph**: Módulo responsável por consumir a Microsoft Graph API
- **Gerenciador_Cache**: Módulo responsável por operações de cache no Redis
- **Gerenciador_Webhook**: Módulo responsável por gerenciar subscrições e processar notificações de webhooks da Microsoft
- **Repositório_Dados**: Camada de persistência PostgreSQL com asyncpg
- **Token_Pair**: Conjunto de access_token e refresh_token obtidos do Microsoft Entra ID
- **PKCE**: Proof Key for Code Exchange — extensão de segurança para o fluxo OAuth 2.0
- **TTL**: Time To Live — tempo de expiração de um item no cache
- **clientState**: Segredo compartilhado usado para validar notificações de webhook da Microsoft
- **ETag**: Identificador de versão de um recurso, usado para cache condicional
- **Graph_API**: Microsoft Graph API v1.0
- **Entra_ID**: Microsoft Entra ID (antigo Azure AD), provedor de identidade OAuth 2.0

## Requisitos

### Requisito 1: Início do Fluxo OAuth 2.0

**User Story:** Como usuário, quero ser redirecionado para o login da Microsoft ao acessar o endpoint de autenticação, para que eu possa autorizar o Lanez a acessar meus dados do Microsoft 365.

#### Critérios de Aceitação

1. WHEN o usuário acessa GET /auth/microsoft, THE Servidor_Auth SHALL gerar um code_verifier e code_challenge usando o método S256 conforme a especificação PKCE
2. WHEN o usuário acessa GET /auth/microsoft, THE Servidor_Auth SHALL redirecionar o usuário para o endpoint de autorização do Entra_ID com os parâmetros client_id, redirect_uri, response_type=code, scope, code_challenge e code_challenge_method
3. THE Servidor_Auth SHALL solicitar os escopos Calendars.Read, Mail.Read, Notes.Read, Files.Read, User.Read e offline_access na requisição de autorização
4. WHEN o usuário acessa GET /auth/microsoft, THE Servidor_Auth SHALL gerar um parâmetro state aleatório e incluí-lo na URL de redirecionamento para proteção contra CSRF

### Requisito 2: Callback OAuth e Troca de Tokens

**User Story:** Como usuário, quero que o sistema receba o código de autorização e obtenha os tokens de acesso, para que eu possa acessar meus dados do Microsoft 365 de forma segura.

#### Critérios de Aceitação

1. WHEN o Entra_ID redireciona para GET /auth/callback com um código de autorização válido, THE Servidor_Auth SHALL trocar o código por um Token_Pair usando o token endpoint do Entra_ID com o code_verifier correspondente
2. WHEN o Servidor_Auth recebe um Token_Pair válido, THE Repositório_Dados SHALL persistir o access_token e o refresh_token criptografados na tabela User
3. WHEN o Servidor_Auth recebe um Token_Pair válido, THE Repositório_Dados SHALL registrar o token_expires_at com base no campo expires_in da resposta do Entra_ID
4. IF o parâmetro state retornado pelo Entra_ID não corresponder ao state original, THEN THE Servidor_Auth SHALL rejeitar a requisição com status HTTP 400
5. IF o Entra_ID retornar um erro no callback, THEN THE Servidor_Auth SHALL retornar uma resposta HTTP 400 com a descrição do erro

### Requisito 3: Renovação de Tokens

**User Story:** Como usuário, quero que o sistema renove automaticamente meu token de acesso, para que eu mantenha acesso contínuo aos meus dados sem precisar re-autenticar.

#### Critérios de Aceitação

1. WHEN uma requisição POST /auth/refresh é recebida com um user_id válido, THE Servidor_Auth SHALL usar o refresh_token armazenado para obter um novo Token_Pair do Entra_ID
2. WHEN o Entra_ID retorna um novo Token_Pair, THE Repositório_Dados SHALL atualizar o access_token, refresh_token e token_expires_at criptografados na tabela User
3. IF o refresh_token armazenado for inválido ou expirado, THEN THE Servidor_Auth SHALL retornar status HTTP 401 indicando que re-autenticação é necessária
4. THE Servidor_Auth SHALL NEVER log token values in any log output or error message

### Requisito 4: Segurança de Tokens

**User Story:** Como operador do sistema, quero que os tokens sejam armazenados de forma segura, para que credenciais de usuários não sejam expostas em caso de acesso indevido ao banco de dados.

#### Critérios de Aceitação

1. THE Repositório_Dados SHALL criptografar o access_token e o refresh_token antes de persistir na tabela User usando uma chave derivada da variável SECRET_KEY
2. THE Repositório_Dados SHALL descriptografar os tokens somente no momento do uso, mantendo-os criptografados em repouso
3. THE Sistema SHALL carregar a SECRET_KEY exclusivamente de variáveis de ambiente, sem valores padrão no código-fonte
4. FOR ALL operações de log do Sistema, THE Sistema SHALL omitir valores de tokens, substituindo-os por marcadores de redação


### Requisito 5: Consulta de Eventos do Calendário

**User Story:** Como usuário, quero consultar meus eventos do Outlook Calendar via Lanez, para que assistentes de IA possam acessar minha agenda.

#### Critérios de Aceitação

1. WHEN uma requisição GET /me/events é recebida com um user_id autenticado, THE Cliente_Graph SHALL consultar o endpoint /me/events da Graph_API usando o access_token do usuário
2. WHEN a Graph_API retorna eventos com sucesso, THE Gerenciador_Cache SHALL armazenar a resposta no Redis com TTL de 5 minutos e chave baseada no user_id e serviço "calendar"
3. WHILE existir uma entrada válida no cache para o user_id e serviço "calendar", THE Gerenciador_Cache SHALL retornar os dados do cache sem consultar a Graph_API
4. WHEN a Graph_API retorna eventos com sucesso, THE Repositório_Dados SHALL persistir os dados na tabela GraphCache com o service "calendar"
5. IF a Graph_API retornar status HTTP 401, THEN THE Cliente_Graph SHALL tentar renovar o access_token e repetir a requisição uma vez

### Requisito 6: Consulta de Mensagens de Email

**User Story:** Como usuário, quero consultar minhas mensagens do Outlook Mail via Lanez, para que assistentes de IA possam acessar meus emails.

#### Critérios de Aceitação

1. WHEN uma requisição GET /me/messages é recebida com um user_id autenticado, THE Cliente_Graph SHALL consultar o endpoint /me/messages da Graph_API usando o access_token do usuário
2. WHEN a Graph_API retorna mensagens com sucesso, THE Gerenciador_Cache SHALL armazenar a resposta no Redis com TTL de 5 minutos e chave baseada no user_id e serviço "mail"
3. WHILE existir uma entrada válida no cache para o user_id e serviço "mail", THE Gerenciador_Cache SHALL retornar os dados do cache sem consultar a Graph_API
4. WHEN a Graph_API retorna mensagens com sucesso, THE Repositório_Dados SHALL persistir os dados na tabela GraphCache com o service "mail"
5. IF a Graph_API retornar status HTTP 401, THEN THE Cliente_Graph SHALL tentar renovar o access_token e repetir a requisição uma vez

### Requisito 7: Consulta de Páginas do OneNote

**User Story:** Como usuário, quero consultar minhas páginas do OneNote via Lanez, para que assistentes de IA possam acessar minhas anotações.

#### Critérios de Aceitação

1. WHEN uma requisição GET /me/onenote/pages é recebida com um user_id autenticado, THE Cliente_Graph SHALL consultar o endpoint /me/onenote/pages da Graph_API usando o access_token do usuário
2. WHEN a Graph_API retorna páginas com sucesso, THE Gerenciador_Cache SHALL armazenar a resposta no Redis com TTL de 15 minutos e chave baseada no user_id e serviço "onenote"
3. WHILE existir uma entrada válida no cache para o user_id e serviço "onenote", THE Gerenciador_Cache SHALL retornar os dados do cache sem consultar a Graph_API
4. WHEN a Graph_API retorna páginas com sucesso, THE Repositório_Dados SHALL persistir os dados na tabela GraphCache com o service "onenote"
5. IF a Graph_API retornar status HTTP 401, THEN THE Cliente_Graph SHALL tentar renovar o access_token e repetir a requisição uma vez

### Requisito 8: Consulta de Arquivos do OneDrive

**User Story:** Como usuário, quero consultar meus arquivos do OneDrive via Lanez, para que assistentes de IA possam acessar meus documentos.

#### Critérios de Aceitação

1. WHEN uma requisição GET /me/drive/root/children é recebida com um user_id autenticado, THE Cliente_Graph SHALL consultar o endpoint /me/drive/root/children da Graph_API usando o access_token do usuário
2. WHEN a Graph_API retorna arquivos com sucesso, THE Gerenciador_Cache SHALL armazenar a resposta no Redis com TTL de 15 minutos e chave baseada no user_id e serviço "onedrive"
3. WHILE existir uma entrada válida no cache para o user_id e serviço "onedrive", THE Gerenciador_Cache SHALL retornar os dados do cache sem consultar a Graph_API
4. WHEN a Graph_API retorna arquivos com sucesso, THE Repositório_Dados SHALL persistir os dados na tabela GraphCache com o service "onedrive"
5. IF a Graph_API retornar status HTTP 401, THEN THE Cliente_Graph SHALL tentar renovar o access_token e repetir a requisição uma vez

### Requisito 9: Rate Limiting e Backoff

**User Story:** Como operador do sistema, quero que o sistema respeite os limites de taxa da Microsoft Graph API, para que o acesso não seja bloqueado por excesso de requisições.

#### Critérios de Aceitação

1. THE Cliente_Graph SHALL limitar requisições à Graph_API a no máximo 200 requisições por janela de 15 minutos por usuário
2. IF a Graph_API retornar status HTTP 429 (Too Many Requests), THEN THE Cliente_Graph SHALL aguardar o tempo indicado no header Retry-After antes de repetir a requisição
3. IF a Graph_API retornar status HTTP 429 sem header Retry-After, THEN THE Cliente_Graph SHALL aplicar exponential backoff começando em 1 segundo, dobrando a cada tentativa, até um máximo de 3 tentativas
4. THE Cliente_Graph SHALL registrar em log cada ocorrência de rate limiting com o user_id e o serviço afetado


### Requisito 10: Recebimento de Notificações de Webhook

**User Story:** Como usuário, quero que o sistema receba notificações em tempo real da Microsoft quando meus dados mudam, para que o cache seja atualizado sem polling.

#### Critérios de Aceitação

1. WHEN a Microsoft envia uma requisição POST /webhooks/graph com uma notificação de mudança, THE Gerenciador_Webhook SHALL validar que o campo clientState da notificação corresponde ao WEBHOOK_CLIENT_STATE configurado
2. IF o clientState da notificação não corresponder ao WEBHOOK_CLIENT_STATE configurado, THEN THE Gerenciador_Webhook SHALL rejeitar a notificação com status HTTP 403
3. WHEN a Microsoft envia uma requisição de validação POST /webhooks/graph com o parâmetro validationToken, THE Gerenciador_Webhook SHALL responder com status HTTP 200 e o validationToken no corpo da resposta em texto plano
4. WHEN uma notificação válida é recebida, THE Gerenciador_Webhook SHALL identificar o user_id e o serviço afetado a partir do recurso notificado
5. WHEN uma notificação válida é recebida, THE Gerenciador_Cache SHALL invalidar as entradas de cache do Redis correspondentes ao user_id e serviço afetado

### Requisito 11: Gerenciamento de Subscrições de Webhook

**User Story:** Como operador do sistema, quero gerenciar as subscrições de webhook da Microsoft Graph, para que o sistema receba notificações de forma confiável.

#### Critérios de Aceitação

1. WHEN um usuário completa a autenticação OAuth com sucesso, THE Gerenciador_Webhook SHALL criar subscrições de webhook na Graph_API para os recursos calendar, mail, onenote e onedrive do usuário
2. THE Gerenciador_Webhook SHALL incluir o WEBHOOK_CLIENT_STATE como clientState em cada subscrição criada
3. WHEN uma subscrição é criada com sucesso, THE Repositório_Dados SHALL persistir os dados da subscrição na tabela WebhookSubscription incluindo subscription_id, resource, client_state e expires_at
4. WHEN uma requisição GET /webhooks/subscriptions é recebida, THE Gerenciador_Webhook SHALL retornar a lista de subscrições ativas do usuário autenticado
5. WHILE uma subscrição estiver a menos de 60 minutos de expirar, THE Gerenciador_Webhook SHALL renovar a subscrição na Graph_API antes que expire (limite máximo de 4230 minutos)
6. IF a renovação de uma subscrição falhar, THEN THE Gerenciador_Webhook SHALL criar uma nova subscrição e registrar o erro em log

### Requisito 12: Cache Redis com TTL por Serviço

**User Story:** Como operador do sistema, quero que respostas da Graph API sejam cacheadas com TTLs diferenciados por serviço, para que o sistema minimize requisições à API e respeite os rate limits.

#### Critérios de Aceitação

1. THE Gerenciador_Cache SHALL armazenar respostas do serviço "calendar" no Redis com TTL de 300 segundos (5 minutos)
2. THE Gerenciador_Cache SHALL armazenar respostas do serviço "mail" no Redis com TTL de 300 segundos (5 minutos)
3. THE Gerenciador_Cache SHALL armazenar respostas do serviço "onenote" no Redis com TTL de 900 segundos (15 minutos)
4. THE Gerenciador_Cache SHALL armazenar respostas do serviço "onedrive" no Redis com TTL de 900 segundos (15 minutos)
5. THE Gerenciador_Cache SHALL usar chaves de cache no formato "lanez:{user_id}:{service}" para garantir isolamento entre usuários e serviços
6. WHEN o Gerenciador_Webhook recebe uma notificação válida de mudança, THE Gerenciador_Cache SHALL remover imediatamente a entrada de cache correspondente ao user_id e serviço afetado

### Requisito 13: Modelo de Dados User

**User Story:** Como desenvolvedor, quero um modelo de dados User bem definido, para que tokens e informações de usuário sejam armazenados de forma estruturada.

#### Critérios de Aceitação

1. THE Repositório_Dados SHALL criar a tabela User com as colunas: id (UUID, chave primária), email (string, único, não nulo), microsoft_access_token (string, criptografado), microsoft_refresh_token (string, criptografado), token_expires_at (datetime), created_at (datetime, padrão UTC atual) e last_sync_at (datetime, nulável)
2. THE Repositório_Dados SHALL gerar o id do User como UUID v4 automaticamente na criação
3. THE Repositório_Dados SHALL impedir a criação de dois registros User com o mesmo email

### Requisito 14: Modelo de Dados GraphCache

**User Story:** Como desenvolvedor, quero um modelo de dados GraphCache bem definido, para que dados sincronizados da Graph API sejam persistidos de forma estruturada.

#### Critérios de Aceitação

1. THE Repositório_Dados SHALL criar a tabela GraphCache com as colunas: id (UUID, chave primária), user_id (UUID, chave estrangeira para User), service (string enum: calendar, mail, onenote, onedrive), resource_id (string), data (JSONB), cached_at (datetime, padrão UTC atual), expires_at (datetime) e etag (string, nulável)
2. THE Repositório_Dados SHALL criar um índice composto em (user_id, service, resource_id) na tabela GraphCache
3. WHEN um registro GraphCache é inserido com um user_id inexistente, THE Repositório_Dados SHALL rejeitar a operação com erro de integridade referencial

### Requisito 15: Modelo de Dados WebhookSubscription

**User Story:** Como desenvolvedor, quero um modelo de dados WebhookSubscription bem definido, para que subscrições de webhook sejam rastreadas de forma confiável.

#### Critérios de Aceitação

1. THE Repositório_Dados SHALL criar a tabela WebhookSubscription com as colunas: id (UUID, chave primária), user_id (UUID, chave estrangeira para User), subscription_id (string, único), resource (string), client_state (string), expires_at (datetime) e created_at (datetime, padrão UTC atual)
2. THE Repositório_Dados SHALL criar um índice em expires_at na tabela WebhookSubscription para consultas eficientes de subscrições próximas de expirar
3. WHEN um registro WebhookSubscription é inserido com um user_id inexistente, THE Repositório_Dados SHALL rejeitar a operação com erro de integridade referencial

### Requisito 16: Infraestrutura Docker Compose

**User Story:** Como desenvolvedor, quero um ambiente de desenvolvimento completo via Docker Compose, para que eu possa executar o sistema localmente com todos os serviços necessários.

#### Critérios de Aceitação

1. THE Sistema SHALL fornecer um arquivo docker-compose.yml que defina os serviços: app (FastAPI), db (PostgreSQL com pgvector) e redis (Redis)
2. THE Sistema SHALL fornecer um Dockerfile que construa a imagem da aplicação FastAPI com todas as dependências do requirements.txt
3. THE Sistema SHALL fornecer um arquivo .env.example documentando todas as variáveis de ambiente necessárias: MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID, MICROSOFT_REDIRECT_URI, DATABASE_URL, REDIS_URL, SECRET_KEY, WEBHOOK_CLIENT_STATE e CORS_ORIGINS
4. WHEN o comando docker-compose up é executado com um arquivo .env válido, THE Sistema SHALL iniciar todos os serviços e a aplicação FastAPI SHALL estar acessível na porta 8000
5. THE Sistema SHALL fornecer um arquivo requirements.txt com todas as dependências Python e versões fixadas

### Requisito 17: Configuração da Aplicação

**User Story:** Como desenvolvedor, quero que a aplicação carregue configurações de variáveis de ambiente de forma centralizada, para que a configuração seja consistente e segura.

#### Critérios de Aceitação

1. THE Sistema SHALL carregar todas as configurações a partir de variáveis de ambiente usando um módulo config.py centralizado
2. IF uma variável de ambiente obrigatória não estiver definida, THEN THE Sistema SHALL falhar na inicialização com uma mensagem de erro indicando a variável ausente
3. THE Sistema SHALL inicializar a conexão com PostgreSQL usando asyncpg como driver assíncrono
4. THE Sistema SHALL inicializar a conexão com Redis de forma assíncrona na inicialização da aplicação

### Requisito 18: Autenticação JWT para Endpoints de Dados

**User Story:** Como operador do sistema, quero que os endpoints de dados da Graph API sejam protegidos por autenticação JWT, para que apenas usuários autenticados possam acessar seus próprios dados.

#### Critérios de Aceitação

1. WHEN o callback OAuth completa com sucesso, THE Servidor_Auth SHALL emitir um JWT interno assinado com SECRET_KEY contendo o user_id e um tempo de expiração
2. THE Sistema SHALL expor uma dependency `get_current_user` que valida o JWT do header Authorization (Bearer token) e retorna o User correspondente do banco de dados
3. FOR ALL endpoints de dados da Graph API (GET /me/events, GET /me/messages, GET /me/onenote/pages, GET /me/drive/root/children), THE Sistema SHALL exigir um JWT válido via a dependency `get_current_user`
4. IF o JWT for inválido, expirado ou ausente, THEN THE Sistema SHALL retornar status HTTP 401
5. THE endpoint GET /webhooks/subscriptions SHALL também exigir autenticação JWT via `get_current_user`
6. THE endpoint POST /auth/refresh SHALL também exigir autenticação JWT via `get_current_user` em vez de receber user_id no body
