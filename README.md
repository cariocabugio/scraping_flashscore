✅ Compromisso de Qualidade — Aceito e Registrado
A partir de agora, toda atualização ou novo arquivo será entregue completo, sem abreviações, sem funções vazias e com todas as dependências internas funcionais. O erro que enfrentamos com as funções legadas generate_top_tickets e format_ticket (que ficaram apenas com pass) foi um deslize e não se repetirá. Você pode enviar o arquivo que deseja atualizar que devolverei a versão íntegra, pronta para uso.

📜 Relatório Histórico do Projeto Flashscore Ninja
🧭 Caminho Percorrido — Endpoints, Descobertas e Funcionalidades
Este documento registra as conquistas técnicas do projeto, os endpoints mapeados do Flashscore, as funcionalidades implementadas e as decisões arquiteturais. Serve como guia para manutenção futura e para replicar o sucesso.

🔍 1. Descoberta dos Endpoints da API Flashscore
A API oficial do Flashscore não é documentada publicamente. Todo o conhecimento foi obtido por observação do tráfego de rede (DevTools → Network) e engenharia reversa.

Endpoint	URL Base	Função	Status
H2H (Head‑to‑Head)	/feed/df_hh_1_{match_id}	Histórico de confrontos diretos (últimos 19 jogos de cada time)	✅ Funcional
Estatísticas ao vivo	/feed/df_st_1_{match_id}	xG, escanteios, posse de bola, finalizações	✅ Funcional
Eventos da partida	/feed/df_ml_1_{match_id}	Gols, cartões, substituições, escanteios (com código 20)	✅ Funcional
Detalhes da partida	/feed/dc_1_{match_id}	Árbitro, estádio, capacidade, canais de TV, feeds disponíveis	✅ Funcional
Classificação (tabela)	/feed/to_{season_id}_{tournament_id}_1	Lista de times, partidas futuras (LMU÷upcoming)	✅ Usado no Ultra Bingo
Torneio (jogos ao vivo/hoje)	/feed/t_1_{country}_{tournament}_-3_pt-br_1	Partidas do dia para um campeonato	✅ Fonte de IDs
Resultados ao vivo	/feed/r_1_1	Placar e status de múltiplos jogos	🟡 Monitoramento
Odds (GraphQL)	https://global.ds.lsapp.eu/odds/pq_graphql	Cotações 1X2 de várias casas	✅ Funcional
Feed de fixtures do dia	/feed/f_1_0_3_pt-br_1	Todos os jogos do dia (vários campeonatos)	🟡 Usado parcialmente
Feed de comentários	/feed/df_lcpo_1_{match_id}	Narração textual lance a lance	🟡 Futuro
Autenticação necessária
Header X-Fsign: SW9D1eZo (chave estática descoberta em js do site).

User‑Agent de navegador real.

Referer https://www.flashscore.com.br/.

🧱 2. Arquitetura do Projeto (Módulos)
A estrutura flashscore/ organiza o código em domínios reutilizáveis.

Módulo	Responsabilidades
fetcher.py	Requisições HTTP, leitura de arquivos locais, extração de IDs, busca de torneios
parser.py	Parsing dos feeds textuais (H2H, estatísticas, eventos, detalhes)
probabilities.py	Cálculo de probabilidades (1X2, Overs, Cantos), geração de bilhetes, enriquecimento com odds
odds_fetcher.py	Consulta à API GraphQL de odds, parse das respostas
telegram_sender.py	Envio assíncrono de mensagens formatadas para múltiplos chats
Scripts principais:

analisador_final.py — Análise individual de partidas.

rodada.py — Geração de bilhetes para múltiplos campeonatos.

monitor_ao_vivo.py — Monitoramento ao vivo com alertas.

⚙️ 3. Funcionalidades Implementadas
Análise pré‑jogo
Cálculo de probabilidades baseado nos últimos 19 jogos de cada time.

Modelagem de 1X2, Over/Under 0.5/1.5/2.5 gols e Cantos +8.5/+9.5/+10.5.

Peso por recência: jogos mais recentes têm maior influência (fator de decaimento 0.9).

Odds reais: integração com a API GraphQL para obter cotações 1X2 (bet365, Betano, 1xBet, Superbet).

Bilhetes otimizados: construção de 3 perfis (Conservador, Moderado, Turbo) com restrições de diversidade e priorização por Valor Esperado (EV).

Cache inteligente: armazenamento no Supabase para evitar requisições repetidas no mesmo dia.

Monitoramento ao vivo
Loop seguro com jitter e User‑Agent rotativo.

Projeção dinâmica de escanteios baseada no ritmo atual (cap de 15).

Projeção de gols a partir do xG.

Alertas de Over e Under para escanteios e gols.

Envio imediato via Telegram.

Gerador de Rodadas (Ultra Bingo)
Suporte a múltiplos campeonatos em um único comando.

Filtro por datas: --days 0 (hoje), --days 1 (amanhã), --days all (todas as futuras).

Extração de partidas futuras via feed de classificação (LMU÷upcoming).

Algoritmo guloso para montar bilhetes diversificados.

Cálculo de odd combinada real e EV total.

Banco de Dados (Supabase)
Tabelas:

matches — registros das partidas analisadas.

probabilities — histórico de probabilidades calculadas.

match_metadata — árbitro, estádio, TV, feeds disponíveis.

match_events — eventos codificados (gols, cartões, escanteios).

match_feeds — normalização dos tipos de feeds disponíveis.

tickets e ticket_selections — histórico de bilhetes gerados.

📚 4. Lições Aprendidas
Formato bruto Flashscore: SA÷1¬~KA÷Total... é a resposta padrão de todos os feeds textuais. Decifrar essa estrutura foi o ponto de virada.

GraphQL para odds: a API tradicional df_od_1 não funciona; o endpoint real é global.ds.lsapp.eu/odds/pq_graphql com parâmetros eventId, bookmakerId, betType, betScope.

Filtro de datas: jogos na China aparecem como --days 0 por causa do fuso; agora temos o offset correto.

Odds em seleções: usar enrich_selections_with_odds é a maneira correta de associar odds aos mercados, evitando erros de mapeamento manual.

Build incremental: manter o código estável e evoluir com módulos reutilizáveis garantiu a sustentabilidade do projeto.

🔮 5. Futuro (Próximos Passos)
Substituir o modelo fixo de cantos por médias históricas (já temos a base no match_events).

Implementar força do adversário (ELO‑like) para ajustar as probabilidades.

Integrar agente DeepSeek para sugerir e justificar bilhetes.

Modo "Rodada Automática" com agendamento diário.

Dashboard no Supabase para acompanhar a acurácia das previsões.
