--[[
	MatchManager (ModuleScript)
	Cérebro do jogo: LOBBY -> CONTAGEM -> PARTIDA -> FIM -> repete.
	Também cria BOTS inimigos no meio do mapa (pra jogar/treinar sozinho):
	eles têm vida, dão moeda quando abatidos e renascem.

	Local no Studio: ServerScriptService > Server > MatchManager
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local GameConfig = require(Shared.GameConfig)
local Maps = require(Shared.Maps)
local Net = require(Shared.Net)

local MatchManager = {}

local DataManager
local Spawner
local CombatManager
local MapGenerator

local matchEvent = Net.Event("Match")
local notifyEvent = Net.Event("Notify")

local LOBBY_CENTER = Vector3.new(0, 500, 0)
local LOBBY_SPAWN_CFRAME = CFrame.new(LOBBY_CENTER + Vector3.new(0, 4, 0))

local BOT_COUNT = 3
local BOT_HEALTH = 80
local BOT_RESPAWN = 4

local phase = "LOBBY"
local matchActive = false
local currentMap = nil
local currentMapDef = nil
local enemiesFolder = nil
local scores = {}
local timeLeft = 0

-- ===================================================================
-- LOBBY
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
-- BOTS INIMIGOS
-- ===================================================================
local function botHealthBar(model, humanoid)
	local head = model:FindFirstChild("Head")
	if not head then
		return
	end
	local bb = Instance.new("BillboardGui")
	bb.Size = UDim2.new(0, 90, 0, 28)
	bb.StudsOffset = Vector3.new(0, 2.4, 0)
	bb.AlwaysOnTop = true
	bb.Adornee = head
	bb.Parent = head

	local label = Instance.new("TextLabel")
	label.Size = UDim2.new(1, 0, 0.5, 0)
	label.BackgroundTransparency = 1
	label.Font = Enum.Font.GothamBold
	label.TextSize = 13
	label.TextColor3 = Color3.fromRGB(255, 120, 120)
	label.TextStrokeTransparency = 0.3
	label.Text = "BOT"
	label.Parent = bb

	local bg = Instance.new("Frame")
	bg.Size = UDim2.new(1, 0, 0.32, 0)
	bg.Position = UDim2.new(0, 0, 0.6, 0)
	bg.BackgroundColor3 = Color3.fromRGB(18, 18, 24)
	bg.BorderSizePixel = 0
	bg.Parent = bb
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(1, 0)
	c.Parent = bg

	local fill = Instance.new("Frame")
	fill.BackgroundColor3 = Color3.fromRGB(230, 70, 70)
	fill.BorderSizePixel = 0
	fill.Size = UDim2.new(1, 0, 1, 0)
	fill.Parent = bg
	local c2 = Instance.new("UICorner")
	c2.CornerRadius = UDim.new(1, 0)
	c2.Parent = fill

	humanoid.HealthChanged:Connect(function()
		local r = humanoid.MaxHealth > 0 and math.clamp(humanoid.Health / humanoid.MaxHealth, 0, 1) or 0
		fill.Size = UDim2.new(r, 0, 1, 0)
	end)
end

local function buildBot(position)
	local model = Instance.new("Model")
	model.Name = "Bot"

	local hrp = Instance.new("Part")
	hrp.Name = "HumanoidRootPart"
	hrp.Size = Vector3.new(2, 2, 1)
	hrp.Transparency = 1
	hrp.Anchored = true
	hrp.CanCollide = false
	hrp.CFrame = CFrame.new(position)
	hrp.Parent = model

	local torso = Instance.new("Part")
	torso.Name = "Torso"
	torso.Size = Vector3.new(2.2, 2.4, 1.2)
	torso.Color = Color3.fromRGB(210, 60, 60)
	torso.Material = Enum.Material.SmoothPlastic
	torso.Anchored = true
	torso.CanCollide = false
	torso.CFrame = hrp.CFrame
	torso.Parent = model

	local head = Instance.new("Part")
	head.Name = "Head"
	head.Shape = Enum.PartType.Ball
	head.Size = Vector3.new(1.5, 1.5, 1.5)
	head.Color = Color3.fromRGB(240, 90, 90)
	head.Material = Enum.Material.SmoothPlastic
	head.Anchored = true
	head.CanCollide = false
	head.CFrame = hrp.CFrame * CFrame.new(0, 1.7, 0)
	head.Parent = model

	local humanoid = Instance.new("Humanoid")
	humanoid.RigType = Enum.HumanoidRigType.R6
	humanoid.RequiresNeck = false
	humanoid.MaxHealth = BOT_HEALTH
	humanoid.Health = BOT_HEALTH
	humanoid.Parent = model

	model.PrimaryPart = hrp
	botHealthBar(model, humanoid)
	return model, humanoid
end

local function onBotDeath(model)
	local attacker = CombatManager.GetLastAttacker(model)
	CombatManager.ClearLastAttacker(model)
	if attacker and attacker.Parent and scores[attacker] ~= nil then
		scores[attacker] += 1
		DataManager.AddCoins(attacker, GameConfig.CoinsPerKill)
		DataManager.IncrementKills(attacker)
		notifyEvent:FireClient(attacker, "Abateu um BOT! +" .. GameConfig.CoinsPerKill .. " 🪙")
		if scores[attacker] >= GameConfig.KillsToWin then
			matchActive = false
		end
	end
	local pos = model.PrimaryPart and model.PrimaryPart.Position
	model:Destroy()
	task.delay(BOT_RESPAWN, function()
		if matchActive and enemiesFolder and enemiesFolder.Parent and pos then
			MatchManager.SpawnBot(pos)
		end
	end)
end

function MatchManager.SpawnBot(position)
	local model, humanoid = buildBot(position)
	model.Parent = enemiesFolder
	humanoid.Died:Once(function()
		onBotDeath(model)
	end)
end

local function spawnBots()
	enemiesFolder = Instance.new("Folder")
	enemiesFolder.Name = "Enemies"
	enemiesFolder.Parent = workspace

	local spots = {
		Vector3.new(0, 4, 0),
		Vector3.new(12, 4, 8),
		Vector3.new(-12, 4, -8),
	}
	for i = 1, BOT_COUNT do
		MatchManager.SpawnBot(spots[i] or Vector3.new(0, 4, 0))
	end
end

local function clearBots()
	if enemiesFolder then
		enemiesFolder:Destroy()
		enemiesFolder = nil
	end
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
	return CFrame.new(points[math.random(1, #points)])
end

-- ===================================================================
-- SPAWN no LOBBY e na PARTIDA
-- ===================================================================
local function onLobbyDeath(player)
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

local function onMatchDeath(player, character)
	local attacker = CombatManager.GetLastAttacker(character)
	CombatManager.ClearLastAttacker(character)

	if attacker and attacker ~= player and scores[attacker] ~= nil then
		scores[attacker] += 1
		DataManager.AddCoins(attacker, GameConfig.CoinsPerKill)
		DataManager.IncrementKills(attacker)
		notifyEvent:FireClient(attacker, "Abateu " .. player.Name .. "! +" .. GameConfig.CoinsPerKill .. " 🪙")
		if scores[attacker] >= GameConfig.KillsToWin then
			matchActive = false
		end
	end

	broadcastState()

	task.delay(GameConfig.RespawnDelay, function()
		if matchActive and player.Parent and scores[player] ~= nil then
			MatchManager.SpawnMatch(player)
		end
	end)
end

function MatchManager.SpawnMatch(player)
	Spawner.Spawn(player, getSelectedBrawler(player), randomMapSpawn(), onMatchDeath)
end

-- ===================================================================
-- CICLO
-- ===================================================================
local function runLobby()
	phase = "LOBBY"
	matchActive = false
	currentMapDef = nil
	clearBots()
	if currentMap then
		currentMap:Destroy()
		currentMap = nil
	end
	for _, player in ipairs(Players:GetPlayers()) do
		MatchManager.SpawnLobby(player)
	end
	broadcastState()

	while #Players:GetPlayers() < GameConfig.MinPlayersToStart do
		task.wait(1)
	end
end

local function runCountdown()
	phase = "COUNTDOWN"
	for t = GameConfig.LobbyCountdown, 1, -1 do
		if #Players:GetPlayers() < GameConfig.MinPlayersToStart then
			return false
		end
		broadcastState({ Countdown = t })
		task.wait(1)
	end
	return true
end

local function runMatch()
	phase = "MATCH"
	matchActive = true

	currentMapDef = Maps[math.random(1, #Maps)]
	currentMap = MapGenerator.Build(currentMapDef)

	scores = {}
	for _, player in ipairs(Players:GetPlayers()) do
		scores[player] = 0
	end
	for _, player in ipairs(Players:GetPlayers()) do
		MatchManager.SpawnMatch(player)
	end

	spawnBots()

	notifyEvent:FireAllClients("Partida iniciada no mapa: " .. currentMapDef.Name)

	timeLeft = GameConfig.MatchDurationSeconds
	while matchActive and timeLeft > 0 do
		broadcastState()
		task.wait(1)
		timeLeft -= 1
	end
	matchActive = false
end

local function endMatch()
	local winner, best = nil, -1
	for player, kills in pairs(scores) do
		if kills > best then
			best = kills
			winner = player
		end
	end

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

function MatchManager.OnPlayerAdded(player)
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
			if runCountdown() then
				runMatch()
				endMatch()
			end
		end
	end)
end

return MatchManager
