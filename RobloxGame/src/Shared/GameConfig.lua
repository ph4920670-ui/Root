--[[
	GameConfig (ModuleScript)
	Configurações gerais do jogo. Mexa aqui pra ajustar o balanceamento.
	Local no Studio: ReplicatedStorage > Shared > GameConfig
]]

local GameConfig = {
	-- ====== PARTIDA ======
	MinPlayersToStart = 1,        -- jogadores necessários pra começar (1 = bom pra testar sozinho)
	LobbyCountdown = 10,          -- segundos de contagem regressiva no lobby
	MatchDurationSeconds = 150,   -- duração máxima da partida
	KillsToWin = 12,              -- kills pra ganhar antes do tempo acabar
	RespawnDelay = 3,             -- tempo pra reviver após morrer (durante a partida)
	SpawnProtection = 2,          -- segundos de escudo ao nascer

	-- ====== ECONOMIA ======
	StartingCoins = 0,            -- moedas iniciais de um jogador novo
	CoinsPerKill = 12,            -- moedas por abate
	CoinsPerMatch = 15,           -- moedas de participação (ganha quem jogou a partida)
	CoinsPerWin = 60,             -- bônus extra pro vencedor

	-- ====== BRAWLERS INICIAIS ======
	StartingBrawlers = { "Shelly" }, -- brawlers que todo mundo já começa tendo
}

return GameConfig
