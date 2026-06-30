--[[
	MatchManager (ModuleScript)
	O "cérebro" do jogo. Controla o ciclo:
	  LOBBY -> CONTAGEM -> PARTIDA -> FIM -> (volta pro LOBBY)

	O servidor inteiro joga uma partida por vez (estilo simples). Quem está
	online entra na próxima partida. Também constrói o lobby por código.

	Local no Studio: ServerScriptService > Server > MatchManager
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local GameConfig = require(Shared.GameConfig)
local Maps = require(Shared.Maps)
local Net = require(Shared.Net)

local MatchManager = {}

-- dependências injetadas no Init
local DataManager
local Spawner
local CombatManager
local MapGenerator

local matchEvent = Net.Event("Match")
local notifyEvent = Net.Event("Notify")

-- O lobby fica bem alto pra não cruzar com os mapas (que ficam na origem)
local LOBBY_CENTER = Vector3.new(0, 500, 0)
local LOBBY_SPAWN_CFRAME = CFrame.new(LOBBY_CENTER + Vector3.new(0, 4, 0))

local phase = "LOBBY"      -- "LOBBY" | "COUNTDOWN" | "MATCH"
local matchActive = false
local currentMap = nil     -- Model do mapa atual
local currentMapDef = nil
local scores = {}          -- [player] = kills na partida atual
local timeLeft = 0

-- ===================================================================
-- LOBBY (construído por código)
-- ===================================================================
local function buildLobby()
	local model = Instance.new("Model")
	model.Name = "Lobby"

	local floor = Instance.new("Part")
	floor.Name = "LobbyFloor"
	floor.Anchored = true
	floor.Size = Vector3.new(60, 2, 60)
	floor.Position = LOBBY_CENTER
	floor.Color = Color3.fromRGB(70, 75, 95)
	floor.Material = Enum.Material.Metal
	floor.Parent = model

	-- bordas pra não cair
	for _, off in ipairs({
		Vector3.new(0, 0, 31), Vector3.new(0, 0, -31),
		Vector3.new(31, 0, 0), Vector3.new(-31, 0, 0),
	}) do
		local wall = Instance.new("Part")
		wall.Anchored = true
		wall.Size = (off.X ~= 0) and Vector3.new(2, 8, 62) or Vector3.new(62, 8, 2)
		wall.Position = LOBBY_CENTER + off + Vector3.new(0, 5, 0)
		wall.Color = Color3.fromRGB(50, 55, 70)
		wall.Material = Enum.Material.Metal
		wall.Parent = model
	end

	model.Parent = workspace
end

-- ===================================================================
-- HELPERS
-- ===================================================================
local function broadcastState(extra)
	local board = {}
	for player, kills in pairs(scores) do
		table.insert(board, { Name = player.Name, Kills = kills })
	end
	table.sort(board, function(a, b) return a.Kills > b.Kills end)

	local state = {
		Phase = phase,
		MapName = currentMapDef and currentMapDef.Name or "—",
		TimeLeft = math.max(0, math.floor(timeLeft)),
		KillsToWin = GameConfig.KillsToWin,
		Scores = board,
	}
	if extra then
		for k, v in pairs(extra) do
			state[k] = v
		end
	end
	matchEvent:FireAllClients(state)
end

local function getSelectedBrawler(player)
	local data = DataManager.Get(player)
	return data and data.Selected or GameConfig.StartingBrawlers[1]
end

local function randomMapSpawn()
	local points = currentMapDef.SpawnPoints
	local p = points[math.random(1, #points)]
	return CFrame.new(p)
end

-- ===================================================================
-- SPAWN no LOBBY
-- ===================================================================
local function onLobbyDeath(player)
	-- caiu no lobby: renasce no lobby (se ainda estamos no lobby)
	task.delay(1, function()
		if player.Parent and phase ~= "MATCH" then
			MatchManager.SpawnLobby(player)
		end
	end)
end

function MatchManager.SpawnLobby(player)
	local spot = LOBBY_SPAWN_CFRAME * CFrame.new(math.random(-20, 20), 0, math.random(-20, 20))
	Spawner.Spawn(player, getSelectedBrawler(player), spot, onLobbyDeath)
end

-- ===================================================================
-- SPAWN na PARTIDA + mortes
-- ===================================================================
local function onMatchDeath(victim)
	local attacker = CombatManager.GetLastAttacker(victim)
	CombatManager.ClearLastAttacker(victim)

	if attacker and attacker ~= victim and scores[attacker] ~= nil then
		scores[attacker] += 1
		DataManager.AddCoins(attacker, GameConfig.CoinsPerKill)
		DataManager.IncrementKills(attacker)
		notifyEvent:FireClient(attacker, "Abateu " .. victim.Name .. "! +" .. GameConfig.CoinsPerKill .. " 🪙")

		if scores[attacker] >= GameConfig.KillsToWin then
			matchActive = false
		end
	end

	broadcastState()

	-- renasce se a partida ainda estiver rolando
	task.delay(GameConfig.RespawnDelay, function()
		if matchActive and victim.Parent and scores[victim] ~= nil then
			MatchManager.SpawnMatch(victim)
		end
	end)
end

function MatchManager.SpawnMatch(player)
	Spawner.Spawn(player, getSelectedBrawler(player), randomMapSpawn(), onMatchDeath)
end

-- ===================================================================
-- CICLO PRINCIPAL
-- ===================================================================
local function runLobby()
	phase = "LOBBY"
	matchActive = false
	currentMapDef = nil
	if currentMap then
		currentMap:Destroy()
		currentMap = nil
	end
	for _, player in ipairs(Players:GetPlayers()) do
		MatchManager.SpawnLobby(player)
	end
	broadcastState()

	-- espera ter jogadores suficientes
	while #Players:GetPlayers() < GameConfig.MinPlayersToStart do
		task.wait(1)
	end
end

local function runCountdown()
	phase = "COUNTDOWN"
	for t = GameConfig.LobbyCountdown, 1, -1 do
		if #Players:GetPlayers() < GameConfig.MinPlayersToStart then
			return false -- gente saiu, cancela
		end
		broadcastState({ Countdown = t })
		task.wait(1)
	end
	return true
end

local function runMatch()
	phase = "MATCH"
	matchActive = true

	-- escolhe um mapa aleatório e constrói
	currentMapDef = Maps[math.random(1, #Maps)]
	currentMap = MapGenerator.Build(currentMapDef)

	-- prepara placar e nasce todo mundo
	scores = {}
	for _, player in ipairs(Players:GetPlayers()) do
		scores[player] = 0
	end
	for _, player in ipairs(Players:GetPlayers()) do
		MatchManager.SpawnMatch(player)
	end

	notifyEvent:FireAllClients("Partida iniciada no mapa: " .. currentMapDef.Name)

	-- relógio da partida
	timeLeft = GameConfig.MatchDurationSeconds
	while matchActive and timeLeft > 0 do
		broadcastState()
		task.wait(1)
		timeLeft -= 1
	end
	matchActive = false
end

local function endMatch()
	-- acha o vencedor (mais kills)
	local winner, best = nil, -1
	for player, kills in pairs(scores) do
		if kills > best then
			best = kills
			winner = player
		end
	end

	-- recompensas
	for player in pairs(scores) do
		if player.Parent then
			DataManager.AddCoins(player, GameConfig.CoinsPerMatch)
		end
	end
	if winner and winner.Parent then
		DataManager.AddCoins(winner, GameConfig.CoinsPerWin)
		DataManager.IncrementWins(winner)
	end

	broadcastState({ Winner = winner and winner.Name or "—" })
	notifyEvent:FireAllClients(
		(winner and ("🏆 " .. winner.Name .. " venceu com " .. best .. " kills!") or "Fim da partida!")
		.. " +" .. GameConfig.CoinsPerMatch .. " 🪙 (vencedor +" .. GameConfig.CoinsPerWin .. ")"
	)

	task.wait(5)
	scores = {}
end

-- ===================================================================
-- INIT
-- ===================================================================
function MatchManager.OnPlayerAdded(player)
	-- quem entra começa no lobby (entra na próxima partida)
	MatchManager.SpawnLobby(player)
	DataManager.Sync(player)
end

function MatchManager.Init(deps)
	DataManager = deps.DataManager
	Spawner = deps.Spawner
	CombatManager = deps.CombatManager
	MapGenerator = deps.MapGenerator

	buildLobby()

	task.spawn(function()
		while true do
			runLobby()
			local ok = runCountdown()
			if ok then
				runMatch()
				endMatch()
			end
		end
	end)
end

return MatchManager
