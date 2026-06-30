# 🎮 Brawl Arena — Jogo estilo Brawl Stars (Roblox)

Jogo de batalha em arena onde os jogadores **desbloqueiam personagens (brawlers)** com moedas, escolhem qual usar e disputam partidas em **3 mapas** diferentes. Tudo pronto pra rodar no Roblox Studio.

## ✨ O que já vem pronto

- **4 brawlers** com vida, dano, alcance e habilidade especial diferentes (Shelly grátis; Colt, Bull e Piper compráveis)
- **Loja** pra comprar e selecionar brawlers
- **Moedas** ganhas por abate, participação e vitória
- **3 mapas** construídos automaticamente por código (você **não precisa** montar cenário à mão)
- **Sistema de partida completo**: lobby → contagem → batalha → vencedor → recompensa → recomeça
- **Combate** com tiro (dano em cone), vida, respawn, escudo ao nascer e **Super** (habilidade especial)
- **Interface** com moedas, placar ao vivo, estado da partida e avisos
- **Funciona no PC e no celular** (mouse + tecla Q, ou botões na tela)
- **Salvamento** de progresso com DataStore

---

## 🚀 Como colocar no Roblox Studio

Você tem dois caminhos. O **Jeito A (manual)** é o mais simples se você nunca usou ferramentas externas.

### Jeito A — Manual (copiar e colar)

Abra o Roblox Studio com um lugar (Baseplate serve) e crie esta estrutura usando o painel **Explorer** (botão direito > Insert Object):

```
ReplicatedStorage
└── Shared (Folder)
    ├── GameConfig (ModuleScript)   ← cole src/Shared/GameConfig.lua
    ├── Brawlers   (ModuleScript)   ← cole src/Shared/Brawlers.lua
    ├── Maps       (ModuleScript)   ← cole src/Shared/Maps.lua
    └── Net        (ModuleScript)   ← cole src/Shared/Net.lua

ServerScriptService
└── Server (Folder)
    ├── Main           (Script)        ← cole src/Server/Main.server.lua
    ├── DataManager    (ModuleScript)  ← cole src/Server/DataManager.lua
    ├── Spawner        (ModuleScript)  ← cole src/Server/Spawner.lua
    ├── CombatManager  (ModuleScript)  ← cole src/Server/CombatManager.lua
    ├── ShopManager    (ModuleScript)  ← cole src/Server/ShopManager.lua
    ├── MapGenerator   (ModuleScript)  ← cole src/Server/MapGenerator.lua
    └── MatchManager   (ModuleScript)  ← cole src/Server/MatchManager.lua

StarterPlayer
└── StarterPlayerScripts
    └── Client (LocalScript)         ← cole src/StarterPlayerScripts/Client.client.lua
```

**Atenção aos tipos** (isso é o que mais costuma dar erro):
- `Main` é um **Script** (server).
- `Client` é um **LocalScript**.
- Todo o resto é **ModuleScript**.
- Os **nomes** precisam ser exatamente os de cima (sem o `.lua`).

Depois é só apertar **Play** ▶️.

### Jeito B — Com Rojo (recomendado pra continuar editando no PC)

[Rojo](https://rojo.space) sincroniza estes arquivos direto pro Studio.

1. Instale o Rojo (via [Foreman](https://github.com/roblox/foreman) ou a extensão do VS Code).
2. Na pasta `RobloxGame/`, rode:
   ```bash
   rojo serve
   ```
3. No Studio, instale o plugin Rojo, clique em **Connect**.

O arquivo `default.project.json` já mapeia tudo pros lugares certos.

---

## 💾 Para salvar o progresso (moedas/brawlers) entre sessões

O salvamento usa **DataStore**, que só funciona se você:
1. **Publicar** o jogo (File > Publish to Roblox).
2. Ligar em **Game Settings > Security**: *Enable Studio Access to API Services*.

Sem isso o jogo roda normalmente, só não guarda o progresso (sempre começa do zero). Não trava nada — está tudo protegido com `pcall`.

---

## 🎯 Como jogar

| Ação | PC | Celular |
|------|----|---------|
| Mover | W A S D | Joystick |
| Atirar | Clique do mouse (mira no cursor) | Botão **ATIRAR** |
| Super | Tecla **Q** | Botão **SUPER** |
| Loja | Tecla **B** ou botão 🛒 | Botão 🛒 |

A partida começa sozinha quando há jogadores suficientes (por padrão **1**, pra você testar sozinho).

---

## 🔧 Ajustes rápidos

- **Balanceamento da partida** (tempo, kills pra vencer, moedas): `src/Shared/GameConfig.lua`
- **Criar/editar brawlers**: `src/Shared/Brawlers.lua` (copie um bloco e mude os valores)
- **Editar os mapas ou adicionar mais**: `src/Shared/Maps.lua`
- Pra exigir mais jogadores antes de começar, mude `MinPlayersToStart` no `GameConfig`.

## 🧱 Próximos passos (ideias)

- Modos de jogo (pega-bandeira, sobrevivência)
- Mais brawlers e habilidades únicas
- Sons e partículas nos tiros
- Skins e níveis de brawler
