--[[
	Main (Script — roda no servidor)
	Inicializa todos os sistemas na ordem certa e conecta entrada/saída
	de jogadores.

	Local no Studio: ServerScriptService > Server > Main
	(Com Rojo este arquivo vira um Script automaticamente por causa do .server)
]]

local Players = game:GetService("Players")

-- nós controlamos quando o personagem nasce (não deixa o Roblox nascer sozinho)
Players.CharacterAutoLoads = false

local Server = script.Parent
local DataManager   = require(Server.DataManager)
local Spawner       = require(Server.Spawner)
local CombatManager = require(Server.CombatManager)
local ShopManager   = require(Server.ShopManager)
local MapGenerator  = require(Server.MapGenerator)
local MatchManager  = require(Server.MatchManager)

-- inicializa sistemas
CombatManager.Init()
ShopManager.Init(DataManager)
MatchManager.Init({
	DataManager = DataManager,
	Spawner = Spawner,
	CombatManager = CombatManager,
	MapGenerator = MapGenerator,
})

-- jogadores
Players.PlayerAdded:Connect(function(player)
	DataManager.Load(player)
	MatchManager.OnPlayerAdded(player)
end)

Players.PlayerRemoving:Connect(function(player)
	DataManager.Save(player)
	DataManager.Remove(player)
end)

-- salva todo mundo ao fechar o servidor
game:BindToClose(function()
	for _, player in ipairs(Players:GetPlayers()) do
		DataManager.Save(player)
	end
	task.wait(1)
end)

print("[BrawlArena] Servidor iniciado ✔")
