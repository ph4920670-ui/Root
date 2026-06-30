--[[
	DataManager (ModuleScript)
	Guarda os dados de cada jogador: moedas, brawlers desbloqueados, brawler
	selecionado, kills e vitórias. Salva com DataStore.

	IMPORTANTE: o DataStore só funciona em jogos PUBLICADOS com
	"Enable Studio Access to API Services" ligado (Game Settings > Security).
	Se estiver desligado, o jogo continua funcionando, só não salva entre
	sessões (usa valores padrão). Está tudo dentro de pcall, então não quebra.

	Local no Studio: ServerScriptService > Server > DataManager
]]

local DataStoreService = game:GetService("DataStoreService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local GameConfig = require(Shared.GameConfig)
local Net = require(Shared.Net)

local DataManager = {}

local store = DataStoreService:GetDataStore("BrawlArena_v1")
local cache = {}                  -- [player] = data
local syncEvent = Net.Event("Sync")

local function defaultData()
	return {
		Coins = GameConfig.StartingCoins,
		Owned = table.clone(GameConfig.StartingBrawlers),
		Selected = GameConfig.StartingBrawlers[1],
		Kills = 0,
		Wins = 0,
	}
end

-- Garante que dados antigos tenham todos os campos novos
local function reconcile(data)
	local base = defaultData()
	for key, value in pairs(base) do
		if data[key] == nil then
			data[key] = value
		end
	end
	-- garante que o brawler inicial sempre esteja desbloqueado
	for _, name in ipairs(GameConfig.StartingBrawlers) do
		if not table.find(data.Owned, name) then
			table.insert(data.Owned, name)
		end
	end
	return data
end

function DataManager.Load(player)
	local data
	local ok, result = pcall(function()
		return store:GetAsync("p_" .. player.UserId)
	end)
	if ok and result then
		data = reconcile(result)
	else
		if not ok then
			warn("[DataManager] Falha ao carregar (usando padrão):", result)
		end
		data = defaultData()
	end
	cache[player] = data
	DataManager.Sync(player)
	return data
end

function DataManager.Save(player)
	local data = cache[player]
	if not data then
		return
	end
	local ok, err = pcall(function()
		store:SetAsync("p_" .. player.UserId, data)
	end)
	if not ok then
		warn("[DataManager] Falha ao salvar:", err)
	end
end

function DataManager.Remove(player)
	cache[player] = nil
end

function DataManager.Get(player)
	return cache[player]
end

-- Manda os dados pro cliente atualizar a interface
function DataManager.Sync(player)
	local data = cache[player]
	if data then
		syncEvent:FireClient(player, {
			Coins = data.Coins,
			Owned = data.Owned,
			Selected = data.Selected,
			Kills = data.Kills,
			Wins = data.Wins,
		})
	end
end

function DataManager.AddCoins(player, amount)
	local data = cache[player]
	if data then
		data.Coins += amount
		DataManager.Sync(player)
	end
end

function DataManager.IncrementKills(player)
	local data = cache[player]
	if data then
		data.Kills += 1
		DataManager.Sync(player)
	end
end

function DataManager.IncrementWins(player)
	local data = cache[player]
	if data then
		data.Wins += 1
		DataManager.Sync(player)
	end
end

return DataManager
