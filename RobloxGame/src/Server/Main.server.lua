--[[
	Main (Script — roda no servidor)
	Inicializa todos os sistemas, configura a iluminação/atmosfera e conecta
	entrada/saída de jogadores.

	Local no Studio: ServerScriptService > Server > Main
]]

local Players = game:GetService("Players")
local Lighting = game:GetService("Lighting")

-- nós controlamos quando o personagem nasce (não deixa o Roblox nascer sozinho)
Players.CharacterAutoLoads = false

-- ===================================================================
-- VISUAL: iluminação + atmosfera bonitas (tira o cinza padrão)
-- ===================================================================
local function setupScene()
	Lighting.ClockTime = 14.5
	Lighting.Brightness = 2.6
	Lighting.Ambient = Color3.fromRGB(70, 70, 85)
	Lighting.OutdoorAmbient = Color3.fromRGB(125, 130, 150)
	Lighting.EnvironmentDiffuseScale = 0.45
	Lighting.EnvironmentSpecularScale = 0.45
	Lighting.GeographicLatitude = 25
	Lighting.ShadowSoftness = 0.4
	Lighting.FogEnd = 100000 -- remove a névoa cinza pesada

	for _, name in ipairs({ "BA_Atmosphere", "BA_Bloom", "BA_Color", "BA_Sky", "BA_Sun" }) do
		local old = Lighting:FindFirstChild(name)
		if old then
			old:Destroy()
		end
	end

	local atmo = Instance.new("Atmosphere")
	atmo.Name = "BA_Atmosphere"
	atmo.Density = 0.32
	atmo.Offset = 0.2
	atmo.Color = Color3.fromRGB(199, 215, 230)
	atmo.Decay = Color3.fromRGB(106, 112, 125)
	atmo.Glare = 0.15
	atmo.Haze = 1.4
	atmo.Parent = Lighting

	local bloom = Instance.new("BloomEffect")
	bloom.Name = "BA_Bloom"
	bloom.Intensity = 0.7
	bloom.Size = 24
	bloom.Threshold = 1.1
	bloom.Parent = Lighting

	local cc = Instance.new("ColorCorrectionEffect")
	cc.Name = "BA_Color"
	cc.Saturation = 0.18
	cc.Contrast = 0.1
	cc.Brightness = 0.02
	cc.Parent = Lighting

	local sun = Instance.new("SunRaysEffect")
	sun.Name = "BA_Sun"
	sun.Intensity = 0.12
	sun.Spread = 0.6
	sun.Parent = Lighting

	local sky = Instance.new("Sky")
	sky.Name = "BA_Sky"
	sky.Parent = Lighting

	-- sombras ligadas
	Lighting.GlobalShadows = true

	-- nuvens no céu (fundo no lugar do céu vazio)
	local terrain = workspace:FindFirstChildOfClass("Terrain")
	if terrain then
		local clouds = terrain:FindFirstChildOfClass("Clouds")
		if not clouds then
			clouds = Instance.new("Clouds")
			clouds.Parent = terrain
		end
		clouds.Cover = 0.6
		clouds.Density = 0.55
		clouds.Color = Color3.fromRGB(255, 255, 255)
	end
end

setupScene()

-- ===================================================================
-- SISTEMAS
-- ===================================================================
local Server = script.Parent
local DataManager   = require(Server.DataManager)
local Spawner       = require(Server.Spawner)
local CombatManager = require(Server.CombatManager)
local ShopManager   = require(Server.ShopManager)
local MapGenerator  = require(Server.MapGenerator)
local MatchManager  = require(Server.MatchManager)

CombatManager.Init()
ShopManager.Init(DataManager)
MatchManager.Init({
	DataManager = DataManager,
	Spawner = Spawner,
	CombatManager = CombatManager,
	MapGenerator = MapGenerator,
})

-- ===================================================================
-- JOGADORES
-- ===================================================================
local function onPlayerAdded(player)
	DataManager.Load(player)
	MatchManager.OnPlayerAdded(player)
end

-- cobre quem entrou ANTES do script ligar (importante no teste do Studio)
for _, player in ipairs(Players:GetPlayers()) do
	task.spawn(onPlayerAdded, player)
end
Players.PlayerAdded:Connect(onPlayerAdded)

Players.PlayerRemoving:Connect(function(player)
	DataManager.Save(player)
	DataManager.Remove(player)
end)

game:BindToClose(function()
	for _, player in ipairs(Players:GetPlayers()) do
		DataManager.Save(player)
	end
	task.wait(1)
end)

print("[BrawlArena] Servidor iniciado ✔")
