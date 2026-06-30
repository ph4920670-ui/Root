--[[
	Spawner (ModuleScript)
	Nasce o personagem com o brawler escolhido (vida, velocidade, cor),
	adiciona nome + barra de vida flutuando, e um efeito ao nascer.

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
	humanoid.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None -- esconde o nome padrão

	character:SetAttribute("Brawler", brawlerName)

	for _, part in ipairs(character:GetDescendants()) do
		if part:IsA("BasePart") and part.Name ~= "HumanoidRootPart" then
			part.Color = data.Color
			part.Material = Enum.Material.SmoothPlastic
		end
	end
end

-- monta o "chapéu/capacete" da skin e prende na cabeça
local HAT_PRESETS = {
	Cap    = { Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.6, 2.2, 2.2), Offset = 0.7,  Rotate = true },
	Box    = { Shape = Enum.PartType.Block,    Size = Vector3.new(2.2, 1.0, 2.2), Offset = 0.9,  Rotate = false },
	Helmet = { Shape = Enum.PartType.Ball,     Size = Vector3.new(2.4, 2.4, 2.4), Offset = 0.4,  Rotate = false },
	Cone   = { Shape = Enum.PartType.Cylinder, Size = Vector3.new(2.2, 1.6, 1.6), Offset = 1.0,  Rotate = true },
}

local function applySkin(character, skin)
	if not skin then
		return
	end
	-- tamanho do personagem
	if skin.Scale and skin.Scale ~= 1 then
		pcall(function()
			character:ScaleTo(skin.Scale)
		end)
	end
	-- chapéu
	local preset = HAT_PRESETS[skin.Hat]
	local head = character:FindFirstChild("Head")
	if preset and head then
		local hat = Instance.new("Part")
		hat.Name = "BrawlHat"
		hat.Shape = preset.Shape
		hat.Size = preset.Size
		hat.Color = skin.HatColor or Color3.fromRGB(60, 60, 60)
		hat.Material = Enum.Material.SmoothPlastic
		hat.CanCollide = false
		hat.Massless = true
		local cf = head.CFrame * CFrame.new(0, head.Size.Y / 2 + preset.Offset, 0)
		if preset.Rotate then
			cf = cf * CFrame.Angles(0, 0, math.rad(90)) -- deita o cilindro como "boné"
		end
		hat.CFrame = cf
		hat.Parent = character

		local weld = Instance.new("WeldConstraint")
		weld.Part0 = hat
		weld.Part1 = head
		weld.Parent = hat
	end
end

-- nome + barra de vida acima da cabeça
local function addNameplate(character, player)
	local head = character:FindFirstChild("Head")
	local humanoid = character:FindFirstChildOfClass("Humanoid")
	if not head or not humanoid then
		return
	end

	local bb = Instance.new("BillboardGui")
	bb.Name = "Nameplate"
	bb.Size = UDim2.new(0, 130, 0, 40)
	bb.StudsOffset = Vector3.new(0, 2.8, 0)
	bb.AlwaysOnTop = true
	bb.MaxDistance = 200
	bb.Adornee = head
	bb.Parent = head

	local nameLabel = Instance.new("TextLabel")
	nameLabel.Size = UDim2.new(1, 0, 0.5, 0)
	nameLabel.BackgroundTransparency = 1
	nameLabel.Font = Enum.Font.GothamBold
	nameLabel.TextSize = 15
	nameLabel.TextColor3 = Color3.fromRGB(255, 255, 255)
	nameLabel.TextStrokeTransparency = 0.3
	nameLabel.Text = player.Name
	nameLabel.Parent = bb

	local barBg = Instance.new("Frame")
	barBg.Size = UDim2.new(0.85, 0, 0.28, 0)
	barBg.Position = UDim2.new(0.075, 0, 0.62, 0)
	barBg.BackgroundColor3 = Color3.fromRGB(18, 18, 24)
	barBg.BorderSizePixel = 0
	barBg.Parent = bb
	local c1 = Instance.new("UICorner")
	c1.CornerRadius = UDim.new(1, 0)
	c1.Parent = barBg

	local fill = Instance.new("Frame")
	fill.Size = UDim2.new(1, 0, 1, 0)
	fill.BorderSizePixel = 0
	fill.Parent = barBg
	local c2 = Instance.new("UICorner")
	c2.CornerRadius = UDim.new(1, 0)
	c2.Parent = fill

	local function update()
		local ratio = humanoid.MaxHealth > 0 and math.clamp(humanoid.Health / humanoid.MaxHealth, 0, 1) or 0
		fill.Size = UDim2.new(ratio, 0, 1, 0)
		fill.BackgroundColor3 = Color3.fromRGB(
			math.floor(235 * (1 - ratio)) + 20,
			math.floor(200 * ratio) + 40,
			70
		)
	end
	update()
	humanoid.HealthChanged:Connect(update)
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

-- efeito visual ao nascer (anel que sobe)
local function spawnEffect(character, color)
	local root = character:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end
	local ring = Instance.new("Part")
	ring.Shape = Enum.PartType.Cylinder
	ring.Anchored = true
	ring.CanCollide = false
	ring.CanQuery = false
	ring.Material = Enum.Material.Neon
	ring.Color = color
	ring.Size = Vector3.new(0.4, 7, 7)
	ring.CFrame = CFrame.new(root.Position - Vector3.new(0, 2.5, 0)) * CFrame.Angles(0, 0, math.rad(90))
	ring.Parent = workspace
	task.spawn(function()
		for i = 1, 12 do
			ring.CFrame = ring.CFrame + Vector3.new(0, 0.4, 0)
			ring.Transparency = i / 12
			task.wait(0.03)
		end
		ring:Destroy()
	end)
end

function Spawner.Spawn(player, brawlerName, cframe, onDied)
	player:LoadCharacter()
	local character = player.Character or player.CharacterAdded:Wait()
	local humanoid = character:WaitForChild("Humanoid")

	applyBrawler(character, brawlerName)
	applySkin(character, (Brawlers[brawlerName] or {}).Skin)
	character:PivotTo(cframe)
	addNameplate(character, player)
	addSpawnProtection(character)

	local data = Brawlers[brawlerName] or Brawlers[GameConfig.StartingBrawlers[1]]
	spawnEffect(character, data.Color)

	if onDied then
		humanoid.Died:Once(function()
			onDied(player, character)
		end)
	end

	return character
end

return Spawner
