# Testar o app do executor no seu celular

Pré-requisito: celular e computador na **mesma rede Wi-Fi** (redes de convidados/corporativas costumam bloquear — se não abrir, use o roteamento/hotspot do próprio celular).

1. **Descubra o IP do computador**: no `cmd`, `ipconfig` → "Endereço IPv4" (ex.: `192.168.0.15`).
2. **Apague o banco antigo** (a demonstração ganhou locais e novos campos): na pasta do projeto, `del data\missao.db*`
3. **Suba a plataforma aceitando conexões da rede** (troque pelo seu IP — ele faz o link de confirmação funcionar no celular):
```
set BASE_URL=http://192.168.0.15:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
4. **Firewall do Windows**: se aparecer o aviso, clique em *Permitir* (rede privada). Se não aparecer e o celular não abrir, rode o `cmd` **como administrador**:
`netsh advfirewall firewall add rule name="MissaoSJP" dir=in action=allow protocol=TCP localport=8000,9000`
5. **No celular**, abra `http://192.168.0.15:8000/m/` e entre com `exec3` / `demo123`.

## O que funciona por HTTP e o que exige HTTPS
| Funciona | Exige HTTPS (ou localhost) |
|---|---|
| Login, missões, foto pela câmera, impedimento, concluir, ranking, chat, notificações no app | **GPS** ("Iniciar" com localização e "mais perto de mim"), instalar como app (PWA), Web Push |

Sem GPS, "Qual a mais perto de mim?" usa a **central** como ponto de partida e avisa na tela; e a sugestão após concluir uma missão **funciona normalmente** (parte do local da OS).

## Para testar o GPS
- **Android + Chrome**: abra `chrome://flags`, procure *Insecure origins treated as secure*, ative e digite `http://192.168.0.15:8000`; reinicie o Chrome.
- **iPhone/qualquer um**: use um túnel HTTPS temporário só para o teste (ex.: `cloudflared tunnel --url http://localhost:8000`), com dados fictícios — **não use dados reais** nesse caso, pois o tráfego passa por um serviço externo.
- Em produção: HTTPS interno (proxy reverso com certificado da prefeitura).

## Dica de demonstração
Abra o painel do gestor no computador e o app no celular lado a lado: ao atribuir uma missão no PC, o aviso chega ao celular em tempo real.
