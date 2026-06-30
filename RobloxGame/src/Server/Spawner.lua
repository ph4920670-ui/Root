--[[
	Spawner (ModuleScript)
	Responsável por nascer o personagem do jogador com o brawler escolhido,
	aplicando vida, velocidade e cor, e colocando na posição certa.

	Local no Studio: ServerScriptService > Server > Spawner
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Brawlers = require(Shared.Brawlers)
local GameConfig = require(Shared.GameConfig)

local Spawner = {}

local function applyBrawler(character, brawlerName)
	local data = Brawlers[brawlerName] or Brawlers[GameConfig.StartingBrawlers[1]]
	local humanoid = character:WaitForChild("Humanoid")

	humanoid.MaxHealth = data.Health
	humanoid.Health = data.Health
	humanoid.WalkSpeed = data.WalkSpeed

	-- guarda o brawler atual no personagem (o combate lê isso)
	character:SetAttribute("Brawler", brawlerName)

	-- pinta o corpo
	for _, part in ipairs(character:GetDescendants()) do
		if part:IsA("BasePart") and part.Name ~= "HumanoidRootPart" then
			part.Color = data.Color
			part.Material = Enum.Material.SmoothPlastic
		end
	end
end

local function addSpawnProtection(character)
	if GameConfig.SpawnProtection <= 0 then
		return
	end
	local ff = Instance.new("ForceField")
	ff.Visible = true
	ff.Parent = character
	task.delay(GameConfig.SpawnProtection, function()
		if ff and ff.Parent then
			ff:Destroy()
		end
	end)
end

-- Nasce o jogador com o brawler indicado, na CFrame indicada.
-- onDied: função chamada quando o Humanoid morrer (opcional).
function Spawner.Spawn(player, brawlerName, cframe, onDied)
	player:LoadCharacter()
	local character = player.Character or player.CharacterAdded:Wait()
	local humanoid = character:WaitForChild("Humanoid")

	applyBrawler(character, brawlerName)
	character:PivotTo(cframe)
	addSpawnProtection(character)

	if onDied then
		humanoid.Died:Once(function()
			onDied(player, character)
		end)
	end

	return character
end

return Spawner
