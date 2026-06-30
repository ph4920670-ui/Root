--[[
	ShopManager (ModuleScript)
	Cuida da loja: comprar brawlers e selecionar qual brawler usar.

	Local no Studio: ServerScriptService > Server > ShopManager
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Brawlers = require(Shared.Brawlers)
local Net = require(Shared.Net)

local ShopManager = {}

local DataManager  -- injetado no Init pra evitar dependência circular

local buyEvent = Net.Event("BuyBrawler")
local selectEvent = Net.Event("SelectBrawler")
local notifyEvent = Net.Event("Notify")

local function notify(player, message)
	notifyEvent:FireClient(player, message)
end

function ShopManager.Init(dataManager)
	DataManager = dataManager

	buyEvent.OnServerEvent:Connect(function(player, brawlerName)
		local b = Brawlers[brawlerName]
		local data = DataManager.Get(player)
		if not b or not data then
			return
		end
		if table.find(data.Owned, brawlerName) then
			notify(player, "Você já tem o " .. b.DisplayName .. "!")
			return
		end
		if data.Coins < b.Price then
			notify(player, "Moedas insuficientes (" .. b.Price .. ").")
			return
		end
		data.Coins -= b.Price
		table.insert(data.Owned, brawlerName)
		data.Selected = brawlerName
		DataManager.Sync(player)
		notify(player, "Desbloqueou o " .. b.DisplayName .. "! 🎉")
	end)

	selectEvent.OnServerEvent:Connect(function(player, brawlerName)
		local data = DataManager.Get(player)
		if not data or not Brawlers[brawlerName] then
			return
		end
		if not table.find(data.Owned, brawlerName) then
			notify(player, "Você ainda não tem esse brawler.")
			return
		end
		data.Selected = brawlerName
		DataManager.Sync(player)
		notify(player, "Selecionado: " .. Brawlers[brawlerName].DisplayName)
	end)
end

return ShopManager
