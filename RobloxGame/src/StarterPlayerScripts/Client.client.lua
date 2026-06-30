--[[
	Client (LocalScript)
	Interface, controles, câmera, efeitos, sons, minimapa e banners.

	Local no Studio: StarterPlayer > StarterPlayerScripts > Client (ou Cliente)
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")
local RunService = game:GetService("RunService")
local Debris = game:GetService("Debris")
local SoundService = game:GetService("SoundService")
local TweenService = game:GetService("TweenService")

local player = Players.LocalPlayer
local mouse = player:GetMouse()
local camera = workspace.CurrentCamera

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Brawlers = require(Shared.Brawlers)
local Maps = require(Shared.Maps)
local Net = require(Shared.Net)

local attackEvent = Net.Event("Attack")
local specialEvent = Net.Event("Special")
local buyEvent = Net.Event("BuyBrawler")
local selectEvent = Net.Event("SelectBrawler")
local syncEvent = Net.Event("Sync")
local matchEvent = Net.Event("Match")
local notifyEvent = Net.Event("Notify")
local fxEvent = Net.Event("AttackFX")
local hitEvent = Net.Event("Hit")

local myData = { Coins = 0, Owned = {}, Selected = "Shelly" }
local superCooldownUntil = 0
local superCooldownTotal = 1
local lastHealth = nil
local damageAlpha = 0
local currentHalf = 50
local currentPhase = "LOBBY"
local minimapClock = 0
local lastResult = 0

-- ===================================================================
-- HELPERS
-- ===================================================================
local function corner(parent, radius)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius or 8)
	c.Parent = parent
	return c
end

local function gradient(parent, c1, c2, rot)
	local g = Instance.new("UIGradient")
	g.Color = ColorSequence.new(c1, c2)
	g.Rotation = rot or 90
	g.Parent = parent
	return g
end

local function stroke(parent, color, thickness, transparency)
	local s = Instance.new("UIStroke")
	s.Color = color or Color3.fromRGB(0, 0, 0)
	s.Thickness = thickness or 1.5
	s.Transparency = transparency or 0.4
	s.Parent = parent
	return s
end

local function make(class, props, parent)
	local obj = Instance.new(class)
	for k, v in pairs(props) do
		obj[k] = v
	end
	if parent then
		obj.Parent = parent
	end
	return obj
end

-- ===================================================================
-- SONS (embutidos no Roblox, funcionam offline)
-- ===================================================================
local function makeSound(id, vol, pitch)
	local s = Instance.new("Sound")
	s.SoundId = id
	s.Volume = vol or 0.5
	s.PlaybackSpeed = pitch or 1
	s.Parent = SoundService
	return s
end
local shootSound = makeSound("rbxasset://sounds/electronicpingshort.wav", 0.25, 1.5)
local hitSound = makeSound("rbxasset://sounds/electronicpingshort.wav", 0.35, 0.85)
local superSound = makeSound("rbxasset://sounds/electronicpingshort.wav", 0.6, 0.5)
local buySound = makeSound("rbxasset://sounds/electronicpingshort.wav", 0.5, 1.1)

local function playSound(s)
	s.TimePosition = 0
	s:Play()
end

-- ===================================================================
-- CÂMERA estilo Brawl Stars
-- ===================================================================
local CAM_HEIGHT = 46
local CAM_BACK = 26
RunService:BindToRenderStep("BrawlCam", Enum.RenderPriority.Camera.Value + 1, function()
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end
	camera.CameraType = Enum.CameraType.Scriptable
	local target = root.Position
	local desired = CFrame.lookAt(target + Vector3.new(0, CAM_HEIGHT, CAM_BACK), target)
	local alpha = (camera.CFrame.Position - desired.Position).Magnitude > 120 and 1 or 0.16
	camera.CFrame = camera.CFrame:Lerp(desired, alpha)
end)

-- ===================================================================
-- INTERFACE
-- ===================================================================
local gui = make("ScreenGui", {
	Name = "HUD",
	ResetOnSpawn = false,
	IgnoreGuiInset = true,
	ZIndexBehavior = Enum.ZIndexBehavior.Sibling,
}, player:WaitForChild("PlayerGui"))

-- vinheta de dano (vermelho nas bordas)
local vigTop = make("Frame", {
	Size = UDim2.new(1, 0, 0, 150),
	BackgroundColor3 = Color3.fromRGB(255, 30, 30),
	BackgroundTransparency = 1,
	BorderSizePixel = 0,
}, gui)
do
	local g = Instance.new("UIGradient")
	g.Rotation = 90
	g.Transparency = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 0),
		NumberSequenceKeypoint.new(1, 1),
	})
	g.Parent = vigTop
end
local vigBot = make("Frame", {
	Size = UDim2.new(1, 0, 0, 150),
	Position = UDim2.new(0, 0, 1, -150),
	BackgroundColor3 = Color3.fromRGB(255, 30, 30),
	BackgroundTransparency = 1,
	BorderSizePixel = 0,
}, gui)
do
	local g = Instance.new("UIGradient")
	g.Rotation = 90
	g.Transparency = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 1),
		NumberSequenceKeypoint.new(1, 0),
	})
	g.Parent = vigBot
end

-- Barra superior
local topBar = make("Frame", {
	Size = UDim2.new(1, 0, 0, 54),
	BackgroundColor3 = Color3.fromRGB(28, 30, 42),
	BorderSizePixel = 0,
}, gui)
gradient(topBar, Color3.fromRGB(38, 41, 58), Color3.fromRGB(20, 22, 32))

local coinPill = make("Frame", {
	Size = UDim2.new(0, 150, 0, 36),
	Position = UDim2.new(0, 12, 0.5, -18),
	BackgroundColor3 = Color3.fromRGB(45, 40, 20),
}, topBar)
corner(coinPill, 18)
stroke(coinPill, Color3.fromRGB(255, 210, 90), 1.5, 0.3)
local coinsLabel = make("TextLabel", {
	Size = UDim2.new(1, 0, 1, 0),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 20,
	TextColor3 = Color3.fromRGB(255, 215, 90),
	Text = "🪙 0",
}, coinPill)

local brawlerLabel = make("TextLabel", {
	Size = UDim2.new(0, 300, 1, 0),
	Position = UDim2.new(0.5, -150, 0, 0),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 20,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "Brawler: Shelly",
}, topBar)

local matchLabel = make("TextLabel", {
	Size = UDim2.new(0, 380, 0, 30),
	Position = UDim2.new(0.5, -190, 0, 62),
	BackgroundColor3 = Color3.fromRGB(20, 22, 30),
	BackgroundTransparency = 0.25,
	Font = Enum.Font.GothamBold,
	TextSize = 18,
	TextColor3 = Color3.fromRGB(190, 235, 255),
	Text = "Aguardando...",
}, gui)
corner(matchLabel, 10)
stroke(matchLabel, Color3.fromRGB(120, 180, 255), 1.2, 0.5)

-- Placar
local scoreFrame = make("TextLabel", {
	Size = UDim2.new(0, 230, 0, 130),
	Position = UDim2.new(1, -242, 0, 96),
	BackgroundColor3 = Color3.fromRGB(20, 22, 30),
	BackgroundTransparency = 0.25,
	Font = Enum.Font.GothamMedium,
	TextSize = 16,
	TextColor3 = Color3.fromRGB(235, 235, 235),
	TextXAlignment = Enum.TextXAlignment.Left,
	TextYAlignment = Enum.TextYAlignment.Top,
	Text = "",
}, gui)
corner(scoreFrame, 10)
stroke(scoreFrame, Color3.fromRGB(60, 65, 85), 1, 0.4)
make("UIPadding", { PaddingLeft = UDim.new(0, 12), PaddingTop = UDim.new(0, 8) }, scoreFrame)

-- Barra de VIDA
local healthBg = make("Frame", {
	Size = UDim2.new(0, 280, 0, 24),
	Position = UDim2.new(0.5, -140, 1, -54),
	BackgroundColor3 = Color3.fromRGB(18, 18, 26),
}, gui)
corner(healthBg, 12)
stroke(healthBg, Color3.fromRGB(0, 0, 0), 2, 0.3)
local healthFill = make("Frame", {
	Size = UDim2.new(1, 0, 1, 0),
	BackgroundColor3 = Color3.fromRGB(80, 220, 100),
	BorderSizePixel = 0,
}, healthBg)
corner(healthFill, 12)
gradient(healthFill, Color3.fromRGB(120, 255, 140), Color3.fromRGB(60, 190, 90))
local healthText = make("TextLabel", {
	Size = UDim2.new(1, 0, 1, 0),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 15,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	TextStrokeTransparency = 0.4,
	Text = "100 / 100",
}, healthBg)

-- Minimapa
local minimap = make("Frame", {
	Size = UDim2.new(0, 150, 0, 150),
	Position = UDim2.new(0, 12, 1, -164),
	BackgroundColor3 = Color3.fromRGB(15, 17, 26),
	BackgroundTransparency = 0.2,
	Visible = false,
}, gui)
corner(minimap, 10)
stroke(minimap, Color3.fromRGB(90, 120, 255), 1.5, 0.3)
local dotsFolder = make("Frame", { Size = UDim2.new(1, 0, 1, 0), BackgroundTransparency = 1 }, minimap)

-- Aviso (toast)
local toast = make("TextLabel", {
	Size = UDim2.new(0, 440, 0, 38),
	Position = UDim2.new(0.5, -220, 0.7, 0),
	BackgroundColor3 = Color3.fromRGB(30, 32, 44),
	Font = Enum.Font.GothamBold,
	TextSize = 18,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "",
	TextTransparency = 1,
}, gui)
toast.BackgroundTransparency = 1
corner(toast, 10)

-- Banner de Vitória/Derrota
local resultBanner = make("TextLabel", {
	Size = UDim2.new(0, 560, 0, 100),
	Position = UDim2.new(0.5, -280, 0.32, -50),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBlack,
	TextSize = 60,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	TextStrokeTransparency = 0.2,
	Text = "",
	Visible = false,
}, gui)

-- Botão da loja
local shopBtn = make("TextButton", {
	Size = UDim2.new(0, 120, 0, 38),
	Position = UDim2.new(1, -132, 0.5, -19),
	BackgroundColor3 = Color3.fromRGB(95, 125, 255),
	Font = Enum.Font.GothamBold,
	TextSize = 18,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "🛒 Loja (B)",
}, topBar)
corner(shopBtn, 10)
gradient(shopBtn, Color3.fromRGB(120, 150, 255), Color3.fromRGB(80, 100, 230))
stroke(shopBtn, Color3.fromRGB(180, 200, 255), 1.2, 0.3)

-- Botões de combate (maiores p/ mobile)
local attackBtn = make("TextButton", {
	Size = UDim2.new(0, 130, 0, 130),
	Position = UDim2.new(1, -150, 1, -162),
	BackgroundColor3 = Color3.fromRGB(225, 70, 70),
	Font = Enum.Font.GothamBold,
	TextSize = 20,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "ATIRAR",
	AutoButtonColor = true,
}, gui)
corner(attackBtn, 65)
gradient(attackBtn, Color3.fromRGB(255, 100, 100), Color3.fromRGB(200, 45, 45))
stroke(attackBtn, Color3.fromRGB(255, 180, 180), 2.5, 0.15)

local specialBtn = make("TextButton", {
	Size = UDim2.new(0, 104, 0, 104),
	Position = UDim2.new(1, -286, 1, -148),
	BackgroundColor3 = Color3.fromRGB(245, 195, 50),
	Font = Enum.Font.GothamBold,
	TextSize = 17,
	TextColor3 = Color3.fromRGB(50, 35, 0),
	Text = "SUPER\n(Q)",
	ClipsDescendants = true,
}, gui)
corner(specialBtn, 52)
gradient(specialBtn, Color3.fromRGB(255, 225, 90), Color3.fromRGB(230, 170, 30))
stroke(specialBtn, Color3.fromRGB(255, 235, 160), 2.5, 0.15)
local superCd = make("Frame", {
	Size = UDim2.new(1, 0, 0, 0),
	BackgroundColor3 = Color3.fromRGB(0, 0, 0),
	BackgroundTransparency = 0.45,
	BorderSizePixel = 0,
	ZIndex = 2,
}, specialBtn)

-- ===================================================================
-- LOJA
-- ===================================================================
local shopOpen = false
local shopFrame = make("Frame", {
	Size = UDim2.new(0, 480, 0, 410),
	Position = UDim2.new(0.5, -240, 0.5, -205),
	BackgroundColor3 = Color3.fromRGB(26, 28, 40),
	Visible = false,
}, gui)
corner(shopFrame, 16)
stroke(shopFrame, Color3.fromRGB(90, 120, 255), 2.5, 0.15)
gradient(shopFrame, Color3.fromRGB(36, 39, 58), Color3.fromRGB(20, 22, 34))

make("TextLabel", {
	Size = UDim2.new(1, 0, 0, 48),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBlack,
	TextSize = 26,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "🛒 LOJA DE BRAWLERS",
}, shopFrame)

local closeBtn = make("TextButton", {
	Size = UDim2.new(0, 38, 0, 38),
	Position = UDim2.new(1, -46, 0, 6),
	BackgroundColor3 = Color3.fromRGB(225, 70, 70),
	Font = Enum.Font.GothamBold,
	TextSize = 20,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "X",
}, shopFrame)
corner(closeBtn, 10)

local list = make("ScrollingFrame", {
	Size = UDim2.new(1, -20, 1, -60),
	Position = UDim2.new(0, 10, 0, 52),
	BackgroundTransparency = 1,
	BorderSizePixel = 0,
	ScrollBarThickness = 6,
	CanvasSize = UDim2.new(0, 0, 0, 0),
	AutomaticCanvasSize = Enum.AutomaticSize.Y,
}, shopFrame)
make("UIListLayout", { Padding = UDim.new(0, 8), SortOrder = Enum.SortOrder.LayoutOrder }, list)

local function refreshShop()
	for _, child in ipairs(list:GetChildren()) do
		if child:IsA("Frame") then
			child:Destroy()
		end
	end

	local names = {}
	for name in pairs(Brawlers) do
		table.insert(names, name)
	end
	table.sort(names, function(a, b) return Brawlers[a].Price < Brawlers[b].Price end)

	for _, name in ipairs(names) do
		local b = Brawlers[name]
		local owned = table.find(myData.Owned, name) ~= nil
		local selected = (myData.Selected == name)

		local row = make("Frame", {
			Size = UDim2.new(1, -6, 0, 66),
			BackgroundColor3 = Color3.fromRGB(38, 41, 56),
		}, list)
		corner(row, 12)
		stroke(row, selected and Color3.fromRGB(80, 220, 120) or Color3.fromRGB(60, 65, 85), selected and 2 or 1, 0.35)

		local swatch = make("Frame", {
			Size = UDim2.new(0, 46, 0, 46),
			Position = UDim2.new(0, 12, 0.5, -23),
			BackgroundColor3 = b.Color,
		}, row)
		corner(swatch, 12)
		stroke(swatch, Color3.fromRGB(255, 255, 255), 1.5, 0.5)

		make("TextLabel", {
			Size = UDim2.new(0, 210, 1, 0),
			Position = UDim2.new(0, 68, 0, 0),
			BackgroundTransparency = 1,
			Font = Enum.Font.GothamBold,
			TextSize = 17,
			TextColor3 = Color3.fromRGB(255, 255, 255),
			TextXAlignment = Enum.TextXAlignment.Left,
			Text = b.DisplayName .. "\n❤️" .. b.Health .. "   ⚔️" .. b.Damage .. "   🎯" .. b.Range,
		}, row)

		local btn = make("TextButton", {
			Size = UDim2.new(0, 124, 0, 44),
			Position = UDim2.new(1, -134, 0.5, -22),
			Font = Enum.Font.GothamBold,
			TextSize = 16,
			TextColor3 = Color3.fromRGB(255, 255, 255),
		}, row)
		corner(btn, 10)

		if selected then
			btn.Text = "✔ EM USO"
			btn.BackgroundColor3 = Color3.fromRGB(60, 170, 95)
		elseif owned then
			btn.Text = "USAR"
			btn.BackgroundColor3 = Color3.fromRGB(80, 120, 220)
			btn.MouseButton1Click:Connect(function()
				selectEvent:FireServer(name)
			end)
		else
			btn.Text = "🪙 " .. b.Price
			btn.BackgroundColor3 = Color3.fromRGB(230, 170, 40)
			btn.MouseButton1Click:Connect(function()
				buyEvent:FireServer(name)
			end)
		end
	end
end

local function toggleShop()
	shopOpen = not shopOpen
	shopFrame.Visible = shopOpen
	if shopOpen then
		refreshShop()
	end
end

shopBtn.MouseButton1Click:Connect(toggleShop)
closeBtn.MouseButton1Click:Connect(toggleShop)

-- ===================================================================
-- CONTROLES
-- ===================================================================
local function getAimDirection()
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not root then
		return nil
	end
	-- mira no chão (altura do personagem) embaixo do cursor
	local ray = mouse.UnitRay
	local origin, dirv = ray.Origin, ray.Direction
	if math.abs(dirv.Y) > 1e-4 then
		local t = (root.Position.Y - origin.Y) / dirv.Y
		if t > 0 then
			local hit = origin + dirv * t
			local d = Vector3.new(hit.X - root.Position.X, 0, hit.Z - root.Position.Z)
			if d.Magnitude > 0.1 then
				return d.Unit
			end
		end
	end
	local look = root.CFrame.LookVector
	return Vector3.new(look.X, 0, look.Z).Unit
end

-- efeito local ao usar o Super (anel que se expande)
local function superBurst()
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end
	local b = Brawlers[myData.Selected]
	local color = b and b.Color or Color3.new(1, 1, 1)
	local ring = make("Part", {
		Anchored = true,
		CanCollide = false,
		CanQuery = false,
		Shape = Enum.PartType.Cylinder,
		Material = Enum.Material.Neon,
		Color = color,
		Size = Vector3.new(0.6, 4, 4),
		CFrame = CFrame.new(root.Position - Vector3.new(0, 2.5, 0)) * CFrame.Angles(0, 0, math.rad(90)),
	}, workspace)
	task.spawn(function()
		for i = 1, 12 do
			ring.Size = ring.Size + Vector3.new(0, 4, 4)
			ring.Transparency = i / 12
			task.wait(0.02)
		end
		ring:Destroy()
	end)
end

local function doAttack()
	local dir = getAimDirection()
	if dir then
		attackEvent:FireServer(dir)
	end
end

local function doSpecial()
	if os.clock() < superCooldownUntil then
		return
	end
	local dir = getAimDirection()
	if dir then
		specialEvent:FireServer(dir)
		playSound(superSound)
		superBurst()
		local b = Brawlers[myData.Selected]
		local cd = b and b.Special and b.Special.Cooldown or 8
		superCooldownTotal = cd
		superCooldownUntil = os.clock() + cd
	end
end

attackBtn.MouseButton1Click:Connect(doAttack)
specialBtn.MouseButton1Click:Connect(doSpecial)

UserInputService.InputBegan:Connect(function(input, processed)
	if processed then
		return
	end
	if input.UserInputType == Enum.UserInputType.MouseButton1 then
		doAttack()
	elseif input.KeyCode == Enum.KeyCode.Q then
		doSpecial()
	elseif input.KeyCode == Enum.KeyCode.B then
		toggleShop()
	end
end)

-- ===================================================================
-- BANNER de Vitória/Derrota
-- ===================================================================
local function showResult(winnerName)
	if os.clock() - lastResult < 6 then
		return
	end
	lastResult = os.clock()
	local win = (winnerName == player.Name)
	resultBanner.Text = win and "🏆 VITÓRIA!" or "💀 DERROTA"
	resultBanner.TextColor3 = win and Color3.fromRGB(120, 255, 150) or Color3.fromRGB(255, 110, 110)
	resultBanner.Visible = true
	resultBanner.TextTransparency = 0
	resultBanner.Size = UDim2.new(0, 200, 0, 100)
	resultBanner.Position = UDim2.new(0.5, -100, 0.32, -50)
	TweenService:Create(resultBanner, TweenInfo.new(0.4, Enum.EasingStyle.Back, Enum.EasingDirection.Out), {
		Size = UDim2.new(0, 560, 0, 100),
		Position = UDim2.new(0.5, -280, 0.32, -50),
	}):Play()
	task.delay(3, function()
		TweenService:Create(resultBanner, TweenInfo.new(0.6), { TextTransparency = 1, TextStrokeTransparency = 1 }):Play()
		task.wait(0.6)
		resultBanner.Visible = false
		resultBanner.TextStrokeTransparency = 0.2
	end)
end

-- ===================================================================
-- LOOP (vida, super, vinheta, minimapa)
-- ===================================================================
local function addDot(worldPos, color, size)
	local nx = math.clamp(worldPos.X / currentHalf, -1, 1)
	local nz = math.clamp(worldPos.Z / currentHalf, -1, 1)
	local dot = make("Frame", {
		Size = UDim2.new(0, size, 0, size),
		AnchorPoint = Vector2.new(0.5, 0.5),
		Position = UDim2.new(0.5 + nx * 0.46, 0, 0.5 + nz * 0.46, 0),
		BackgroundColor3 = color,
		BorderSizePixel = 0,
	}, dotsFolder)
	corner(dot, math.floor(size / 2))
end

RunService.RenderStepped:Connect(function(dt)
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")

	-- barra de vida + detecção de dano
	if hum and hum.Health > 0 then
		local ratio = hum.MaxHealth > 0 and math.clamp(hum.Health / hum.MaxHealth, 0, 1) or 0
		healthFill.Size = UDim2.new(ratio, 0, 1, 0)
		healthText.Text = math.floor(hum.Health) .. " / " .. math.floor(hum.MaxHealth)
		healthBg.Visible = true
		if lastHealth and hum.Health < lastHealth - 0.5 then
			damageAlpha = math.min(1, damageAlpha + 0.6)
		end
		lastHealth = hum.Health
	else
		healthBg.Visible = false
		lastHealth = nil
	end

	-- vinheta de dano some aos poucos
	if damageAlpha > 0 then
		damageAlpha = math.max(0, damageAlpha - dt * 1.6)
	end
	vigTop.BackgroundTransparency = 1 - damageAlpha * 0.7
	vigBot.BackgroundTransparency = 1 - damageAlpha * 0.7

	-- cooldown do super
	local remaining = superCooldownUntil - os.clock()
	if remaining > 0 then
		local r = math.clamp(remaining / superCooldownTotal, 0, 1)
		superCd.Size = UDim2.new(1, 0, r, 0)
		specialBtn.Text = string.format("%.1fs", remaining)
	else
		superCd.Size = UDim2.new(1, 0, 0, 0)
		specialBtn.Text = "SUPER\n(Q)"
	end

	-- minimapa (atualiza ~10x/seg)
	minimapClock += dt
	if minimap.Visible and minimapClock >= 0.1 then
		minimapClock = 0
		dotsFolder:ClearAllChildren()
		for _, pl in ipairs(Players:GetPlayers()) do
			local r = pl.Character and pl.Character:FindFirstChild("HumanoidRootPart")
			if r then
				addDot(r.Position, pl == player and Color3.fromRGB(90, 255, 130) or Color3.fromRGB(90, 160, 255), pl == player and 11 or 9)
			end
		end
		local en = workspace:FindFirstChild("Enemies")
		if en then
			for _, m in ipairs(en:GetChildren()) do
				local r = m:FindFirstChild("HumanoidRootPart")
				if r then
					addDot(r.Position, Color3.fromRGB(255, 80, 80), 8)
				end
			end
		end
	end
end)

-- ===================================================================
-- EFEITOS DE TIRO
-- ===================================================================
fxEvent.OnClientEvent:Connect(function(origin, direction, range, color)
	playSound(shootSound)
	local beam = make("Part", {
		Anchored = true,
		CanCollide = false,
		CanQuery = false,
		Material = Enum.Material.Neon,
		Color = color,
		Size = Vector3.new(0.5, 0.5, range),
		CFrame = CFrame.lookAt(origin + direction * (range / 2), origin + direction * range),
	}, workspace)
	task.spawn(function()
		for i = 1, 6 do
			beam.Transparency = i / 6
			beam.Size = Vector3.new(0.5 - i * 0.06, 0.5 - i * 0.06, range)
			task.wait(0.02)
		end
		beam:Destroy()
	end)

	local flash = make("Part", {
		Anchored = true,
		CanCollide = false,
		CanQuery = false,
		Shape = Enum.PartType.Ball,
		Material = Enum.Material.Neon,
		Color = color,
		Size = Vector3.new(2.4, 2.4, 2.4),
		CFrame = CFrame.new(origin + direction * 2),
	}, workspace)
	Debris:AddItem(flash, 0.08)
end)

hitEvent.OnClientEvent:Connect(function(position, damage, color)
	playSound(hitSound)

	-- faísca + partículas
	local spark = make("Part", {
		Anchored = true,
		CanCollide = false,
		CanQuery = false,
		Shape = Enum.PartType.Ball,
		Material = Enum.Material.Neon,
		Color = color,
		Size = Vector3.new(1.4, 1.4, 1.4),
		CFrame = CFrame.new(position),
	}, workspace)
	local emitter = make("ParticleEmitter", {
		Color = ColorSequence.new(color),
		Lifetime = NumberRange.new(0.25, 0.4),
		Speed = NumberRange.new(7, 12),
		SpreadAngle = Vector2.new(180, 180),
		Rate = 0,
		Size = NumberSequence.new(0.7, 0),
		Rotation = NumberRange.new(0, 360),
	}, spark)
	emitter:Emit(14)
	task.spawn(function()
		for i = 1, 5 do
			spark.Size = spark.Size + Vector3.new(0.5, 0.5, 0.5)
			spark.Transparency = i / 5
			task.wait(0.02)
		end
		spark:Destroy()
	end)

	-- número de dano subindo
	local holder = make("Part", {
		Anchored = true,
		CanCollide = false,
		CanQuery = false,
		Transparency = 1,
		Size = Vector3.new(0.2, 0.2, 0.2),
		CFrame = CFrame.new(position + Vector3.new(math.random(-10, 10) / 10, 2, 0)),
	}, workspace)
	local bb = make("BillboardGui", {
		Size = UDim2.new(0, 80, 0, 40),
		AlwaysOnTop = true,
		Adornee = holder,
	}, holder)
	local dmgLabel = make("TextLabel", {
		Size = UDim2.new(1, 0, 1, 0),
		BackgroundTransparency = 1,
		Font = Enum.Font.GothamBlack,
		TextSize = 26,
		TextColor3 = Color3.fromRGB(255, 230, 120),
		TextStrokeTransparency = 0.2,
		Text = "-" .. math.floor(damage),
	}, bb)
	task.spawn(function()
		for i = 1, 14 do
			holder.CFrame = holder.CFrame + Vector3.new(0, 0.18, 0)
			dmgLabel.TextTransparency = i / 14
			dmgLabel.TextStrokeTransparency = 0.2 + (i / 14) * 0.8
			task.wait(0.03)
		end
		holder:Destroy()
	end)
end)

-- ===================================================================
-- DADOS DO SERVIDOR
-- ===================================================================
syncEvent.OnClientEvent:Connect(function(data)
	local hadLess = data.Coins < (myData.Coins or 0)
	myData = data
	coinsLabel.Text = "🪙 " .. data.Coins
	local b = Brawlers[data.Selected]
	brawlerLabel.Text = "Brawler: " .. (b and b.DisplayName or data.Selected)
	if not hadLess and data.Coins > 0 then
		-- som leve quando ganha/compra
	end
	if shopOpen then
		refreshShop()
	end
end)

matchEvent.OnClientEvent:Connect(function(state)
	currentPhase = state.Phase
	if state.Phase == "COUNTDOWN" then
		matchLabel.Text = "⚔️ Começa em " .. (state.Countdown or "?") .. "s..."
	elseif state.Phase == "MATCH" then
		matchLabel.Text = "🗺️ " .. state.MapName .. "   ⏱️ " .. state.TimeLeft .. "s   🎯 " .. state.KillsToWin
	else
		matchLabel.Text = state.Winner and ("🏆 Vencedor: " .. state.Winner) or "🏠 No lobby — aguardando..."
	end

	-- tamanho do mapa atual p/ o minimapa
	for _, m in ipairs(Maps) do
		if m.Name == state.MapName then
			currentHalf = math.max(m.Size.X, m.Size.Z) / 2
		end
	end
	minimap.Visible = (state.Phase == "MATCH")

	-- banner de fim
	if state.Winner and state.Winner ~= "—" then
		showResult(state.Winner)
	end

	local txt = "🏅 PLACAR\n"
	local medals = { "🥇", "🥈", "🥉" }
	for i, entry in ipairs(state.Scores or {}) do
		txt ..= (medals[i] or (i .. ".")) .. " " .. entry.Name .. " — " .. entry.Kills .. "\n"
		if i >= 5 then
			break
		end
	end
	scoreFrame.Text = txt
end)

local toastTween
notifyEvent.OnClientEvent:Connect(function(message)
	toast.Text = message
	toast.TextTransparency = 0
	toast.BackgroundTransparency = 0.15
	local id = tick()
	toastTween = id
	task.delay(2.5, function()
		if toastTween == id then
			for a = 0, 1, 0.1 do
				toast.TextTransparency = a
				toast.BackgroundTransparency = 0.15 + a * 0.85
				task.wait(0.03)
			end
		end
	end)
end)

print("[BrawlArena] Cliente pronto ✔")
